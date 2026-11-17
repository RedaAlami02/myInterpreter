#!/usr/bin/env python3
"""Publish exchange dividends from a capture snapshot.

One row per company and payment year: amounts are summed across ordinary and
exceptional components, and the row keeps the earliest payment's dates. The
database validates the snapshot hash, maps symbols to companies and audits each
change. Dry-run unless --apply is passed.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--years", default="",
                        help="Comma-separated payment years; default current UTC year")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raw = args.snapshot.read_text(encoding="utf-8")
    try:
        records = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"status": "FAILED", "code": "INVALID_SNAPSHOT_JSON"}))
        return 1
    if not isinstance(records, list) or not 1 <= len(records) <= 200:
        print(json.dumps({"status": "FAILED", "code": "INVALID_SNAPSHOT_SHAPE"}))
        return 1
    years = sorted({int(value) for value in args.years.split(",") if value.strip()}
                   or {datetime.now(timezone.utc).year})
    if not 1 <= len(years) <= 5 or any(year < 2000 or year > 2100 for year in years):
        print(json.dumps({"status": "FAILED", "code": "INVALID_YEARS"}))
        return 1
    components = 0
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("dividends"), list):
            continue
        for item in row["dividends"]:
            if (isinstance(item, dict)
                    and isinstance(item.get("montant"), (int, float))
                    and isinstance(item.get("paiement"), str)
                    and item["paiement"][:4] in {str(year) for year in years}):
                components += 1
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "snapshot_sha256": digest,
                          "years": years, "components": components,
                          "production_writes": 0}, sort_keys=True))
        return 0
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not URL_RE.fullmatch(base):
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    try:
        headers = cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    body = json.dumps({"p_snapshot": raw, "p_snapshot_sha256": digest,
                       "p_years": years}).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/rest/v1/rpc/apply_exchange_dividends",
        data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read(300).decode("utf-8", "replace")
        code = "MIGRATION_NOT_APPLIED" if "PGRST202" in detail else "RPC_FAILED"
        print(json.dumps({"status": "FAILED", "code": code, "detail": detail[:300]}))
        return 1
    except urllib.error.URLError:
        print(json.dumps({"status": "FAILED", "code": "RPC_CONNECTION_FAILED"}))
        return 1
    print(json.dumps({"status": "COMPLETE", "snapshot_sha256": digest,
                      "result": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
