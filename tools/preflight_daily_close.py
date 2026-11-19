#!/usr/bin/env python3
"""Decide whether the daily close still needs publishing.

Frequent, cheap preflight for a every-15-minute schedule: one exchange probe
and one database read. Prints JSON with `run` (bool) and `reason`.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation" / "managed"))
import cloud_auth  # noqa: E402
import exchange_history  # noqa: E402
from capture_exchange_pages import session_probe  # noqa: E402

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")


def main():
    today = exchange_history.trade_day(datetime.now(timezone.utc))
    try:
        probed = session_probe()
    except Exception:
        probed = None
    if probed and probed.get("trading_day") and probed["trading_day"] != today:
        print(json.dumps({"run": False, "reason": "NO_SESSION",
                          "exchange_trading_day": probed["trading_day"]}))
        return 0
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base):
        print(json.dumps({"run": False, "reason": "INVALID_PROJECT_URL"}))
        return 0
    try:
        headers = cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"run": False, "reason": str(error)}))
        return 0
    headers["Accept"] = "application/json"
    url = (f"{base}/rest/v1/data?select=id&symbol=eq.ADH"
           f"&date=gte.{today}T00:00:00Z&limit=1")
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(json.dumps({"run": True, "reason": "CHECK_FAILED", "detail": str(error)[:120]}))
        return 0
    if rows:
        print(json.dumps({"run": False, "reason": "ALREADY_PUBLISHED", "day": today}))
    else:
        print(json.dumps({"run": True, "reason": "MISSING", "day": today}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
