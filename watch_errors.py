"""
Desktop watcher for myInterpreter errors.

The cloud functions record problems in the Appwrite 'errors' collection.
Appwrite's own execution logs scroll away, so a failure at 09:15 on a Tuesday is
effectively invisible unless someone happens to look. This polls that collection,
appends everything to a colour-coded local log, and raises a desktop notification
for anything serious — with a sound, no timeout, and a button that opens the log.

    python3 watch_errors.py &                 # background, poll every 5 minutes
    python3 watch_errors.py --interval 60     # more often
    python3 watch_errors.py --once            # single check, for cron
    python3 watch_errors.py --since 24h       # replay recent history and exit
    python3 watch_errors.py --test            # fire one notification of each level

Log:    ~/.myinterpreter/errors.log
State:  ~/.myinterpreter/last_seen     (so restarts do not re-notify)
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

HOME_DIR   = os.path.join(os.path.expanduser("~"), ".myinterpreter")
LOG_PATH   = os.path.join(HOME_DIR, "errors.log")
STATE_PATH = os.path.join(HOME_DIR, "last_seen")

# ── Severity ladder ───────────────────────────────────────────────────────────
# Ordered most to least serious. `notify` decides whether it interrupts you;
# everything is logged regardless, so raising a level's noise never loses data.
#
#   critical  the site is now serving wrong or missing data. Act today.
#   error     a run failed but the previous data still stands. Act this week.
#   warning   something was suppressed or degraded on purpose. Worth reading.
#   notice    informational; a record that something unusual happened.
#
# `colour` is an ANSI code for terminal output. `tag` is what appears in the log
# file, which stays plain text so it can be grepped and read anywhere.
LEVELS = {
    "critical": {"rank": 0, "notify": True,  "colour": "\033[1;97;41m", "icon": "dialog-error",
                 "sound": "dialog-error",       "urgency": "critical", "tag": "CRITICAL"},
    "error":    {"rank": 1, "notify": True,  "colour": "\033[1;31m",    "icon": "dialog-error",
                 "sound": "dialog-error",       "urgency": "critical", "tag": "ERROR   "},
    "warning":  {"rank": 2, "notify": False, "colour": "\033[1;33m",    "icon": "dialog-warning",
                 "sound": "dialog-warning",     "urgency": "normal",   "tag": "WARNING "},
    "notice":   {"rank": 3, "notify": False, "colour": "\033[0;36m",    "icon": "dialog-information",
                 "sound": "message-new-instant","urgency": "low",      "tag": "NOTICE  "},
}
UNKNOWN = {"rank": 9, "notify": False, "colour": "\033[0;37m", "icon": "dialog-information",
           "sound": "message-new-instant", "urgency": "low", "tag": "UNKNOWN "}
RESET = "\033[0m"

SOUND_DIR = "/usr/share/sounds/freedesktop/stereo"


def level_of(name):
    return LEVELS.get((name or "").lower(), UNKNOWN)


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
    resp = requests.get(f"{ENDPOINT}/databases/{DB_ID}/collections/errors/documents?{qs}",
                        headers={"X-Appwrite-Project": PROJECT, "X-Appwrite-Key": api_key()},
                        timeout=30)
    resp.raise_for_status()
    return list(reversed(resp.json()["documents"]))


def play_sound(spec):
    """Short alert sound. Silent if the theme file or player is missing."""
    path = os.path.join(SOUND_DIR, f"{spec['sound']}.oga")
    try:
        if os.path.exists(path):
            subprocess.Popen(["canberra-gtk-play", "-f", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["canberra-gtk-play", "-i", spec["sound"]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def open_log():
    try:
        subprocess.Popen(["xdg-open", LOG_PATH],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def notify(row):
    """Notification that persists until dismissed, with a button opening the log.

    -t 0 asks for no timeout. --action implies --wait, so this call blocks until
    the notification is dismissed or the button is pressed — hence a thread, so
    a notification left on screen never stalls polling.
    """
    spec = level_of(row.get("level"))
    title = f"[{spec['tag'].strip()}] myInterpreter — {row.get('source', '?')}"
    body = row.get("message", "")
    if row.get("context"):
        body += f"\n\n{row['context'][:300]}"

    play_sound(spec)

    def run():
        try:
            proc = subprocess.run(
                ["notify-send", "--app-name=myInterpreter",
                 f"--urgency={spec['urgency']}", f"--icon={spec['icon']}",
                 "-t", "0",                       # never expire on its own
                 "--action=open=Ouvrir le journal",
                 title, body],
                capture_output=True, text=True, timeout=86400,
            )
            if proc.stdout.strip() == "open":
                open_log()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    import threading
    threading.Thread(target=run, daemon=True).start()


def write_log(row):
    spec = level_of(row.get("level"))
    line = (f"{row.get('ts', '')}  {spec['tag']} "
            f"{row.get('source', '?'):16} {row.get('message', '')}")
    if row.get("context"):
        line += f"\n{'':26}└─ {row['context']}"
    with open(LOG_PATH, "a") as fh:
        fh.write(line + "\n")
    return spec, line


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


def emit(row, quiet=False):
    spec, line = write_log(row)
    if not quiet:
        colour = spec["colour"] if sys.stdout.isatty() else ""
        end = RESET if colour else ""
        print(f"{colour}{line}{end}")
    if spec["notify"]:
        notify(row)


def check(state, quiet=False):
    rows = fetch_since(state)
    for row in rows:
        emit(row, quiet)
    return rows[-1]["ts"] if rows else state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=300,
                        help="seconds between polls (default 300)")
    parser.add_argument("--once", action="store_true", help="check once and exit")
    parser.add_argument("--since", help="replay history (e.g. 24h) and exit")
    parser.add_argument("--test", action="store_true",
                        help="fire one notification of each level and exit")
    args = parser.parse_args()

    os.makedirs(HOME_DIR, exist_ok=True)

    if args.test:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
        for lvl in ("critical", "error", "warning", "notice"):
            emit({"ts": now, "source": "test", "level": lvl,
                  "message": f"Exemple de niveau « {lvl} »",
                  "context": "Ceci est un test local — rien n'a été écrit dans la base."})
            time.sleep(1)
        print(f"\nOnly levels marked notify=True raise a popup. Log: {LOG_PATH}")
        time.sleep(2)
        return

    if args.since:
        rows = fetch_since(parse_since(args.since))
        for row in rows:
            spec, line = write_log(row)
            colour = spec["colour"] if sys.stdout.isatty() else ""
            print(f"{colour}{line}{RESET if colour else ''}")
        print(f"\n{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}. Log: {LOG_PATH}")
        return

    state = read_state()
    if args.once:
        new = check(state)
        if new:
            write_state(new)
        return

    print(f"Watching every {args.interval}s. Log: {LOG_PATH}")
    print("critical and error raise a popup with sound; warning and notice are logged only.")
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
            # Never die on a transient network problem — note it and retry.
            print(f"[watcher] {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
