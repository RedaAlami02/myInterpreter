#!/usr/bin/env python3
"""Fail when the exchange's latest session has no published history row.

A dispatcher can stop silently: the market audit's staleness window is a week,
and the alert cron lives in the same scheduler, so on 2026-11-27 a full day of
outage produced no run and no alert. This check reads the exchange's own last
trade date and the public table, so it works from any trigger — including
GitHub's delayed schedule, which does fire when Cloudflare's does not.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_exchange_pages import session_probe  # noqa: E402

ZONE = ZoneInfo("Africa/Casablanca")
CLOSE_AFTER = time(15, 45)  # local wall clock; the same gate as the preflight
BASE = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""


def published(day):
    url = (f"{BASE}/rest/v1/data?select=id&symbol=eq.ADH"
           f"&date=gte.{day}T00:00:00Z&limit=1")
    request = urllib.request.Request(url, headers={
        "apikey": KEY,
        "Authorization": "Bearer " + KEY,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return bool(json.loads(response.read() or b"[]"))


def main():
    if not BASE or not KEY:
        print("::error::SUPABASE_PROJECT_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        return 2
    try:
        trading_day = (session_probe() or {}).get("trading_day")
    except Exception as error:
        print(f"::warning::exchange probe failed ({type(error).__name__}); liveness unknown")
        return 0
    if not trading_day:
        print("::warning::exchange reported no last-trade date; liveness unknown")
        return 0
    local = datetime.now(ZONE)
    if trading_day == local.date().isoformat() and local.time() < CLOSE_AFTER:
        print(f"session {trading_day} is still open (local {local:%H:%M}); the close is not due")
        return 0
    if published(trading_day):
        print(f"published: history exists for the exchange session {trading_day}")
        return 0
    print(f"::error::no published history for the exchange session {trading_day} — "
          "the dispatcher is not running")
    return 1


if __name__ == "__main__":
    sys.exit(main())
