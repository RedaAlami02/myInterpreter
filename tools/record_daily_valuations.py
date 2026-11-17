#!/usr/bin/env python3
"""Record daily portfolio valuations from the published close history.

One call values every owner for one day; the RPC returns counts only, never a
personal value. Backfill is conservative: a past day is skipped when the owner
traded after it, because today's holdings are then not that day's holdings.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")


def call(base, headers, payload):
    request = urllib.request.Request(
        f"{base}/rest/v1/rpc/record_all_valuations_from_history",
        data=json.dumps(payload).encode(), method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--day")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--backfill", action="store_true",
                        help="allow past days; skipped when the owner traded later")
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
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    days = []
    if args.day:
        days = [date.fromisoformat(args.day)]
    elif args.start:
        end = date.fromisoformat(args.end) if args.end else date.today()
        cursor = date.fromisoformat(args.start)
        while cursor <= end:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
    else:
        days = [date.today()]

    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "days": [d.isoformat() for d in days],
                          "production_writes": 0}, sort_keys=True))
        return 0

    totals = {"owners": 0, "created": 0, "existing": 0, "price_unavailable": 0,
              "empty": 0, "skipped": 0}
    for day in days:
        result = call(base, headers, {"p_day": day.isoformat(),
                                      "p_allow_backfill": bool(args.backfill)})
        for key_name in totals:
            totals[key_name] += int(result.get(key_name, 0))
        print(json.dumps({"day": day.isoformat(), "result": result}, sort_keys=True))
    print(json.dumps({"status": "COMPLETE", "days": len(days), "totals": totals},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
