#!/usr/bin/env python3
"""Publish symbol -> ISIN identities from an exchange capture into public.format.

The capture is `tools/capture_exchange_pages.py`'s snapshot: one record per
instrument with `symbol` and `isin`. Rows without a well-formed ISIN are dropped
here and would be rejected by the RPC anyway.
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
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
SYMBOL_RE = re.compile(r"^[A-Z0-9.]{1,16}$")


def identities(records):
    values = {}
    for row in records or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        isin = str(row.get("isin") or "").strip().upper()
        if SYMBOL_RE.fullmatch(symbol) and ISIN_RE.fullmatch(isin):
            values.setdefault(symbol, isin)
    return [{"symbol": symbol, "isin": isin} for symbol, isin in sorted(values.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        records = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(json.dumps({"status": "FAILED", "code": "INVALID_SNAPSHOT_JSON"}))
        return 1
    if isinstance(records, dict) and isinstance(records.get("records"), list):
        records = records["records"]
    if not isinstance(records, list):
        print(json.dumps({"status": "FAILED", "code": "INVALID_SNAPSHOT_SHAPE"}))
        return 1
    rows = identities(records)
    raw = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "snapshot_sha256": digest,
                          "identities": len(rows), "production_writes": 0}, sort_keys=True))
        return 0 if rows else 1
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
        f"{base}/rest/v1/rpc/apply_instrument_identities",
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
