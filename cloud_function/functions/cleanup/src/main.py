"""
Appwrite Cloud Function: end-of-day cleanup.
Deletes intraday duplicate docs from the 'data' collection,
keeping only the latest snapshot per company for today.

Schedule (UTC): 0 16 * * 1-5   (deployed value — verify with `appwrite functions list`)
  → fires once at 16:00 UTC (17:00 Casablanca), Mon–Fri, after getprice's last run at 15:45.

Authentication uses Appwrite's per-execution dynamic API key. Grant this
function documents.read and documents.write; do not store a long-lived API key
in the function environment.
"""

import os
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

DB_ID = "myinterpreter"
DEFAULT_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DEFAULT_PROJECT = "6a12447800077d5113ae"


def all_docs(db, col_id, queries=None):
    docs, limit, offset = [], 100, 0
    base = queries or []
    while True:
        page = db.list_documents(DB_ID, col_id,
                                 queries=base + [Query.limit(limit), Query.offset(offset)])
        docs.extend([{'$id': d.id, **d._data} for d in page.documents])
        if len(page.documents) < limit:
            break
        offset += limit
    return docs


def _execution_key(context):
    """Return Appwrite's short-lived key injected for this execution."""
    try:
        key = (context.req.headers or {}).get('x-appwrite-key', '') or ''
    except Exception:
        key = ''
    if not key:
        raise RuntimeError("missing Appwrite dynamic execution key")
    return key


def main(context):
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', DEFAULT_ENDPOINT)) \
          .set_project(os.environ.get('APPWRITE_PROJECT_ID', DEFAULT_PROJECT)) \
          .set_key(_execution_key(context))
    db = Databases(client)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    context.log(f"Cleanup started for {today}")

    today_docs = all_docs(db, "data", queries=[
        Query.greater_than_equal("date", today + "T00:00:00.000+00:00"),
        Query.less_than_equal("date",    today + "T23:59:59.999+00:00"),
        Query.order_desc("date"),
    ])

    context.log(f"Found {len(today_docs)} docs for today")

    seen, deleted = set(), 0
    for doc in today_docs:
        name = doc['c_name']
        if name in seen:
            try:
                db.delete_document(DB_ID, "data", doc['$id'])
                deleted += 1
            except Exception:
                pass
        else:
            seen.add(name)

    context.log(f"Cleanup done: deleted {deleted} intraday duplicates, kept {len(seen)} companies")
    return context.res.json({"date": today, "deleted": deleted, "kept": len(seen)})
