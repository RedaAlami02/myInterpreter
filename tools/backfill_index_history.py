#!/usr/bin/env python3
"""Backfill daily index closes (MASI, MASI20) from CDG into public.data.

One-off: live publication writes today's close every weekday; this fills the
history the chart needs when a period older than the publication start is
selected. Dry-run unless --apply.
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
import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")
CDG_API = "https://www.cdgcapitalbourse.ma/api/"


def cdg_history(symbol):
    action = {"ACTION": {"NAME": "VALEUR-GRAPH-APPL", "TYPE": "SELECT", "VALUE": "VALEUR-GRAPH-APPL"},
              "PARAMS": [{"NAME": "Lang_", "TYPE": "S", "VALUE": "FR"},
                         {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
                         {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}]}
    body = json.dumps({"ACTIONS": [action]}).encode()
    request = urllib.request.Request(
        CDG_API, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "bourse-data/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.load(response)
    envelope = payload[0].get("VALEUR-GRAPH-APPL") or {}
    if not envelope.get("Valid"):
        raise RuntimeError(f"{symbol}: CDG rejected the request")
    return envelope.get("Data") or []


def rows_for(symbol, history):
    parsed = []
    for row in history:
        stamp = str(row.get("DateCotation") or "")[:10]
        try:
            day = datetime.strptime(stamp, "%d/%m/%Y").date()
        except ValueError:
            continue
        close = row.get("Cloture")
        if not isinstance(close, (int, float)) or close <= 0:
            continue
        parsed.append((day, float(close)))
    parsed.sort()
    rows, previous = [], None
    for day, close in parsed:
        variation = round((close / previous - 1) * 100, 4) if previous else None
        entry = {"symbol": symbol, "trade_day": day.isoformat(), "pa": close}
        if variation is not None:
            entry["variation"] = variation
        rows.append(entry)
        previous = close
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--symbols", default="MASI")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    rows = []
    for symbol in symbols:
        history = cdg_history(symbol)
        rows.extend(rows_for(symbol, history))
        print(json.dumps({"symbol": symbol, "points": len(history)},
                         sort_keys=True), file=sys.stderr)
    if not rows:
        print(json.dumps({"status": "FAILED", "code": "NO_ROWS"}))
        return 1
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", "rows": len(rows), "sha256": digest,
                          "first": rows[0], "last": rows[-1], "production_writes": 0},
                         ensure_ascii=False, sort_keys=True))
        return 0
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
    request = urllib.request.Request(
        f"{base}/rest/v1/rpc/apply_index_history",
        data=json.dumps({"p_snapshot": raw, "p_snapshot_sha256": digest}).encode(),
        method="POST", headers=headers)
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
    print(json.dumps({"status": "COMPLETE", "sha256": digest, "result": result},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
