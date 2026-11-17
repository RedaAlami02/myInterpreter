#!/usr/bin/env python3
"""Fetch public market/calendar observations without any Appwrite operations.

Uses the existing read-only source adapters and ignored source configuration.
New observations remain separate from the recovery copy and production data.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def adapter(function):
    directory = ROOT / "cloud_function/functions" / function / "src"
    sys.path.insert(0, str(directory))
    previous = sys.modules.pop("sources", None)
    try:
        spec = importlib.util.spec_from_file_location("public_refetch_" + function, directory / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("sources", None)
        if previous is not None:
            sys.modules["sources"] = previous
        if str(directory) in sys.path:
            sys.path.remove(str(directory))


def save(output, filename, payload, manifest):
    path = output / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(data)
    manifest["files"].append({"path": filename, "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()})


def run(output, years):
    if output.exists():
        raise ValueError("Choose a new snapshot directory")
    output.mkdir(parents=True, mode=0o700)
    manifest = {"status": "PUBLIC_SOURCE_OBSERVATIONS", "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "production_writes": False, "recovery_data_modified": False,
                "files": [], "results": [], "limitations": [
                    "Current source responses do not reproduce original historical snapshots.",
                    "No user accounts, holdings, transactions, or private records are fetched."]}
    try:
        prices = adapter("getprice")
        stocks, index, status, tickers = prices.fetch_all()
        if not tickers or not index:
            raise ValueError("Incomplete market response")
        save(output, "market_snapshot.json", {"stocks": stocks, "index": index,
             "market_status": status, "tickers": tickers,
             "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}, manifest)
        manifest["results"].append({"dataset": "current_market", "status": "fetched",
                                     "stock_rows": len(stocks), "ticker_rows": len(tickers)})
    except Exception as error:
        manifest["results"].append({"dataset": "current_market", "status": "failed",
                                     "error": type(error).__name__})
    try:
        dividends = adapter("dividends")
        for year in years:
            try:
                page = dividends.fetch_calendar(year)
                if page is None:
                    manifest["results"].append({"dataset": "dividend_calendar", "year": year,
                                                 "status": "not_published"})
                    continue
                # Keep the evidence even when a future calendar is empty or
                # its layout no longer matches the parser.
                save(output, f"dividends/{year}_raw.json", {"html": page}, manifest)
                rows = dividends.parse_calendar(page, year)
                if not rows:
                    manifest["results"].append({"dataset": "dividend_calendar", "year": year,
                                                 "status": "no_parseable_rows"})
                    continue
                save(output, f"dividends/{year}.json", {
                    "payment_year": year, "rows": rows,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}, manifest)
                manifest["results"].append({"dataset": "dividend_calendar", "year": year,
                                             "status": "fetched", "rows": len(rows)})
            except Exception as error:
                manifest["results"].append({"dataset": "dividend_calendar", "year": year,
                                             "status": "failed", "error": type(error).__name__})
            time.sleep(0.5)
    except Exception as error:
        manifest["results"].append({"dataset": "dividend_adapter", "status": "failed",
                                     "error": type(error).__name__})
    manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if any(r["status"] in ("failed", "no_parseable_rows") for r in manifest["results"]):
        manifest["status"] = "PARTIAL_PUBLIC_SOURCE_OBSERVATIONS"
    save(output, "manifest.json", {**manifest, "files": list(manifest["files"])}, {"files": []})
    print(json.dumps({"output": str(output), "status": manifest["status"],
                      "results": manifest["results"]}), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "backup_live_public_20261022")
    parser.add_argument("--years", type=int, nargs="+", default=list(range(2022, 2028)))
    args = parser.parse_args()
    output = args.output.absolute()
    if output.parent != ROOT or not output.name.startswith("backup_live_"):
        parser.error("Use an ignored backup_live_* directory directly under the project root")
    os.umask(0o077)
    run(output, args.years)


if __name__ == "__main__":
    main()
