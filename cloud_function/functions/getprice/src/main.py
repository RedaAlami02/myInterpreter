"""
Appwrite Cloud Function: fetch live market data, compute ratios, store in 'data' collection.

Environment variables (Appwrite Console → Functions → Settings → Variables):
  APPWRITE_ENDPOINT   https://fra.cloud.appwrite.io/v1
  APPWRITE_PROJECT_ID 6a12447800077d5113ae
  APPWRITE_API_KEY    <server API key with documents.read/write>

Schedule (UTC): */15 8-15 * * 1-5   (see cloud_function/appwrite.config.json)
  → every 15 min, 09:00–16:45 Casablanca time, Mon–Fri
  End-of-day cleanup is handled by the separate 'cleanup' function (cron: 0 16 * * 1-5).
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.functions import Functions
from appwrite.query import Query
from appwrite.id import ID

# The runtime imports this file as `function.src.main`, so a sibling module is
# not importable by bare name. Put this directory on the path and be explicit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sources import MARKET_API_URL, MARKET_ORIGIN
except ImportError:  # no sources.py — copy sources.example.py, or set these in
    # the function's environment variables (Console → Settings → Variables).
    MARKET_API_URL = os.environ.get("MARKET_API_URL", "")
    MARKET_ORIGIN  = os.environ.get("MARKET_ORIGIN", "")


# ── constants ─────────────────────────────────────────────────────────────────

DB_ID = "myinterpreter"

PER_GREEN  = 20;  PER_ORANGE  = 25
PEG_GREEN  =  1;  PEG_ORANGE  =  2
PR_GREEN   = 1.5; PR_ORANGE   = 2.0
PB_GREEN   = 2.0; PB_ORANGE   = 3.0

# ── Ratio sanity guards ───────────────────────────────────────────────────────
# PEG and P/R divide the PER by a growth rate and a return on equity, both stored
# as percentages. As those denominators approach zero the quotient explodes, and
# when they go negative it changes sign while remaining meaningless. Publishing
# "PEG 97.57" or "P/R -70.97" is worse than publishing nothing: a reader cannot
# tell an extreme valuation from a divide-by-almost-zero. Below these floors the
# ratio is simply not computed and the UI renders an em-dash.
MIN_TC5 = 1.0    # % five-year revenue CAGR required before PEG means anything
MIN_ROE = 1.0    # % return on equity required before P/R means anything

# The same instability runs the other way. A five-year revenue CAGR this large is
# never a growth expectation — it is a CAGR measured off a collapsed base year
# (INVOLYS 1242%, SMI 379%, ADDOHA 175%). Dividing by it yields a near-zero PEG
# that scores GREEN, quietly promoting the stock. Suppressing is the safer error.
MAX_TC5 = 100.0  # % — a company more than doubling revenue yearly for five years

# ── Upstream fetch resilience ──────────────────────────────────────────────────────
# Measured response time is ~0.3s, so the timeout is generous headroom rather
# than a tuning knob. Worst case 3 attempts ≈ 15+2+15+4+15 = 51s, inside the 90s
# function timeout even if every attempt hangs to the limit.
MKT_TIMEOUT  = 15
MKT_ATTEMPTS = 3
MKT_BACKOFF  = 2   # seconds, multiplied by the attempt number

# Ceiling on enrichment executions fired per run. Only matters on a cold database
# where every company needs onboarding; steady state fires zero.
ENRICH_MAX_PER_RUN = 5

# Companies re-checked for newer published accounts, on the first run of each
# hour only. 5 x 8 hourly runs = 40/day, so ~81 companies get swept every two
# days — ample for figures that change once a year, and light on the fundamentals API
# (each enrichment is ~17 requests).
REFRESH_PER_HOUR = 5

# A PER this large implies an earnings-per-share near zero, which in practice has
# always meant a bad fundamental rather than a real valuation (e.g. LESIEUR
# CRISTAL stored bpa=0.1 against a true figure near 11, yielding PER 3100).
# Suppress the whole earnings-derived family rather than publish the artefact.
# P/B is unaffected — it derives from share count and equity, not from BPA.
MAX_PER = 500.0

MKT_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,fr;q=0.8',
    'content-type': 'application/json',
    'origin': MARKET_ORIGIN,
    'referer': MARKET_ORIGIN + '/',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
    ),
}

# Single request: stocks (PALMARES) + MASI index + market status
MKT_PAYLOAD = {
    'ACTIONS': [
        {
            'ACTION': {'NAME': 'PALMARES-STOCKS', 'TYPE': 'SELECT', 'VALUE': 'PALMARES-STOCKS'},
            'PARAMS': [
                {'NAME': 'Lang_',       'TYPE': 'S', 'VALUE': 'XX'},
                {'NAME': 'TypeStocks_', 'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'IdPartener_', 'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'TypeOrder_',  'TYPE': 'S', 'VALUE': 'volume'},
                {'NAME': 'Frequence_',  'TYPE': 'S', 'VALUE': 'D'},
                {'NAME': 'Nbr_',        'TYPE': 'I', 'VALUE': '1'},
            ],
        },
        {
            'ACTION': {'NAME': 'INDICE-SYNTHESE', 'TYPE': 'SELECT', 'VALUE': 'INDICE-SYNTHESE'},
            'PARAMS': [
                {'NAME': 'Lang_',       'TYPE': 'S', 'VALUE': 'XX'},
                {'NAME': 'Espace_',     'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'IdPartener_', 'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'Indice_',     'TYPE': 'S', 'VALUE': 'MASI'},
            ],
        },
        {
            'ACTION': {'NAME': 'MARKET-STATUS', 'TYPE': 'SELECT', 'VALUE': 'MARKET-STATUS'},
            'PARAMS': [
                {'NAME': 'Lang_',       'TYPE': 'S', 'VALUE': 'XX'},
                {'NAME': 'Espace_',     'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'IdPartener_', 'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'NumSeq_',     'TYPE': 'I', 'VALUE': '0'},
            ],
        },
        {
            # Full instrument list (Symbol + Libelle) — used to detect brand-new
            # companies not yet in the 'format' collection.
            'ACTION': {'NAME': 'TICKER', 'TYPE': 'SELECT', 'VALUE': 'TICKER'},
            'PARAMS': [
                {'NAME': 'Espace_',     'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'IdPartener_', 'TYPE': 'I', 'VALUE': '1'},
                {'NAME': 'Lang_',       'TYPE': 'S', 'VALUE': 'XX'},
                {'NAME': 'NumseqMin_',  'TYPE': 'I', 'VALUE': '0'},
                {'NAME': 'NumseqMax_',  'TYPE': 'I', 'VALUE': '0'},
            ],
        },
    ]
}

# ── helpers ───────────────────────────────────────────────────────────────────

def num(value):
    """Coerce an upstream value to float, or None.

    The market API intermittently returns numeric fields as strings using French
    formatting (non-breaking/regular spaces as thousands separators, comma as the
    decimal point), e.g. "1 234,56". Appwrite float attributes reject any string,
    so every numeric field must pass through here before insert.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def rate(value, green, orange):
    """Traffic-light rating, or None when the ratio carries no meaning.

    A negative ratio is not a cheap company — it is a loss-making one, or one
    with negative equity. Without the <= 0 guard it lands below the green
    threshold and gets badged as the best possible value: DAR SAADA at PER
    -65.35 and STOKVIS at P/B -11.74 were both scoring green.

    The website's render path was fixed for this some time ago, but ratings are
    also *stored* on every `data` row and the Flutter app reads those directly,
    so the app kept showing the original bug. Fixing it here corrects both.
    """
    if value is None or value <= 0:
        return None
    if value <= green:   return "green"
    if value <= orange:  return "orange"
    return "red"

def fit_chart(chart_str, max_len=195):
    """Trim data_chart from the left to fit within max_len chars."""
    if not chart_str or len(chart_str) <= max_len:
        return chart_str
    parts = chart_str.split('|')
    flag   = parts[-1] if len(parts) > 1 else ''
    points = parts[0].split(';')
    while points and len(';'.join(points) + '|' + flag) > max_len:
        points.pop(0)
    return ';'.join(points) + '|' + flag

def fetch_all(context=None):
    """Single market API call → (stocks, masi, status, tickers).

    Retried, because this one request is a single point of failure for the whole
    run: if it raises, no prices are stored for that 15-minute window at all and
    the gap is never backfilled. The endpoint answers in ~0.3s, so the 15s
    timeout was never the constraint — the missing retry was. Three attempts with
    a short backoff cover a transient blip while staying far inside the 90s
    function budget.
    """
    last_error = None
    for attempt in range(1, MKT_ATTEMPTS + 1):
        try:
            resp = requests.post(MARKET_API_URL,
                                 headers=MKT_HEADERS, json=MKT_PAYLOAD,
                                 timeout=MKT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or len(data) < 3:
                raise ValueError(f"unexpected upstream payload shape: {type(data).__name__}")
            break
        except Exception as exc:
            last_error = exc
            if context:
                context.log(f"upstream fetch attempt {attempt}/{MKT_ATTEMPTS} failed: "
                            f"{type(exc).__name__}: {exc}")
            if attempt == MKT_ATTEMPTS:
                raise
            time.sleep(MKT_BACKOFF * attempt)
    else:  # pragma: no cover — the loop always breaks or raises
        raise last_error

    stocks  = data[0].get('PALMARES-STOCKS', {}).get('Data', [])
    masi    = (data[1].get('INDICE-SYNTHESE', {}).get('Data') or [{}])[0]
    status  = (data[2].get('MARKET-STATUS',   {}).get('Data') or [{}])[0]
    tickers = data[3].get('TICKER', {}).get('Data', []) if len(data) > 3 else []
    return stocks, masi, status, tickers

# Severity ladder, mirrored in watch_errors.py:
#   critical  the site now serves wrong or missing data. Act today.
#   error     this run failed but previous data still stands. Act this week.
#   warning   something was suppressed or degraded deliberately. Worth reading.
#   notice    informational record that something unusual happened.
# critical and error raise a desktop popup; the rest are logged quietly.

def log_error(db, source, level, message, ctx=None, context=None):
    """Record a problem in the 'errors' collection.

    Appwrite's own execution logs are the only other record and they scroll away,
    so a failure that happens at 09:15 on a Tuesday is effectively invisible
    unless someone happens to look. These rows are what the local watcher reads
    to raise a desktop notification.

    Never raises: logging a problem must not become a second problem.
    """
    try:
        db.create_document(DB_ID, "errors", ID.unique(), {
            'ts':      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            'source':  source[:40],
            'level':   level[:16],
            'message': str(message)[:1000],
            'context': (str(ctx)[:2000] if ctx else None),
        })
    except Exception as e:
        if context:
            context.log(f"could not record error: {e}")

def trigger_onboard(functions, fn_id, symbol, name, context):
    """Fire the onboard_company function asynchronously (fire-and-forget).
    Never raises — enrichment is best-effort and must not affect price ingestion."""
    try:
        functions.create_execution(
            fn_id,
            body=json.dumps({'symbol': symbol, 'name': name}),
            xasync=True,
        )
    except Exception as e:
        context.log(f"onboard trigger failed for {symbol}: {e}")

def all_docs(db, col_id, queries=None):
    docs, limit, offset = [], 100, 0
    base = queries or []
    while True:
        page = db.list_documents(DB_ID, col_id,
                                 queries=base + [Query.limit(limit), Query.offset(offset)])
        docs.extend([d._data for d in page.documents])
        if len(page.documents) < limit:
            break
        offset += limit
    return docs

# ── entry point ───────────────────────────────────────────────────────────────

def main(context):
    client = Client()
    client.set_endpoint(os.environ['APPWRITE_ENDPOINT']) \
          .set_project(os.environ['APPWRITE_PROJECT_ID']) \
          .set_key(os.environ['APPWRITE_API_KEY'])
    db = Databases(client)
    # Trigger executions with the per-execution dynamic key (carries this function's
    # functions.write scope); fall back to the standard key. DB writes keep using
    # the standard key above — unchanged, proven.
    dyn_key = ''
    try:
        dyn_key = (context.req.headers or {}).get('x-appwrite-key', '') or ''
    except Exception:
        dyn_key = ''
    fn_client = Client()
    fn_client.set_endpoint(os.environ['APPWRITE_ENDPOINT']) \
             .set_project(os.environ['APPWRITE_PROJECT_ID']) \
             .set_key(dyn_key or os.environ['APPWRITE_API_KEY'])
    functions = Functions(fn_client)
    onboard_fn = os.environ.get('ONBOARD_FUNCTION_ID', 'onboard_company')

    # 1. Fetch everything from the market API in one call
    try:
        stocks, masi, status, tickers = fetch_all(context)
    except Exception as e:
        # All retries exhausted: no prices are stored for this window and the
        # gap is never backfilled, so this is the most serious failure there is.
        log_error(db, "getprice", "critical",
                  f"upstream fetch failed after {MKT_ATTEMPTS} attempts: {type(e).__name__}: {e}",
                  context=context)
        raise
    context.log(f"Market: {status.get('Statut', '?')} | "
                f"MASI: {masi.get('Cours', '?')} ({masi.get('VariationP', '?')}%)")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    inserted = 0

    # 2. Load mappings and fundamentals
    fmt_docs      = all_docs(db, "format")
    symbol_to_name = {d['symbol']: d['name'] for d in fmt_docs}
    company_docs  = all_docs(db, "company")
    companies     = {d['name']: d for d in company_docs}

    # 2b. Onboard brand-new companies: any TICKER symbol not yet in 'format'.
    #     Create the format + a bare company row so the live price flows THIS run;
    #     fundamentals are filled asynchronously by the onboard_company function.
    #     Fully guarded — must never break price ingestion.
    try:
        ticker_name = {}
        for t in tickers:
            sym = t.get('Symbol')
            lib = (t.get('Libelle') or '').strip()
            if sym and lib and sym not in ticker_name:
                ticker_name[sym] = lib
        for sym, name in ticker_name.items():
            if sym in symbol_to_name:
                continue
            try:
                db.create_document(DB_ID, "format", ID.unique(),
                                   {"symbol": sym, "name": name})
            except Exception as e:
                context.log(f"format create failed {sym}: {e}")
                continue
            symbol_to_name[sym] = name
            if name not in companies:
                try:
                    co_doc = db.create_document(DB_ID, "company", ID.unique(),
                                                {"name": name})
                    companies[name] = co_doc._data
                except Exception as e:
                    context.log(f"company create failed '{name}': {e}")
            context.log(f"NEW COMPANY: {sym} / {name}")
            log_error(db, "getprice", "notice",
                      f"New listing detected: {sym} / {name}",
                      ctx="format and company rows created; fundamentals follow "
                          "asynchronously via onboard_company", context=context)
    except Exception as e:
        context.log(f"onboarding detection error: {e}")

    # 3. Build enriched stock map
    name_to_market = {}
    for row in stocks:
        sym  = row['Symbol']
        name = symbol_to_name.get(sym)
        if not name:
            continue
        cours_ref = num(row.get('CoursDeReferance'))
        cours     = num(row.get('DernierCours'))
        name_to_market[name] = {
            'symbol':      sym,
            'cours':       cours,
            'cours_ref':   cours_ref,
            'open_price':  num(row.get('Ouverture')),
            'high':        num(row.get('PlusHaut')),
            'low':         num(row.get('PlusBas')),
            'volume':      num(row.get('Volume')),
            'qty_traded':  num(row.get('QteEchangee')),
            'market_cap':  num(row.get('Capitalisation')),
            'variation':   num(row.get('Variation')),
            'variation_v': round(cours - cours_ref, 4) if cours and cours_ref else None,
            'data_chart':  fit_chart(row.get('DataChart', '')),
        }

    # 3b. Fill the gap with TICKER.
    #     PALMARES-STOCKS only returns instruments that traded during the
    #     session — typically ~68 of the ~81 listed. The illiquid remainder
    #     (AFMA, OULMES, PROMOPHARM, SAMIR, MINIERE TOUISSIT, …) was simply
    #     never stored, so those companies were invisible on the site.
    #     TICKER covers the full list and carries Cours/Variation/VariationV,
    #     and it already rides along in the same request — no extra API call.
    #
    #     These rows deliberately carry no volume/qty_traded/high/low/open:
    #     the instrument did not trade, and absent volume is the signal the
    #     UI uses to label it "non traité aujourd'hui". Never fabricate a
    #     zero there — zero volume and unknown volume must stay distinct.
    ticker_filled = 0
    for t in tickers:
        sym  = t.get('Symbol')
        name = symbol_to_name.get(sym)
        if not name or name in name_to_market:
            continue
        cours = num(t.get('Cours'))
        if not cours:
            continue
        var_v = num(t.get('VariationV'))
        name_to_market[name] = {
            'symbol':      sym,
            'cours':       cours,
            # TICKER gives no reference price directly; derive it from the
            # absolute variation when available, else leave it unset.
            'cours_ref':   round(cours - var_v, 4) if var_v is not None else None,
            'open_price':  None,
            'high':        None,
            'low':         None,
            'volume':      None,
            'qty_traded':  None,
            'market_cap':  None,
            'variation':   num(t.get('Variation')),
            'variation_v': var_v,
            'data_chart':  fit_chart(t.get('DataChart', '')),
        }
        ticker_filled += 1
    if ticker_filled:
        context.log(f"TICKER fallback supplied {ticker_filled} untraded instruments")

    # 4a. Build a last-known-price fallback map (one query, covers all suspended stocks)
    last_price_docs = db.list_documents(DB_ID, "data", queries=[
        Query.order_desc('date'),
        Query.limit(100),
    ])
    last_known_pa = {}
    for d in last_price_docs.documents:
        n  = d._data.get('c_name')
        pa = d._data.get('pa', 0) or 0
        if n and n not in last_known_pa and pa > 0:
            last_known_pa[n] = pa

    # 4b. Preload latest_prices once (c_name -> doc id) so the per-company loop
    #     does a single update/create instead of a SELECT + write each iteration.
    latest_price_id, lp_limit, lp_offset = {}, 100, 0
    while True:
        page = db.list_documents(DB_ID, "latest_prices",
                                 queries=[Query.limit(lp_limit), Query.offset(lp_offset)])
        for d in page.documents:
            latest_price_id[d._data.get('c_name')] = d.id
        if len(page.documents) < lp_limit:
            break
        lp_offset += lp_limit

    # 4. Compute ratios and insert stock docs
    missing_company = []
    for name, m in name_to_market.items():
        co = companies.get(name)
        if co is None:
            # Priced by the exchange but absent from `company`, so it silently
            # never reaches the site. Worth surfacing rather than skipping.
            missing_company.append(name)
            continue

        pa  = m['cours'] or last_known_pa.get(name, 0)
        bpa = co.get('bpa') or 0
        tc5 = co.get('tc5') or 0
        roe = co.get('roe') or 0
        na  = co.get('na')  or 0
        cp  = co.get('cp')  or 0

        # Market capitalisation straight from the exchange when available.
        #
        # `cb` was pa * na, where `na` is the share count from the fundamentals API's last
        # *reported* fiscal year. That silently goes stale the moment a company
        # splits or issues shares: MANAGEM shows 11,864,676 for 2024 against
        # 118,646,760 trading today (10:1 split), SOTHEMA 7,200,000 against
        # 38,309,500, CASH PLUS 542,500 against 24,553,090. Each understated its
        # market cap by that factor and dragged P/B down with it — SOTHEMA read
        # as a green P/B on a red company.
        #
        # The market API publishes Capitalisation per instrument on every run, computed by
        # the exchange itself, so it is both authoritative and current. Taking it
        # directly makes P/B independent of the share count and self-correcting
        # at the next split. The pa * na path stays as a fallback for TICKER-
        # sourced rows, which carry no capitalisation because they did not trade.
        cb = m.get('market_cap') or (pa * na if na else None)
        pb = cb / cp if cb is not None and cp else None

        # PER the same way: total value over total profit.
        #
        # price / earnings-per-share and market cap / net income are the same
        # number, but the second has no share count in it. Preferring it makes
        # PER immune to a stale share count for exactly the reason P/B now is —
        # after MANAGEM's 10:1 split the price was post-split while the stored
        # per-share earnings were pre-split, showing PER 30 for a company on
        # roughly 300. net_profit is RNPG in millions of dirhams.
        #
        # PER keeps its sign: a negative value is real information (the company
        # loses money) and the UI renders it as "not applicable" rather than
        # scoring it. Only an implausible magnitude is discarded.
        rnpg = co.get('net_profit')
        if m.get('market_cap') and rnpg:
            per = m['market_cap'] / (rnpg * 1_000_000)
        else:
            per = pa / bpa if bpa else None
        if per is not None and abs(per) > MAX_PER:
            context.log(f"suspect fundamentals for {name}: "
                        f"pa={pa} bpa={bpa} -> per={per:.1f}, suppressing PER/PEG/P-R")
            log_error(db, "getprice", "warning",
                      f"{name}: implausible PER {per:.0f} suppressed",
                      ctx=f"pa={pa} bpa={bpa} max_per={MAX_PER}", context=context)
            per = None

        # PEG and P/R only from a positive PER over a denominator far enough from
        # zero to be numerically stable.
        peg = per / tc5 if (per is not None and per > 0
                            and MIN_TC5 <= tc5 <= MAX_TC5) else None
        pr  = per / roe if (per is not None and per > 0 and roe >= MIN_ROE) else None

        doc = {k: v for k, v in {
            'date':        now,
            'c_name':      name,
            'symbol':      m['symbol'],
            'pa':          pa,
            'cb':          cb,
            'per':         per,
            'peg':         peg,
            'pr':          pr,
            'pb':          pb,
            'per_rating':  rate(per, PER_GREEN, PER_ORANGE),
            'peg_rating':  rate(peg, PEG_GREEN, PEG_ORANGE),
            'pr_rating':   rate(pr,  PR_GREEN,  PR_ORANGE),
            'pb_rating':   rate(pb,  PB_GREEN,  PB_ORANGE),
            'variation':   m['variation'],
            'variation_v': m['variation_v'],
            'cours_ref':   m['cours_ref'],
            'open_price':  m['open_price'],
            'high':        m['high'],
            'low':         m['low'],
            'volume':      m['volume'],
            'qty_traded':  m['qty_traded'],
            'market_cap':  m['market_cap'],
            'data_chart':  m['data_chart'] or None,
        }.items() if v is not None}

        db.create_document(DB_ID, "data", ID.unique(), doc)
        inserted += 1

        # Upsert into latest_prices (one row per company, always current).
        # Uses the preloaded id map — no per-company SELECT.
        if pa:
            lp_doc = {'c_name': name, 'pa': pa, 'date': now}
            existing_id = latest_price_id.get(name)
            if existing_id:
                db.update_document(DB_ID, "latest_prices", existing_id, lp_doc)
            else:
                new_doc = db.create_document(DB_ID, "latest_prices", ID.unique(), lp_doc)
                latest_price_id[name] = new_doc.id

    if missing_company:
        log_error(db, "getprice", "warning",
                  f"{len(missing_company)} priced instrument(s) have no company row "
                  f"and were skipped",
                  ctx=", ".join(missing_company[:20]), context=context)

    # 5. Insert MASI index as its own doc (c_name="MASI")
    masi_cours = num(masi.get('Cours'))
    if masi_cours:
        masi_doc = {k: v for k, v in {
            'date':        now,
            'c_name':      'MASI',
            'pa':          masi_cours,
            'cours_ref':   num(masi.get('CoursVeille')),
            'variation':   num(masi.get('VariationP')),
            'variation_v': num(masi.get('VariationV')),
            'high':        num(masi.get('PlusHaut')),
            'low':         num(masi.get('PlusBas')),
            'volume':      num(masi.get('Volume')),
            'qty_traded':  num(masi.get('QteEchange')),
            'market_cap':  num(masi.get('Capitalisation')),
        }.items() if v is not None}
        db.create_document(DB_ID, "data", ID.unique(), masi_doc)
        context.log(f"Inserted MASI doc: {masi_cours}")

    # 6. Trigger async enrichment for companies that have never been enriched.
    #
    #    This used to select on `not co.get('bpa')` alone, which never terminates
    #    for a company the fundamentals API has no earnings figure for: VICENNE and T2S would
    #    be re-triggered every run forever (32 runs/day) and gain nothing each
    #    time. It went unnoticed only because the trigger was failing outright on
    #    a missing executions.write scope.
    #
    #    `sector` is the completion marker: onboard_company always sets it from
    #    the fundamentals registry, so its presence means enrichment has succeeded at
    #    least once and the remaining gaps are upstream, not ours. A brand-new
    #    listing has neither field and is still picked up on the very next run.
    #    ENRICH_MAX_PER_RUN caps the fan-out on a cold database.
    #
    # 6b. Slow refresh rotation. onboard_company can now replace figures when a
    #     newer fiscal year is published, but nothing would ever call it again —
    #     the condition above only fires for companies never enriched. Annual
    #     accounts appear once a year, so a leisurely sweep is enough: a few
    #     companies on the first run of each hour works out to a full pass every
    #     couple of days, and re-running against an unchanged year writes
    #     nothing. Oldest (or unknown) fiscal year goes first so a company that
    #     has never been dated is picked up before one already on 2024.
    try:
        name_to_symbol = {v: k for k, v in symbol_to_name.items()}
        pending, triggered = 0, set()

        for cname, co in companies.items():
            if pending >= ENRICH_MAX_PER_RUN:
                context.log(f"enrichment cap {ENRICH_MAX_PER_RUN} reached; "
                            f"remaining companies retry next run")
                break
            if not co.get('bpa') and not co.get('sector'):
                sym = name_to_symbol.get(cname)
                if sym:
                    trigger_onboard(functions, onboard_fn, sym, cname, context)
                    triggered.add(cname)
                    pending += 1
        if pending:
            context.log(f"Triggered enrichment for {pending} companies missing fundamentals")

        if datetime.now(timezone.utc).minute < 15:
            stale = sorted(
                ((co.get('fiscal_year') or 0, cname) for cname, co in companies.items()
                 if cname not in triggered and name_to_symbol.get(cname)),
                key=lambda t: t[0],
            )[:REFRESH_PER_HOUR]
            for fy, cname in stale:
                trigger_onboard(functions, onboard_fn, name_to_symbol[cname], cname, context)
            if stale:
                context.log(f"Refresh sweep: {len(stale)} companies "
                            f"(oldest fiscal_year {stale[0][0] or 'unset'})")
    except Exception as e:
        context.log(f"enrichment trigger error: {e}")

    if inserted == 0:
        log_error(db, "getprice", "critical",
                  "Run stored zero companies — symbol mapping or upstream payload shape "
                  "may have changed",
                  ctx=f"stocks={len(stocks)} tickers={len(tickers)} format={len(symbol_to_name)}",
                  context=context)

    context.log(f"Inserted {inserted} stock docs at {now} "
                f"({inserted - ticker_filled} traded, {ticker_filled} via TICKER)")
    return context.res.json({"inserted": inserted, "traded": inserted - ticker_filled,
                             "untraded": ticker_filled,
                             "masi": bool(masi.get('Cours')),
                             "status": status.get('Statut', ''), "timestamp": now})
