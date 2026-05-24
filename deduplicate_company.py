"""
One-time script: remove duplicate documents from the `company` collection.
Keeps the document with the most recent `date` per unique `name`.

Usage:
    pip install appwrite
    python3 deduplicate_company.py
"""

import time
from appwrite.client import Client
from appwrite.services.databases import Databases

PROJECT_ID   = "6a12447800077d5113ae"
API_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DB_ID        = "myinterpreter"

def all_docs(db, collection_id):
    docs = []
    offset = 0
    while True:
        res = db.list_documents(DB_ID, collection_id, queries=[
            f'{{"method":"limit","values":[100]}}',
            f'{{"method":"offset","values":[{offset}]}}',
        ])
        batch = res.documents if hasattr(res, 'documents') else res['documents']
        docs.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return docs

def main():
    api_key = input("Appwrite API key: ").strip()
    client = Client()
    client.set_endpoint(API_ENDPOINT).set_project(PROJECT_ID).set_key(api_key)
    db = Databases(client)

    print("Fetching all company documents...")
    docs = all_docs(db, "company")
    print(f"Total documents: {len(docs)}")

    # Group by name
    groups = {}
    for d in docs:
        name = d.data.get('name', '')
        groups.setdefault(name, []).append(d)

    deleted = 0
    for name, group in groups.items():
        if len(group) == 1:
            continue
        # Keep the one with the latest date
        group.sort(key=lambda d: d.data.get('date') or '', reverse=True)
        keep = group[0]
        to_delete = group[1:]
        print(f"  '{name}': keeping {keep.id} ({keep.data.get('date')}), deleting {len(to_delete)}")
        for d in to_delete:
            for attempt in range(3):
                try:
                    db.delete_document(DB_ID, "company", d.id)
                    deleted += 1
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"    FAILED to delete {d.id}: {e}")
                    else:
                        time.sleep(2 ** attempt)

    unique = len(groups)
    print(f"\nDone. Deleted {deleted} duplicate(s). Unique companies: {unique}")

if __name__ == '__main__':
    main()
