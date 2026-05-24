"""
Appwrite Cloud Function: fetch live CDG Bourse prices, compute ratios, store in 'data' collection.

Environment variables (set in Appwrite Console → Functions → Settings → Variables):
  APPWRITE_ENDPOINT   https://fra.cloud.appwrite.io/v1
  APPWRITE_PROJECT_ID 6a12447800077d5113ae
  APPWRITE_API_KEY    <your server API key>

Schedule (Appwrite cron, UTC): 0 8,11,14 * * 1-5
  → 09:00, 12:00, 15:30 Casablanca time (UTC+1), Mon–Fri only
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
    'priority': 'u=1, i',
    'referer': 'https://www.cdgcapitalbourse.ma/',
    'sec-ch-ua': '"Not-A.Brand";v="24", "Chromium";v="146"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
    ),
}

CDG_PAYLOAD = {
    'ACTIONS': [{
        'ACTION': {'NAME': 'TICKER', 'TYPE': 'SELECT', 'VALUE': 'TICKER'},
        'PARAMS': [
            {'NAME': 'Espace_',    'TYPE': 'I', 'VALUE': '1'},
            {'NAME': 'IdPartener_','TYPE': 'I', 'VALUE': '1'},
            {'NAME': 'Lang_',      'TYPE': 'S', 'VALUE': 'XX'},
            {'NAME': 'NumseqMin_', 'TYPE': 'I', 'VALUE': '0'},
            {'NAME': 'NumseqMax_', 'TYPE': 'I', 'VALUE': '0'},
        ],
    }]
}

# ── helpers ───────────────────────────────────────────────────────────────────

def rate(value, green, orange):
    if value is None:
        return None
    if value <= green:
        return "green"
    if value <= orange:
        return "orange"
    return "red"

def fetch_market_data():
    session = requests.Session()
    session.get("https://www.cdgcapitalbourse.ma/Bourse/market/ATW?tab=Cotation")
    resp = session.post("https://www.cdgcapitalbourse.ma/api/", headers=CDG_HEADERS, json=CDG_PAYLOAD)
    resp.raise_for_status()
    return resp.json()[0]['TICKER']['Data']

def all_docs(db, col_id, queries=None):
    """Fetch every document in a collection (handles Appwrite's 25-doc default limit)."""
    docs = []
    limit = 100
    offset = 0
    base_queries = queries or []
    while True:
        page = db.list_documents(
            DB_ID, col_id,
            queries=base_queries + [Query.limit(limit), Query.offset(offset)]
        )
        docs.extend([d._data for d in page.documents])
        if len(page.documents) < limit:
            break
        offset += limit
    return docs

# ── entry point ───────────────────────────────────────────────────────────────

def main(context):
    endpoint   = os.environ['APPWRITE_ENDPOINT']
    project_id = os.environ['APPWRITE_PROJECT_ID']
    api_key    = os.environ['APPWRITE_API_KEY']

    client = Client()
    client.set_endpoint(endpoint).set_project(project_id).set_key(api_key)
    db = Databases(client)

    # 1. fetch live prices → {symbol: cours}
    ticker_data = fetch_market_data()
    prices = {row['Symbol']: row['Cours'] for row in ticker_data}

    # 2. load symbol→name mapping from 'format' collection
    fmt_docs = all_docs(db, "format")
    symbol_to_name = {d['symbol']: d['name'] for d in fmt_docs}

    # 3. build name→price map (only stocks we have a mapping for)
    name_to_price = {}
    for symbol, cours in prices.items():
        if symbol in symbol_to_name:
            name_to_price[symbol_to_name[symbol]] = cours

    # 4. load company fundamentals → {name: doc}
    company_docs = all_docs(db, "company")
    companies = {d['name']: d for d in company_docs}

    # 5. compute ratios and insert into 'data'
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    inserted = 0

    for name, pa in name_to_price.items():
        co = companies.get(name)
        if co is None:
            continue

        bpa = co.get('bpa') or 0
        tc5 = co.get('tc5') or 0
        roe = co.get('roe') or 0
        na  = co.get('na')  or 0
        cp  = co.get('cp')  or 0

        cb  = pa * na         if na  else None
        per = pa / bpa        if bpa else None
        peg = per / tc5       if (per is not None and tc5) else None
        pr  = per / roe       if (per is not None and roe) else None
        pb  = cb / cp         if (cb is not None and cp)   else None

        doc = {k: v for k, v in {
            'date':       now,
            'c_name':     name,
            'pa':         pa,
            'cb':         cb,
            'per':        per,
            'peg':        peg,
            'pr':         pr,
            'pb':         pb,
            'per_rating': rate(per, PER_GREEN, PER_ORANGE),
            'peg_rating': rate(peg, PEG_GREEN, PEG_ORANGE),
            'pr_rating':  rate(pr,  PR_GREEN,  PR_ORANGE),
            'pb_rating':  rate(pb,  PB_GREEN,  PB_ORANGE),
        }.items() if v is not None}

        db.create_document(DB_ID, "data", ID.unique(), doc)
        inserted += 1

    context.log(f"Inserted {inserted} data documents at {now}")
    return context.res.json({"inserted": inserted, "timestamp": now})
