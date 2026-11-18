#!/usr/bin/env python3
"""Capture one order-book snapshot for every listed symbol.

Medias24 is the primary source (10 levels per side); CDG Capital is the
fallback. Identities (symbol -> ISIN) come from public.format, or from an
explicit JSON file. Without either, the capture still runs across the CDG symbol
universe, so a missing database credential degrades coverage instead of stopping
the feed. The artifact is written to --out-dir/snapshot.json.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation" / "managed"))

import cloud_auth  # noqa: E402
import exchange_orderbooks as books  # noqa: E402
from capture_exchange_pages import session_probe  # noqa: E402

def load_identities_from_db():
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not key:
        return None, None
    headers = cloud_auth.service_headers(key)
    headers["Accept"] = "application/json"
    query = "/rest/v1/format?select=symbol,isin&order=symbol"
    request = urllib.request.Request(base + query, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8"))
    identities = {}
    symbols = []
    for row in rows or []:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        symbols.append(symbol)
        isin = row.get("isin")
        if isinstance(isin, str) and isin:
            identities[symbol] = isin.strip().upper()
    return symbols, identities


def load_identities_file(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.items()
    else:
        items = ((row.get("symbol"), row.get("isin")) for row in payload)
    symbols, identities = [], {}
    for symbol, isin in items:
        symbol = str(symbol or "").upper()
        if not symbol:
            continue
        symbols.append(symbol)
        if isinstance(isin, str) and isin:
            identities[symbol] = isin.strip().upper()
    return symbols, identities


def cdg_universe(post):
    payload = post({"ACTIONS": [{
        "ACTION": {"NAME": "TICKER", "TYPE": "SELECT", "VALUE": "TICKER"},
        "PARAMS": [{"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
                   {"NAME": "IdPartener_", "TYPE": "I", "VALUE": "1"},
                   {"NAME": "Lang_", "TYPE": "S", "VALUE": "XX"},
                   {"NAME": "NumseqMin_", "TYPE": "I", "VALUE": "0"},
                   {"NAME": "NumseqMax_", "TYPE": "I", "VALUE": "0"}]}]})
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("CDG_TICKER_INVALID")
    rows = (payload[0].get("TICKER") or {}).get("Data") or []
    return sorted({str(row.get("Symbol") or "").upper() for row in rows if row.get("Symbol")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--identities", type=Path)
    parser.add_argument("--levels", type=int, default=books.MAX_LEVELS)
    parser.add_argument("--pause", type=float, default=0.05)
    parser.add_argument("--force", action="store_true",
                        help="capture outside the Casablanca session window")
    args = parser.parse_args()

    moment = datetime.now(timezone.utc)
    try:
        probed = session_probe()
    except Exception:
        probed = None
    if probed and probed.get("trading_day") and probed["trading_day"] != books.casablanca_now(moment).date().isoformat():
        print(json.dumps({"status": "SKIPPED_NO_SESSION",
                          "exchange_trading_day": probed["trading_day"]}))
        return 0
    if not args.force and not books.session_open(moment):
        print(json.dumps({"status": "SKIPPED_OUTSIDE_SESSION",
                          "casablanca_time": books.casablanca_now(moment).isoformat(timespec="seconds")}))
        return 0

    def post(payload):
        return books.post_json(books.CDG_API, payload)

    symbols = None
    identities = {}
    identity_source = "none"
    if args.identities:
        symbols, identities = load_identities_file(args.identities)
        identity_source = f"file:{args.identities.name}"
    else:
        try:
            symbols, identities = load_identities_from_db()
            if symbols:
                identity_source = "supabase:format"
        except Exception as error:
            print(json.dumps({"identity_lookup": f"FAILED {type(error).__name__}"}), file=sys.stderr)
    if not symbols:
        symbols = cdg_universe(post)
        identity_source = "cdg-universe"
    if args.symbols:
        wanted = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        symbols = [s for s in symbols if s in set(wanted)] or wanted

    rows, report = books.capture(
        symbols, identities, fetch_json_fn=books.fetch_json, cdg_post=post,
        moment=moment, levels=max(1, min(args.levels, books.MAX_LEVELS)),
        pause=max(0.0, args.pause))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    (args.out_dir / "snapshot.json").write_text(snapshot, encoding="utf-8")
    digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    summary = {
        "status": "OK" if rows else "EMPTY_SNAPSHOT",
        "snapshot_sha256": digest,
        "captured_at": books.utc_stamp(moment),
        "identity_source": identity_source,
        "symbols_requested": len(symbols),
        "books_captured": len(rows),
        **{key: report[key] for key in ("medias24", "cdg", "empty", "failed", "unmapped_isin")},
        "universe_error": report.get("universe_error"),
        "empty_symbols": report.get("empty_symbols", [])[:40],
        "failures": report.get("failures", [])[:20],
    }
    (args.out_dir / "report.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
    (args.out_dir / "SHA256SUMS").write_text(f"{digest}  snapshot.json\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
