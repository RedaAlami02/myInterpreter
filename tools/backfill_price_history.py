#!/usr/bin/env python3
"""Backfill daily company closes from CDG into public.data.

One-off (or occasional) repair for gaps in the daily history. Live publication
writes today's rows; this fills the past. Dry-run unless --apply.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
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
        raise RuntimeError("CDG rejected the request")
    return envelope.get("Data") or []


def rows_for(symbol, history):
    closes = {}
    for row in history:
        stamp = str(row.get("DateCotation") or "")[:10]
        try:
            day = datetime.strptime(stamp, "%d/%m/%Y").date()
        except ValueError:
            continue
        close = row.get("Cloture")
        if isinstance(close, (int, float)) and close > 0:
            closes[day] = float(close)
    rows, previous = [], None
    for day in sorted(closes):
        close = closes[day]
        entry = {"symbol": symbol, "trade_day": day.isoformat(), "pa": close}
        if previous:
            entry["variation"] = round((close / previous - 1) * 100, 4)
        rows.append(entry)
        previous = close
    return rows


def fetch_formats(base, key):
    headers = cloud_auth.service_headers(key)
    headers["Accept"] = "application/json"
    request = urllib.request.Request(
        f"{base}/rest/v1/format?select=symbol&order=symbol", headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        rows = json.loads(response.read().decode("utf-8"))
    return sorted({str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--pause", type=float, default=0.3)
    args = parser.parse_args()
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not URL_RE.fullmatch(base):
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    try:
        cloud_auth.service_headers(key)
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        symbols = symbols or fetch_formats(base, key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        print(json.dumps({"status": "FAILED", "code": f"FORMAT_READ_FAILED: {error}"[:200]}))
        return 1

    rows, failures = [], []
    for symbol in symbols:
        try:
            rows.extend(rows_for(symbol, cdg_history(symbol)))
        except Exception as error:
            failures.append({"symbol": symbol, "error": f"{type(error).__name__}: {error}"[:120]})
        if args.pause:
            time.sleep(args.pause)
    summary = {"symbols": len(symbols), "rows": len(rows), "failures": failures[:10],
               "failed": len(failures)}
    if not rows:
        print(json.dumps({"status": "FAILED", "code": "NO_ROWS", **summary}, sort_keys=True))
        return 1
    if not args.apply:
        print(json.dumps({"status": "DRY_RUN", **summary, "production_writes": 0}, sort_keys=True))
        return 0
    headers = cloud_auth.service_headers(key)
    headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    applied, missing = 0, 0
    for start in range(0, len(rows), 4000):
        chunk = rows[start:start + 4000]
        raw = json.dumps(chunk, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        request = urllib.request.Request(
            f"{base}/rest/v1/rpc/apply_price_history",
            data=json.dumps({"p_snapshot": raw, "p_snapshot_sha256": digest}).encode(),
            method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read(300).decode("utf-8", "replace")
            code = "MIGRATION_NOT_APPLIED" if "PGRST202" in detail else "RPC_FAILED"
            print(json.dumps({"status": "FAILED", "code": code, "detail": detail[:300]}))
            return 1
        except urllib.error.URLError:
            print(json.dumps({"status": "FAILED", "code": "RPC_CONNECTION_FAILED"}))
            return 1
        applied += int(result.get("applied", 0))
        missing += int(result.get("missing", 0))
    print(json.dumps({"status": "COMPLETE", **summary, "applied": applied,
                      "missing": missing}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
