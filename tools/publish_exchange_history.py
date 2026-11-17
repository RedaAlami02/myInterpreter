#!/usr/bin/env python3
"""Publish one daily public.data row per company from an exchange capture.

Reads the capture snapshot (instrument records) and actions.json (market fields),
joins them with public.format and public.company, and calls
apply_exchange_history. Dry-run unless --apply.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation" / "managed"))
import cloud_auth  # noqa: E402
import exchange_history  # noqa: E402

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")


def fetch_rows(base, key, table, select):
    rows, offset = [], 0
    headers = cloud_auth.service_headers(key)
    headers["Accept"] = "application/json"
    while True:
        url = f"{base}/rest/v1/{table}?select={select}&limit=1000&offset={offset}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=45) as response:
            page = json.loads(response.read().decode("utf-8"))
        if not isinstance(page, list):
            raise RuntimeError(f"{table} returned a non-list page")
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000
        if offset > 10000:
            raise RuntimeError(f"{table} pagination limit reached")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        actions_path = args.actions or args.snapshot.parent / "actions.json"
        actions = json.loads(actions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"status": "FAILED", "code": "INVALID_CAPTURE"}))
        return 1
    if not isinstance(snapshot, list) or not isinstance(actions, list):
        print(json.dumps({"status": "FAILED", "code": "INVALID_CAPTURE_SHAPE"}))
        return 1

    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base or ""):
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    try:
        cloud_auth.service_headers(key)
        formats = fetch_rows(base, key, "format", "name,symbol")
        company_rows = fetch_rows(
            base, key, "company", "name,cp,net_profit,bpa,tc5,roe,na")
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as error:
        print(json.dumps({"status": "FAILED", "code": f"READ_FAILED: {error}"[:200]}))
        return 1
    companies = {row.get("name"): row for row in company_rows if isinstance(row, dict)}

    moment = datetime.now(timezone.utc)
    rows, unpriced = exchange_history.build_rows(snapshot, actions, formats, companies, moment)
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not rows:
        print(json.dumps({"status": "FAILED", "code": "NO_PRICED_ROWS",
                          "symbols": len(formats or [])}))
        return 1
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "snapshot_sha256": digest,
                          "rows": len(rows), "unpriced": len(unpriced),
                          "unpriced_symbols": unpriced[:20],
                          "production_writes": 0}, sort_keys=True))
        return 0
    headers = cloud_auth.service_headers(key)
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    body = json.dumps({"p_snapshot": raw, "p_snapshot_sha256": digest}).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/rest/v1/rpc/apply_exchange_history", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read(300).decode("utf-8", "replace")
        code = "MIGRATION_NOT_APPLIED" if "PGRST202" in detail else "RPC_FAILED"
        print(json.dumps({"status": "FAILED", "code": code, "detail": detail[:300]}))
        return 1
    except urllib.error.URLError:
        print(json.dumps({"status": "FAILED", "code": "RPC_CONNECTION_FAILED"}))
        return 1
    written = int((result or {}).get("applied", 0)) + int((result or {}).get("updated", 0))
    print(json.dumps({"status": "COMPLETE" if written else "NO_WRITE",
                      "snapshot_sha256": digest, "result": result},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
