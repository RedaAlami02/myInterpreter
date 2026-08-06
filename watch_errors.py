"""
Desktop watcher for myInterpreter errors.

The cloud functions record problems in the Appwrite 'errors' collection.
Appwrite's own execution logs scroll away, so a failure at 09:15 on a Tuesday is
effectively invisible unless someone happens to look. This polls that collection,
appends everything to a local log file, and raises a desktop notification for
anything critical.

Run it in the background while your machine is on:

    python3 watch_errors.py &                 # poll every 5 minutes
    python3 watch_errors.py --interval 60     # or more often
    python3 watch_errors.py --once            # single check, for cron
    python3 watch_errors.py --since 24h       # replay recent history and exit

Log file:  ~/.myinterpreter/errors.log
State:     ~/.myinterpreter/last_seen        (so restarts do not re-notify)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

ENDPOINT = os.environ.get("APPWRITE_ENDPOINT", "https://fra.cloud.appwrite.io/v1")
PROJECT  = os.environ.get("APPWRITE_PROJECT_ID", "6a12447800077d5113ae")
DB_ID    = "myinterpreter"

HOME_DIR  = os.path.join(os.path.expanduser("~"), ".myinterpreter")
LOG_PATH  = os.path.join(HOME_DIR, "errors.log")
STATE_PATH = os.path.join(HOME_DIR, "last_seen")

# Levels that interrupt you. Everything else is logged quietly.
NOTIFY_LEVELS = {"critical"}


def api_key() -> str:
    key = os.environ.get("APPWRITE_API_KEY")
    if key:
        return key
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.txt")
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        sys.exit("No APPWRITE_API_KEY in the environment and no readable .env.txt")


def fetch_since(iso_ts, limit=100):
    """Error rows newer than `iso_ts`, oldest first."""
    queries = [{"method": "orderDesc", "attribute": "ts"},
               {"method": "limit", "values": [limit]}]
    if iso_ts:
        queries.insert(0, {"method": "greaterThan", "attribute": "ts", "values": [iso_ts]})
    qs = "&".join("queries[]=" + urllib.parse.quote(json.dumps(q)) for q in queries)
    url = f"{ENDPOINT}/databases/{DB_ID}/collections/errors/documents?{qs}"
    resp = requests.get(url, headers={"X-Appwrite-Project": PROJECT,
                                      "X-Appwrite-Key": api_key()}, timeout=30)
    resp.raise_for_status()
    return list(reversed(resp.json()["documents"]))


def notify(row):
    """Desktop notification. Silently does nothing on a headless machine."""
    title = f"myInterpreter — {row.get('source', '?')}"
    body = row.get("message", "")
    try:
        subprocess.run(
            ["notify-send", "--urgency=critical", "--app-name=myInterpreter",
             "--icon=dialog-error", title, body],
            check=False, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def write_log(row):
    line = (f"{row.get('ts', '')}  {row.get('level', '?').upper():8} "
            f"{row.get('source', '?'):16} {row.get('message', '')}")
    if row.get("context"):
        line += f"\n{'':26}└─ {row['context']}"
    with open(LOG_PATH, "a") as fh:
        fh.write(line + "\n")
    return line


def read_state():
    try:
        with open(STATE_PATH) as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def write_state(ts):
    with open(STATE_PATH, "w") as fh:
        fh.write(ts)


def parse_since(text):
    m = re.fullmatch(r"(\d+)([hdm])", text.strip().lower())
    if not m:
        sys.exit("--since expects a value like 30m, 24h or 7d")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def check(state, quiet=False):
    """One poll. Returns the newest timestamp seen."""
    rows = fetch_since(state)
    for row in rows:
        line = write_log(row)
        if not quiet:
            print(line)
        if row.get("level") in NOTIFY_LEVELS:
            notify(row)
    return rows[-1]["ts"] if rows else state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=300,
                        help="seconds between polls (default 300)")
    parser.add_argument("--once", action="store_true", help="check once and exit")
    parser.add_argument("--since", help="replay history (e.g. 24h) and exit")
    args = parser.parse_args()

    os.makedirs(HOME_DIR, exist_ok=True)

    if args.since:
        rows = fetch_since(parse_since(args.since))
        for row in rows:
            print(write_log(row))
        print(f"\n{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}. Log: {LOG_PATH}")
        return

    state = read_state()
    if args.once:
        new = check(state)
        if new:
            write_state(new)
        return

    print(f"Watching for errors every {args.interval}s. Log: {LOG_PATH}")
    print("Critical problems raise a desktop notification. Ctrl-C to stop.")
    while True:
        try:
            new = check(state)
            if new and new != state:
                state = new
                write_state(state)
        except KeyboardInterrupt:
            print("\nstopped")
            return
        except Exception as exc:
            # Never die on a transient network problem — just note and retry.
            print(f"[watcher] {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
