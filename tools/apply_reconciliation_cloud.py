#!/usr/bin/env python3
"""Apply or stage an exchange reconciliation report through Supabase RPCs.

Cloud-safe: the report is sent as-is and the database re-validates its digest,
contract, freshness, verified share status and per-row evidence. The script
never writes company fields directly and never prints credentials.

Environment:
  SUPABASE_PROJECT_URL      https://<project>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY service-role key (never commit or print)
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

import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")
CONTRACT = "exchange-reconciliation/v1"


def post_rpc(base, key, name, payload):
    url = f"{base}/rest/v1/rpc/{name}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = cloud_auth.service_headers(key)
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read(400).decode("utf-8", "replace")
        raise RuntimeError(f"RPC {name} rejected ({error.code}): {detail[:300]}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"RPC {name} connection failed: {error.reason}") from None


def eligible(report):
    shares = changes = annual = 0
    for company in report.get("companies") or []:
        proposed = (company.get("proposed_fields") or {}).get("na")
        if (company.get("current_shares") or {}).get("status") == "VERIFIED" \
                and company.get("status") != "QUARANTINE" \
                and isinstance(proposed, (int, float)):
            shares += 1
            saved = (company.get("saved") or {}).get("na")
            if not isinstance(saved, (int, float)) or saved <= 0 \
                    or abs(proposed / saved - 1) > 0.01:
                changes += 1
        if company.get("review_class") == "AUTO_ANNUAL_CANDIDATE" \
                and (company.get("proposed_fields") or {}).get("fiscal_year"):
            annual += 1
    return shares, changes, annual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--apply-shares", action="store_true")
    parser.add_argument("--stage-annual", action="store_true")
    args = parser.parse_args()
    raw = args.report.read_text(encoding="utf-8")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"status": "FAILED", "code": "INVALID_REPORT_JSON"}))
        return 1
    if report.get("contract") != CONTRACT or not isinstance(report.get("companies"), list):
        print(json.dumps({"status": "FAILED", "code": "INVALID_REPORT_CONTRACT"}))
        return 1
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    shares, changes, annual = eligible(report)
    if not args.apply_shares and not args.stage_annual:
        print(json.dumps({
            "status": "DRY_RUN", "report_sha256": digest,
            "verified_share_rows": shares, "share_changes_vs_saved": changes,
            "annual_candidates": annual, "production_writes": 0,
        }, sort_keys=True))
        return 0
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base) or not base:
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    if not key:
        print(json.dumps({"status": "FAILED", "code": "MISSING_SERVICE_ROLE_KEY"}))
        return 1
    try:
        cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    results = {}
    try:
        if args.apply_shares:
            status, results["shares"] = post_rpc(
                base, key, "apply_exchange_share_reconciliation",
                {"p_report": raw, "p_report_sha256": digest})
        if args.stage_annual:
            status, results["annual"] = post_rpc(
                base, key, "stage_exchange_annual_candidates",
                {"p_report": raw, "p_report_sha256": digest})
        print(json.dumps({"status": "COMPLETE", "report_sha256": digest,
                          "results": results}, ensure_ascii=False, sort_keys=True))
        return 0
    except RuntimeError as error:
        print(json.dumps({"status": "FAILED", "code": "RPC_FAILED",
                          "detail": str(error)[:400]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
