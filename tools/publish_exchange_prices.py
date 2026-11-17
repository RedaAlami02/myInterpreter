#!/usr/bin/env python3
"""Publish current exchange prices from a capture snapshot into latest_prices.

The snapshot is the cloud capture artifact. The database validates the snapshot
hash, freshness, symbol mapping, share-count consistency and older-than-current
guard before updating anything. Dry-run unless --apply is passed.
"""
import argparse
import hashlib
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
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
    usable = [row for row in records if isinstance(row, dict)
              and isinstance(row.get("price"), (int, float)) and row["price"] > 0
              and isinstance(row.get("fetched_at"), str)]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "snapshot_sha256": digest,
                          "records": len(records), "usable_prices": len(usable),
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
    body = json.dumps({"p_snapshot": raw, "p_snapshot_sha256": digest}).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/rest/v1/rpc/apply_exchange_latest_prices",
        data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read(300).decode("utf-8", "replace")
        code = "MIGRATION_NOT_APPLIED" if "PGRST202" in detail else "RPC_FAILED"
        print(json.dumps({"status": "FAILED", "code": code, "detail": detail[:300]}))
        return 1
    except urllib.error.URLError as error:
        print(json.dumps({"status": "FAILED", "code": "RPC_CONNECTION_FAILED"}))
        return 1
    print(json.dumps({"status": "COMPLETE", "snapshot_sha256": digest,
                      "result": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
