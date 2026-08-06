"""
Rename a company across every collection that keys off its name.

`c_name` is the de-facto foreign key joining `data`, `latest_prices`, `achats`,
`ventes` and `portefeuille` back to `company.name` / `format.name`. There is no
referential integrity behind it, so a rename has to touch every collection in
one pass or it silently orphans price history and user holdings.

Defaults to a dry run. Nothing is written without --apply.

    python3 migrate_rename_company.py --from MANAGER --to MANAGEM
    python3 migrate_rename_company.py --from MANAGER --to MANAGEM --apply

A JSON backup of every affected document is written before the first write, and
the script refuses to run if the target name already exists (that would merge
two companies rather than rename one).
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime

import requests

ENDPOINT = os.environ.get("APPWRITE_ENDPOINT", "https://fra.cloud.appwrite.io/v1")
PROJECT  = os.environ.get("APPWRITE_PROJECT_ID", "6a12447800077d5113ae")
DB_ID    = "myinterpreter"

# collection -> attribute holding the company name
TARGETS = [
    ("format",       "name"),
    ("company",      "name"),
    ("data",         "c_name"),
    ("latest_prices", "c_name"),
    ("achats",       "c_name"),
    ("ventes",       "c_name"),
    ("portefeuille", "c_name"),
]


def api_key() -> str:
    key = os.environ.get("APPWRITE_API_KEY")
    if key:
        return key
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.txt")
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        sys.exit("No APPWRITE_API_KEY in the environment and no readable .env.txt")


HEADERS = None  # set in main()


def _url(collection, queries):
    qs = "&".join("queries[]=" + urllib.parse.quote(json.dumps(q)) for q in queries)
    return f"{ENDPOINT}/databases/{DB_ID}/collections/{collection}/documents?{qs}"


def find(collection, attribute, value):
    """Every document in `collection` whose `attribute` equals `value`."""
    out, offset = [], 0
    while True:
        queries = [
            {"method": "equal", "attribute": attribute, "values": [value]},
            {"method": "limit",  "values": [100]},
            {"method": "offset", "values": [offset]},
        ]
        resp = requests.get(_url(collection, queries), headers=HEADERS, timeout=30)
        resp.raise_for_status()
        page = resp.json()["documents"]
        out.extend(page)
        if len(page) < 100:
            return out
        offset += 100


def update(collection, doc_id, attribute, value):
    resp = requests.patch(
        f"{ENDPOINT}/databases/{DB_ID}/collections/{collection}/documents/{doc_id}",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"data": {attribute: value}},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    global HEADERS
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="old", required=True, help="current name")
    parser.add_argument("--to",   dest="new", required=True, help="corrected name")
    parser.add_argument("--apply", action="store_true",
                        help="perform the writes (default is a dry run)")
    args = parser.parse_args()

    HEADERS = {"X-Appwrite-Project": PROJECT, "X-Appwrite-Key": api_key()}

    print(f"Rename {args.old!r} -> {args.new!r}"
          f"{'' if args.apply else '   (DRY RUN — nothing will be written)'}\n")

    # Refuse to merge two existing companies into one.
    for collection, attribute in (("company", "name"), ("format", "name")):
        if find(collection, attribute, args.new):
            sys.exit(f"ABORT: {args.new!r} already exists in {collection}. "
                     f"This would merge two companies, not rename one.")

    affected, total = {}, 0
    for collection, attribute in TARGETS:
        try:
            docs = find(collection, attribute, args.old)
        except requests.HTTPError as exc:
            print(f"  {collection:15} SKIPPED — {exc}")
            continue
        affected[collection] = (attribute, docs)
        total += len(docs)
        print(f"  {collection:15} {attribute:7} {len(docs):>5} document(s)")

    print(f"\n  {total} document(s) affected in total.")
    if total == 0:
        print("Nothing to do.")
        return

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to perform the rename.")
        return

    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"backup_rename_{args.old.replace(' ', '_')}_{stamp}.json"
    with open(backup, "w") as fh:
        json.dump({c: docs for c, (_, docs) in affected.items()},
                  fh, indent=1, ensure_ascii=False)
    print(f"\nBackup written to {backup}")

    done, failed = 0, []
    for collection, (attribute, docs) in affected.items():
        for doc in docs:
            try:
                update(collection, doc["$id"], attribute, args.new)
                done += 1
            except Exception as exc:
                failed.append((collection, doc["$id"], str(exc)))
            if done % 100 == 0 and done:
                print(f"  ...{done}/{total}")
                time.sleep(0.2)   # stay clear of Appwrite Cloud rate limits
        print(f"  {collection:15} done")

    print(f"\nUpdated {done}/{total} document(s).")
    if failed:
        print(f"{len(failed)} failure(s) — the backup above still holds the originals:")
        for collection, doc_id, err in failed[:10]:
            print(f"  {collection}/{doc_id}: {err[:100]}")


if __name__ == "__main__":
    main()
