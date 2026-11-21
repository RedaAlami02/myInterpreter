#!/usr/bin/env python3
"""Decide what, if anything, this slot should publish.

Two different jobs share the schedule:

* CLOSE    — the day's `data` row does not exist yet, so capture the detail
             pages, publish prices, publish history and record valuations.
* INTRADAY — the close is already stored but `latest_prices` is older than a
             few minutes, so refresh the quotes from the one universe request.

Frequent, cheap preflight for an every-15-minute schedule: one exchange probe
and two database reads. Prints JSON with `run` (bool), `mode` and `reason`.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation" / "managed"))
import cloud_auth  # noqa: E402
import exchange_history  # noqa: E402
from capture_exchange_pages import session_probe  # noqa: E402

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")

# A quote younger than this is already fresh; the schedule runs four times an
# hour, so this only skips runs that would republish the same snapshot.
FRESH_MINUTES = 10

# The close is a local wall-clock fact, not a UTC one: Casablanca trades to
# 15:30 and the local offset moves between UTC+0 and UTC+1. Before this time a
# missing `data` row means the session is still running, so only quotes are
# refreshed — an intraday price must never be written as the day's close.
CLOSE_AFTER = time(15, 45)


def _local_now():
    return datetime.now(ZoneInfo("Africa/Casablanca"))


def _rest(base, key, path, timeout=30):
    headers = cloud_auth.service_headers(key)
    headers["Accept"] = "application/json"
    request = urllib.request.Request(f"{base}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _quote_age_minutes(base, key):
    rows = _rest(base, key, "/rest/v1/latest_prices?select=date&order=date.desc&limit=1")
    if not rows or not rows[0].get("date"):
        return None
    stamp = str(rows[0]["date"]).replace("Z", "+00:00")
    try:
        newest = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - newest).total_seconds() / 60


def main():
    today = exchange_history.trade_day(datetime.now(timezone.utc))
    try:
        probed = session_probe()
    except Exception:
        probed = None
    if probed and probed.get("trading_day") and probed["trading_day"] != today:
        print(json.dumps({"run": False, "mode": "NONE", "reason": "NO_SESSION",
                          "exchange_trading_day": probed["trading_day"]}))
        return 0
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base):
        print(json.dumps({"run": False, "mode": "NONE", "reason": "INVALID_PROJECT_URL"}))
        return 0
    try:
        cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"run": False, "mode": "NONE", "reason": str(error)}))
        return 0
    try:
        closed = _rest(base, key,
                       f"/rest/v1/data?select=id&symbol=eq.ADH"
                       f"&date=gte.{today}T00:00:00Z&limit=1")
    except Exception as error:
        # A failed check is not proof that the close is stored: publish it.
        print(json.dumps({"run": True, "mode": "CLOSE", "reason": "CHECK_FAILED",
                          "detail": str(error)[:120]}))
        return 0
    if not closed:
        local = _local_now()
        if local.time() < CLOSE_AFTER:
            # Session still running: the day has no official close yet.
            print(json.dumps({"run": True, "mode": "INTRADAY", "reason": "SESSION_OPEN",
                              "day": today, "local_time": local.strftime("%H:%M")}))
            return 0
        print(json.dumps({"run": True, "mode": "CLOSE", "reason": "MISSING", "day": today}))
        return 0
    try:
        age = _quote_age_minutes(base, key)
    except Exception as error:
        print(json.dumps({"run": False, "mode": "NONE", "reason": "QUOTE_CHECK_FAILED",
                          "detail": str(error)[:120]}))
        return 0
    if age is not None and age < FRESH_MINUTES:
        print(json.dumps({"run": False, "mode": "NONE", "reason": "ALREADY_FRESH",
                          "quote_age_minutes": round(age, 1)}))
        return 0
    print(json.dumps({"run": True, "mode": "INTRADAY", "reason": "PRICE_STALE",
                      "day": today,
                      "quote_age_minutes": None if age is None else round(age, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
