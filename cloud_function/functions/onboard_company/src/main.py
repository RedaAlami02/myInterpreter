"""
Appwrite Cloud Function: onboard_company

Enriches a single company's fundamentals from the upstream API and writes them into
the 'company' collection. Triggered asynchronously by the getprice scraper when
it detects a brand-new listing, or to backfill any company still missing
fundamentals.

This is a Python port of handlers/market_proxy.php::mkt_fetch_symbol() from the
PHP website. Keep the two in sync when the upstream endpoints change.

Input (execution body JSON, or query string):
  { "symbol": "ATW", "name": "ATTIJARIWAFA BANK" }
  - symbol is required; name (canonical join key) is resolved from 'format' if absent.

Environment variables:
  APPWRITE_ENDPOINT   https://fra.cloud.appwrite.io/v1
  APPWRITE_PROJECT_ID 6a12447800077d5113ae
  APPWRITE_API_KEY    <server API key with documents.read/write>
"""

import os
import sys
import re
import json
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID

# The runtime imports this file as `function.src.main`, so a sibling module is
# not importable by bare name. Put this directory on the path and be explicit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sources import FUNDAMENTALS_BASE, FUNDAMENTALS_ORIGIN
except ImportError:  # no sources.py — copy sources.example.py, or set these in
    # the function's environment variables (Console → Settings → Variables).
    FUNDAMENTALS_BASE   = os.environ.get("FUNDAMENTALS_BASE", "")
    FUNDAMENTALS_ORIGIN = os.environ.get("FUNDAMENTALS_ORIGIN", "")


DB_ID = "myinterpreter"

# Non-secret defaults (also present in the SDK/config); the API key comes from the
# per-execution dynamic key (x-appwrite-key header) or a standard key env fallback.
DEFAULT_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DEFAULT_PROJECT  = "6a12447800077d5113ae"

SRC1 = FUNDAMENTALS_BASE
SRC2 = FUNDAMENTALS_BASE + "/supabase"
# The upstream proxy returns 403 without a same-origin Referer/Origin.
HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Referer": FUNDAMENTALS_ORIGIN + "/",
    "Origin": FUNDAMENTALS_ORIGIN,
}
TIMEOUT = 10

# ── Upstream fetch helpers ─────────────────────────────────────────────────────
#
# These used to `except Exception: return None`, which made an upstream outage
# indistinguishable from "this company genuinely has no data". Enrichment could
# fail for every company indefinitely and the only visible symptom was companies
# stuck without fundamentals. Failures are now retried and recorded so main() can
# report them.
#
# Concurrency note: 15 parallel table reads per company was measured at ~0.5s
# with no failures, and 8 concurrent companies (~136 requests) completed in 2.2s
# clean. The fan-out itself is not a problem. MAX_FETCH_WORKERS caps it anyway
# because the number of *concurrent executions* is set by getprice's trigger
# loop — on a fresh database that is every company at once, which is untested.

RETRY_ATTEMPTS = 3
RETRY_BACKOFF  = 0.5   # seconds, multiplied by the attempt number
MAX_FETCH_WORKERS = 8

_failures = []
_failures_lock = threading.Lock()

def _record_failure(what, exc):
    with _failures_lock:
        _failures.append(f"{what}: {type(exc).__name__}: {exc}")

def reset_failures():
    with _failures_lock:
        _failures.clear()

def fetch_failures():
    with _failures_lock:
        return list(_failures)

def _request(method, url, what, **kwargs):
    """One upstream call with bounded retries. Returns parsed JSON or None.

    A non-ok HTTP status is retried too — the upstream fronts Supabase and returns
    502/504 under load, which is exactly the transient case worth retrying.
    """
    last = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            r = requests.request(method, url, headers=kwargs.pop("headers", HEADERS),
                                 timeout=TIMEOUT, **kwargs)
            if r.ok:
                return r.json()
            last = RuntimeError(f"HTTP {r.status_code}")
            # 4xx other than 429 is a permanent answer; retrying wastes time.
            if 400 <= r.status_code < 500 and r.status_code != 429:
                break
        except Exception as exc:
            last = exc
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF * attempt)
    if last is not None:
        _record_failure(what, last)
    return None

def _get(url):
    return _request("GET", url, what=url.rsplit("/api/proxy", 1)[-1] or url)

def _post_sb(table, col, val, single=True, sel=None):
    """POST a Supabase-style query to the upstream proxy."""
    opts = {"filter": {"column": col, "value": val}, "single": single}
    if sel:
        opts["select"] = sel
    body = json.dumps({"table": table, "options": opts})
    return _request("POST", SRC2, what=f"{table}[{col}={val}]",
                    headers={**HEADERS, "Content-Type": "application/json"},
                    data=body)

def _data(r):
    return r.get("data") if isinstance(r, dict) else None

def _to_float(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None

def _latest(r, allow_projected=False):
    """Most recent reported yearly value (2024 → 2021).

    `allow_projected` additionally accepts the upstream feed's forecast columns ('2025p',
    '2026p', …) when no reported year has a value. Use it ONLY for figures that
    do not depend on performance — share count is the one case: a company listed
    in 2025 has nulls for every reported year, so without this its share count
    stays unknown forever and any stored placeholder is never corrected.
    (VICENNE sat at 100,000 against a real 10,258,850, making its P/B read 0.08
    and score green instead of 7.98 and red.)

    Never enable it for revenue, profit or equity — publishing a forecast as a
    reported figure is exactly the kind of silent wrongness this audit removed.
    """
    d = _data(r)
    if not isinstance(d, dict):
        return None
    for y in _reported_years(r)[:MAX_LOOKBACK]:
        f = _to_float(d.get(y))
        if f is not None:
            return f
    if allow_projected:
        # Nearest forecast first: '2025p' before '2027p'.
        for k in sorted(k for k in d if isinstance(k, str) and re.match(r'^\d{4}p$', k)):
            f = _to_float(d[k])
            if f is not None:
                return f
    return None

def _series(r):
    """All numeric year points (keys like '2024' or '2024p')."""
    d = _data(r)
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(k, str) and re.match(r'^\d{4}p?$', k):
                f = _to_float(v)
                if f is not None:
                    out[k] = f
    return dict(sorted(out.items()))

# Reported-year columns are discovered from the payload, never hardcoded.
#
# These lists used to read ("2024", "2023", "2022", "2021"). That is a slow
# time bomb: the moment the upstream feed publishes a newer year the code cannot see it,
# and every figure on the site freezes at 2024 permanently with no error and no
# symptom. It had already started — ca-corpo and fp-corpo carry a reported 2025
# column today, which the hardcoded list was silently skipping.
#
# Scanning the keys means a new year is picked up the day it appears, for as
# long as the upstream feed keeps the same shape. YEAR_FLOOR only guards against junk
# keys, and MAX_LOOKBACK bounds how far back a fallback may reach.
YEAR_FLOOR   = 2000
MAX_LOOKBACK = 6

def _reported_years(*tables):
    """Four-digit reported year columns present in these tables, newest first.

    Forecast columns ('2025p') are excluded — they are projections, and only
    _shares_now() is allowed to look at those.
    """
    years = set()
    for t in tables:
        d = _data(t)
        if isinstance(d, dict):
            for k in d:
                if isinstance(k, str) and len(k) == 4 and k.isdigit() and int(k) >= YEAR_FLOOR:
                    years.add(k)
    return sorted(years, reverse=True)

def _projected_profit(profit):
    """Newest projected net profit and its year, as (year, value), or (None, None).

    Kept strictly separate from the reported figures. The upstream feed marks forecasts
    with a trailing 'p' ('2025p'), and it also promotes a column to reported
    ('2025') well after the accounts are public — IAM had reported 2025 revenue
    and equity while its profit was still only '2025p'.

    That gap is not cosmetic. IAM's reported 2024 is its Inwi-settlement year,
    which puts its PER at 48 while the projection implies about 12. Publishing
    the projection *as* a reported figure would be exactly the silent wrongness
    this audit removed, so it is stored under its own keys and every surface
    must label it a forecast.

    A literal 0 is rejected for the same reason as in _consistent_year: it is
    how the upstream feed encodes "nothing here".
    """
    d = _data(profit)
    if not isinstance(d, dict):
        return None, None
    # Nearest forecast first ('2025p' before '2027p'), matching _latest().
    # The furthest-out year is the least meaningful: a three-year projection
    # says almost nothing about what the market is pricing today.
    years = sorted(
        k for k in d
        if isinstance(k, str) and len(k) == 5 and k.endswith('p')
        and k[:4].isdigit() and int(k[:4]) >= YEAR_FLOOR)
    for k in years[:MAX_LOOKBACK]:
        v = _to_float(d.get(k))
        if v is not None and v != 0:
            return int(k[:4]), v
    return None, None

def _year_value(r, year):
    """Value for exactly `year`, or None. No falling back to another year —
    that silent fallback is what produced the mixed-year figures."""
    d = _data(r)
    if not isinstance(d, dict) or year is None:
        return None
    return _to_float(d.get(str(year)))

def _consistent_year(profit, *tables):
    """Newest reported year for which every supplied table has a usable value.

    `profit` is treated more strictly than the rest: a literal 0 is rejected.
    The upstream feed encodes "not reported" as 0 in the profit table, and taking it at
    face value picks a year with no data in it — IB MAROC and INVOLYS both show
    0 for 2024 *and* for all three forecast years, which no real company does.
    Zero is a legitimate value for other lines (net debt, dividends), so the
    strictness stays confined to profit.

    Returns an int year, or None when the tables never line up (banks, whose
    *-corpo statements the upstream feed does not publish at all).
    """
    for y in _reported_years(profit, *tables)[:MAX_LOOKBACK]:
        p = _year_value(profit, y)
        if p is None or p == 0:
            continue
        if all(_year_value(t, y) is not None for t in tables):
            return int(y)
    return None

def _shares_now(r):
    """Current share count: the highest year present, forecasts included.

    Deliberately NOT the last reported year. A split already in force shows up
    in the forward columns first — MANAGEM reports 11,864,676 for 2024 while
    118,646,760 trade today — and this figure is divided into a live price, so
    it has to describe the shares that exist now.
    """
    d = _data(r)
    if not isinstance(d, dict):
        return None
    best = None
    for k, v in d.items():
        if not (isinstance(k, str) and re.match(r'^\d{4}p?$', k)):
            continue
        f = _to_float(v)
        if f is None or f <= 0:
            continue
        yr = int(k[:4])
        if best is None or yr > best[0]:
            best = (yr, f)
    return best[1] if best else None

def _cagr(r, yr=5):
    d = _data(r)
    if not isinstance(d, dict):
        return None
    ly = lv = None
    for ys in _reported_years(r)[:MAX_LOOKBACK]:
        f = _to_float(d.get(ys))
        if f is not None and f > 0:
            ly, lv = int(ys), f
            break
    if not ly:
        return None
    pv = _to_float(d.get(str(ly - yr)))
    if pv is None or pv <= 0:
        return None
    return round((pow(lv / pv, 1 / yr) - 1) * 100, 2)

# ── main enrichment fetch (port of mkt_fetch_symbol) ───────────────────────────

def fetch_symbol(symbol):
    # Batch 1: stock, financial, symlinks (parallel GETs)
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_stock = ex.submit(_get, f"{SRC1}/stock/{symbol}")
        f_fin   = ex.submit(_get, f"{SRC1}/financial/{symbol}")
        f_syms  = ex.submit(_get, f"{SRC1}/symblinks")
        stock, fin_raw, symlinks = f_stock.result(), f_fin.result(), f_syms.result()

    fin = fin_raw.get("financialData") if isinstance(fin_raw, dict) else None
    if not isinstance(fin, dict):
        fin = {}

    ext_name = sector = None
    if isinstance(symlinks, list):
        for s in symlinks:
            if isinstance(s, dict) and s.get("symbol") == symbol:
                ext_name = s.get("name")
                sector = s.get("type")
                break
    if not ext_name and isinstance(stock, dict):
        ext_name = stock.get("name")
    if not ext_name:
        return {"error": "symbol not found in registry"}

    soc = ext_name
    # Batch 2: corporate financial tables (parallel POSTs)
    specs = {
        'rnpg':     ('rnpg-corpo',     'Société', soc, True,  None),
        'ca':       ('ca-corpo',       'Société', soc, True,  None),
        'ebe':      ('ebe-corpo',      'Société', soc, True,  None),
        'ebit':     ('ebit-corpo',     'Société', soc, True,  None),
        'fp':       ('fp-corpo',       'Société', soc, True,  None),
        'dn':       ('dn-corpo',       'Société', soc, True,  None),
        'tn':       ('tn-corpo',       'Société', soc, True,  None),
        'dpa':      ('dpa-corpo',      'Société', soc, True,  None),
        'fcf':      ('fcf-corpo',      'Société', soc, True,  None),
        'actif':    ('actif-corpo',    'Société', soc, True,  None),
        'nmt':      ('nmt-corpo',      'Société', soc, True,  None),
        'trim':     ('trim-corpo',     'Société', soc, True,  None),
        'sem':      ('sem-corpo',      'Société', soc, True,  None),
        'coursref': ('coursref-corpo', 'Société', soc, True,  None),
        'beta':     ('beta',           'Société', soc, True,  None),
        'desc':     ('descriptions',   'symbol',  symbol, True,  'description'),
        'holders':  ('actionnariat',   'Ticker',  symbol, False, 'Shareholder,Percentage'),
    }
    s2 = {}
    with ThreadPoolExecutor(max_workers=min(len(specs), MAX_FETCH_WORKERS)) as ex:
        futs = {k: ex.submit(_post_sb, *args) for k, args in specs.items()}
        for k, f in futs.items():
            s2[k] = f.result()

    # ── Pick ONE fiscal year and derive everything from it ────────────────────
    #
    # Each table used to be read independently with _latest(), so when the newest
    # year was null in one source but present in another, the metrics silently
    # came from different years. IAM is the clean example: its per-share earnings
    # for 2024 are null, so earnings fell back to 2023 (6.00) while net income
    # resolved to 2024 (1801) — an EPS and a profit figure a year apart, shown
    # side by side. An internal consistency check flagged 24 of 68 companies.
    #
    # fiscal_year is the newest year where the core statements agree, and every
    # derived figure below is pinned to it.
    fy = _consistent_year(s2['rnpg'], s2['fp'], s2['ca'])
    fy_est, rnpg_est = _projected_profit(s2['rnpg'])
    # A projection older than the reported year tells us nothing.
    if fy_est is not None and fy is not None and fy_est <= fy:
        fy_est, rnpg_est = None, None

    rnpg  = _year_value(s2['rnpg'], fy);  fp = _year_value(s2['fp'], fy)
    ca    = _year_value(s2['ca'],   fy)
    ebe   = _year_value(s2['ebe'],  fy);  ebit = _year_value(s2['ebit'], fy)
    dn    = _year_value(s2['dn'],   fy);  tn   = _year_value(s2['tn'],   fy)
    fcf_v = _year_value(s2['fcf'],  fy);  actif = _year_value(s2['actif'], fy)
    dpa_v = _year_value(s2['dpa'],  fy)

    # Share count must be CURRENT, not the reference year's, because it is
    # compared against today's price. _shares_now() takes the highest year
    # available including forecasts, which is what reflects a split already in
    # force (MANAGEM reports 11.8M for 2024 but 118.6M is trading today).
    nmt = _shares_now(s2['nmt'])

    # BPA from the reference year's profit over the current share count, rather
    # than the upstream feed's per-share column — that column is tied to the share count
    # of whichever year it came from, so after a split it silently disagrees with
    # today's price. Deriving it keeps profit, shares and price on one basis.
    bpa = None
    if rnpg is not None and nmt:
        bpa = round(rnpg * 1_000_000 / nmt, 2)
    if bpa is None:
        bpa_fin = fin.get('beneficeParAction') if isinstance(fin.get('beneficeParAction'), dict) else {}
        f = _to_float(bpa_fin.get(str(fy))) if fy else None
        if f is not None:
            bpa = f

    if dpa_v is None:
        dpa_fin = fin.get('dividendeParAction') if isinstance(fin.get('dividendeParAction'), dict) else {}
        f = _to_float(dpa_fin.get(str(fy))) if fy else None
        if f is not None:
            dpa_v = f

    roe = round(rnpg / fp * 100, 2) if (rnpg is not None and fp) else None
    tc5 = _cagr(s2['ca'], 5)
    cp  = fp * 1_000_000 if fp is not None else None
    pm  = round(rnpg / ca * 100, 2) if (rnpg is not None and ca) else None

    beta_d = _data(s2['beta'])
    beta_3y = _to_float(beta_d.get('Béta 3 ans')) if isinstance(beta_d, dict) else None
    beta_5y = _to_float(beta_d.get('Béta 5 ans')) if isinstance(beta_d, dict) else None

    desc_d = _data(s2['desc'])
    description = None
    if isinstance(desc_d, dict):
        description = (desc_d.get('description') or '').strip()[:3800] or None

    holders_d = _data(s2['holders'])
    holders_json = None
    if isinstance(holders_d, list):
        holders = [
            {'name': h.get('Shareholder', ''), 'pct': round(_to_float(h.get('Percentage')) * 100, 2)}
            for h in holders_d
            if isinstance(h, dict) and _to_float(h.get('Percentage'))
        ]
        holders = [h for h in holders if h['pct'] > 0]
        if holders:
            holders_json = json.dumps(holders, ensure_ascii=False)

    return {
        'symbol': symbol,
        'ext_name': ext_name,
        'sector': sector,
        'description': description,
        'computed': {
            'bpa': bpa, 'dpa': dpa_v, 'tc5': tc5, 'roe': roe, 'na': nmt, 'cp': cp,
            'beta_3y': beta_3y, 'beta_5y': beta_5y, 'revenue': ca, 'ebitda': ebe,
            'ebit': ebit, 'net_profit': rnpg, 'fcf': fcf_v, 'net_debt': dn,
            'net_cash': tn, 'total_assets': actif, 'profit_margin': pm,
            'rev_growth_5y': _cagr(s2['ca'], 5), 'rnpg_growth_5y': _cagr(s2['rnpg'], 5),
            'shareholders': holders_json,
            # The year every figure above is pinned to, so the site can label it
            # and a mismatch becomes visible instead of silent.
            'fiscal_year': fy,
            # The newest *projected* year and profit, kept apart from everything
            # above. Never mixed into the reported figures — only shown as a
            # clearly-labelled secondary view, because a reported year can be
            # unrepresentative (IAM 2024 was its settlement year) without the
            # projection being fact.
            'fy_est':   fy_est,
            'rnpg_est': rnpg_est,
        },
    }

# ── entry point ────────────────────────────────────────────────────────────────

def log_error(db, level, message, ctx=None, context=None):
    """Record a problem in the 'errors' collection. Never raises.

    Levels: critical / error / warning / notice — see watch_errors.py. Only the
    first two raise a desktop popup.
    """
    try:
        from datetime import datetime, timezone
        db.create_document(DB_ID, "errors", ID.unique(), {
            'ts':      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            'source':  "onboard_company",
            'level':   level[:16],
            'message': str(message)[:1000],
            'context': (str(ctx)[:2000] if ctx else None),
        })
    except Exception as e:
        if context:
            context.log(f"could not record error: {e}")

def _api_key(context):
    """Prefer Appwrite's per-execution dynamic key; fall back to a standard key env."""
    try:
        k = (context.req.headers or {}).get('x-appwrite-key', '') or ''
        if k:
            return k
    except Exception:
        pass
    return os.environ.get('APPWRITE_API_KEY', '')

def main(context):
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', DEFAULT_ENDPOINT)) \
          .set_project(os.environ.get('APPWRITE_PROJECT_ID', DEFAULT_PROJECT)) \
          .set_key(_api_key(context))
    db = Databases(client)

    # Parse input (execution body JSON, or ?symbol=&name=)
    body = {}
    try:
        raw = context.req.body
        if isinstance(raw, dict):
            body = raw
        elif isinstance(raw, str) and raw.strip():
            body = json.loads(raw)
    except Exception:
        body = {}
    symbol = (body.get('symbol') or (context.req.query or {}).get('symbol') or '').strip().upper()
    name   = (body.get('name')   or (context.req.query or {}).get('name')   or '').strip()

    if not symbol:
        return context.res.json({"ok": False, "error": "symbol required"})

    reset_failures()
    data = fetch_symbol(symbol)

    # Surface upstream trouble instead of letting it look like "no data".
    # If the upstream feed changes its schema or goes down, every enrichment silently
    # produced empty fundamentals; these lines are what makes that visible.
    problems = fetch_failures()
    if problems:
        context.log(f"enrich {symbol}: {len(problems)} upstream fetch failure(s); "
                    f"first: {problems[0]}")
        # One company failing is noise; every company failing means the upstream feed
        # changed or went down. Recording each lets that pattern be seen.
        log_error(db, "warning",
                  f"{symbol}: {len(problems)} upstream fetch failure(s)",
                  ctx="; ".join(problems[:5]), context=context)

    if not data or data.get('error'):
        msg = (data or {}).get('error', 'unavailable')
        context.log(f"enrich {symbol}: {msg}")
        return context.res.json({"ok": False, "error": msg,
                                 "upstream_failures": problems[:5]})

    c = data.get('computed', {})
    candidate = {
        'ext_name':       data.get('ext_name'),
        'sector':         data.get('sector'),
        'description':    data.get('description'),
        'shareholders':   c.get('shareholders'),
        'beta_3y':        c.get('beta_3y'),
        'beta_5y':        c.get('beta_5y'),
        'revenue':        c.get('revenue'),
        'ebitda':         c.get('ebitda'),
        'ebit':           c.get('ebit'),
        'net_profit':     c.get('net_profit'),
        'fcf':            c.get('fcf'),
        'net_debt':       c.get('net_debt'),
        'net_cash':       c.get('net_cash'),
        'total_assets':   c.get('total_assets'),
        'profit_margin':  c.get('profit_margin'),
        'fiscal_year':    c.get('fiscal_year'),
        'fy_est':         c.get('fy_est'),
        'rnpg_est':       c.get('rnpg_est'),
        'rev_growth_5y':  c.get('rev_growth_5y'),
        'rnpg_growth_5y': c.get('rnpg_growth_5y'),
        'bpa':            c.get('bpa'),
        'dpa':            c.get('dpa'),
        'tc5':            c.get('tc5'),
        'roe':            c.get('roe'),
        'na':             c.get('na'),
        'cp':             c.get('cp'),
    }

    # Resolve the canonical company name (join key).
    if not name:
        fmt = db.list_documents(DB_ID, "format",
                                queries=[Query.equal('symbol', symbol), Query.limit(1)])
        if fmt.documents:
            name = (fmt.documents[0]._data.get('name') or '').strip()
    if not name:
        return context.res.json({"ok": False, "error": "company name unresolved"})

    docs = db.list_documents(DB_ID, "company",
                             queries=[Query.equal('name', name), Query.limit(1)])
    if docs.documents:
        existing = docs.documents[0]._data
        # Fill empty fields always; replace populated ones only when the source
        # has published a NEWER fiscal year.
        #
        # This was fill-only, which meant a value was frozen the moment it was
        # first written: once bpa existed, no later publication could ever reach
        # it. Every figure on the site would have stayed on whatever year it was
        # first enriched with, forever.
        #
        # Requiring a strictly newer year keeps the useful half of that
        # behaviour. Re-running against the same year changes nothing, so manual
        # corrections survive; only genuinely newer accounts supersede them.
        # A null is never written over a real value — that matters most for
        # banks, whose *-corpo statements the upstream feed does not publish, so almost
        # every field here comes back None and their existing data must survive.
        incoming_fy = candidate.get('fiscal_year')
        stored_fy   = existing.get('fiscal_year')
        newer = incoming_fy is not None and (stored_fy is None or incoming_fy > stored_fy)

        update = {}
        for k, v in candidate.items():
            if v is None or v == '':
                continue
            if not existing.get(k) or newer:
                update[k] = v

        if update:
            db.update_document(DB_ID, "company", docs.documents[0].id, update)
        context.log(f"enriched {symbol}/{name}: {len(update)} fields"
                    f"{f' (refreshed to {incoming_fy})' if newer and stored_fy else ''}")
        return context.res.json({"ok": True, "fields": len(update),
                                 "fiscal_year": incoming_fy, "refreshed": newer,
                                 "upstream_failures": problems[:5]})
    else:
        create = {k: v for k, v in candidate.items() if v is not None and v != ''}
        create['name'] = name
        db.create_document(DB_ID, "company", ID.unique(), create)
        context.log(f"created+enriched {symbol}/{name}: {len(create)} fields")
        return context.res.json({"ok": True, "fields": len(create), "created": True,
                                 "upstream_failures": problems[:5]})
