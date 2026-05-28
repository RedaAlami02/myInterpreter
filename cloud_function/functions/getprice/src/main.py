"""
Appwrite Cloud Function: fetch live CDG Bourse data, compute ratios, store in 'data' collection.

Environment variables (Appwrite Console → Functions → Settings → Variables):
  APPWRITE_ENDPOINT   https://fra.cloud.appwrite.io/v1
  APPWRITE_PROJECT_ID 6a12447800077d5113ae
  APPWRITE_API_KEY    <server API key with documents.read/write>

Schedule (UTC): */15 8-14 * * 1-5
  → every 15 min, 09:00–15:45 Casablanca time, Mon–Fri
  End-of-day cleanup is handled by the separate 'cleanup' function (cron: 45 15 * * 1-5).
"""

import os
import requests
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID

# ── constants ─────────────────────────────────────────────────────────────────

DB_ID = "myinterpreter"

PER_GREEN  = 20;  PER_ORANGE  = 25
PEG_GREEN  =  1;  PEG_ORANGE  =  2
PR_GREEN   = 1.5; PR_ORANGE   = 2.0
PB_GREEN   = 2.0; PB_ORANGE   = 3.0

CDG_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,fr;q=0.8',
    'content-type': 'application/json',
    'origin': 'https://www.cdgcapitalbourse.ma',
    'referer': 'https://www.cdgcapitalbourse.ma/',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
    ),
}

# Single request: stocks (PALMARES) + MASI index + market status
CDG_PAYLOAD = {
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
    ]
}

# ── helpers ───────────────────────────────────────────────────────────────────

def rate(value, green, orange):
    if value is None:
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

def fetch_all():
    """Single CDG API call → (stocks, masi, status)."""
    resp = requests.post("https://www.cdgcapitalbourse.ma/api/",
                         headers=CDG_HEADERS, json=CDG_PAYLOAD, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    stocks = data[0].get('PALMARES-STOCKS', {}).get('Data', [])
    masi   = (data[1].get('INDICE-SYNTHESE', {}).get('Data') or [{}])[0]
    status = (data[2].get('MARKET-STATUS',   {}).get('Data') or [{}])[0]
    return stocks, masi, status

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

    # 1. Fetch everything from CDG in one call
    stocks, masi, status = fetch_all()
    context.log(f"Market: {status.get('Statut', '?')} | "
                f"MASI: {masi.get('Cours', '?')} ({masi.get('VariationP', '?')}%)")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    inserted = 0

    # 2. Load mappings and fundamentals
    fmt_docs      = all_docs(db, "format")
    symbol_to_name = {d['symbol']: d['name'] for d in fmt_docs}
    company_docs  = all_docs(db, "company")
    companies     = {d['name']: d for d in company_docs}

    # 3. Build enriched stock map
    name_to_market = {}
    for row in stocks:
        sym  = row['Symbol']
        name = symbol_to_name.get(sym)
        if not name:
            continue
        cours_ref = row.get('CoursDeReferance', 0)
        cours     = row.get('DernierCours', 0)
        name_to_market[name] = {
            'symbol':      sym,
            'cours':       cours,
            'cours_ref':   cours_ref,
            'open_price':  row.get('Ouverture'),
            'high':        row.get('PlusHaut'),
            'low':         row.get('PlusBas'),
            'volume':      row.get('Volume'),
            'qty_traded':  row.get('QteEchangee'),
            'market_cap':  row.get('Capitalisation'),
            'variation':   row.get('Variation'),
            'variation_v': round(cours - cours_ref, 4) if cours and cours_ref else None,
            'data_chart':  fit_chart(row.get('DataChart', '')),
        }

    # 4. Compute ratios and insert stock docs
    for name, m in name_to_market.items():
        co = companies.get(name)
        if co is None:
            continue

        pa  = m['cours']
        bpa = co.get('bpa') or 0
        tc5 = co.get('tc5') or 0
        roe = co.get('roe') or 0
        na  = co.get('na')  or 0
        cp  = co.get('cp')  or 0

        cb  = pa * na       if na                       else None
        per = pa / bpa      if bpa                      else None
        peg = per / tc5     if per is not None and tc5  else None
        pr  = per / roe     if per is not None and roe  else None
        pb  = cb / cp       if cb  is not None and cp   else None

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

    # 5. Insert MASI index as its own doc (c_name="MASI")
    if masi.get('Cours'):
        masi_doc = {k: v for k, v in {
            'date':        now,
            'c_name':      'MASI',
            'pa':          masi['Cours'],
            'cours_ref':   masi.get('CoursVeille'),
            'variation':   masi.get('VariationP'),
            'variation_v': masi.get('VariationV'),
            'high':        masi.get('PlusHaut'),
            'low':         masi.get('PlusBas'),
            'volume':      masi.get('Volume'),
            'qty_traded':  masi.get('QteEchange'),
            'market_cap':  masi.get('Capitalisation'),
        }.items() if v is not None}
        db.create_document(DB_ID, "data", ID.unique(), masi_doc)
        context.log(f"Inserted MASI doc: {masi['Cours']}")

    context.log(f"Inserted {inserted} stock docs at {now}")
    return context.res.json({"inserted": inserted, "masi": bool(masi.get('Cours')),
                             "status": status.get('Statut', ''), "timestamp": now})
