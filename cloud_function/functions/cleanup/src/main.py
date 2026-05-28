"""
Appwrite Cloud Function: end-of-day cleanup.
Deletes intraday duplicate docs from the 'data' collection,
keeping only the latest snapshot per company for today.

Schedule (UTC): 45 15 * * 1-5
  → fires once at 15:45 UTC (16:45 Casablanca), Mon–Fri

Environment variables (same as getprice):
  APPWRITE_ENDPOINT   https://fra.cloud.appwrite.io/v1
  APPWRITE_PROJECT_ID 6a12447800077d5113ae
  APPWRITE_API_KEY    <server API key with documents.read/write>
"""

import os
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

DB_ID = "myinterpreter"


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


def main(context):
    client = Client()
    client.set_endpoint(os.environ['APPWRITE_ENDPOINT']) \
          .set_project(os.environ['APPWRITE_PROJECT_ID']) \
          .set_key(os.environ['APPWRITE_API_KEY'])
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
            db.delete_document(DB_ID, "data", doc['$id'])
            deleted += 1
        else:
            seen.add(name)

    context.log(f"Cleanup done: deleted {deleted} intraday duplicates, kept {len(seen)} companies")
    return context.res.json({"date": today, "deleted": deleted, "kept": len(seen)})
