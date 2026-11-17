#!/usr/bin/env python3
"""Export saved reference rows (company or format) from Supabase as JSON.

Used by the reconciliation workflow so the report can compare the exchange
snapshot against what the site actually stores, instead of reporting every row
as a first-time change.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")
TABLES = {
    "company": "name,fiscal_year,na,bpa,cp,net_profit,revenue,roe,date",
    "format": "name,symbol",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, choices=sorted(TABLES))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base):
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    try:
        headers = cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    headers["Accept"] = "application/json"
    rows, offset = [], 0
    while True:
        url = (f"{base}/rest/v1/{args.table}?select={TABLES[args.table]}"
               f"&limit=1000&offset={offset}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=45) as response:
                page = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            print(json.dumps({"status": "FAILED",
                              "code": f"READ_FAILED: {error}"[:200]}))
            return 1
        if not isinstance(page, list):
            print(json.dumps({"status": "FAILED", "code": "NON_LIST_PAGE"}))
            return 1
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
        if offset > 10000:
            print(json.dumps({"status": "FAILED", "code": "PAGINATION_LIMIT"}))
            return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "OK", "table": args.table, "rows": len(rows),
                      "out": args.out.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
