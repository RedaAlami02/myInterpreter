#!/usr/bin/env python3
"""Read-only cloud market-data health audit.

Fetches public market tables with the service role and reports stale/missing
prices, stale fiscal years, missing shares, stale dividends and missing
shareholders. Writes a JSON/CSV/Markdown report; never writes the database.
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
import market_health
import cloud_auth

URL_RE = re.compile(r"^https://[a-z0-9]{10,40}\.supabase\.co/?$")


def fetch(base, key, table, select):
    rows = []
    offset = 0
    while True:
        url = (f"{base}/rest/v1/{table}?select={select}"
               f"&limit=1000&offset={offset}")
        headers = cloud_auth.service_headers(key)
        headers["Accept"] = "application/json"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                page = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{table} read failed ({error.code})") from None
        except urllib.error.URLError as error:
            raise RuntimeError(f"{table} connection failed: {error.reason}") from None
        if not isinstance(page, list):
            raise RuntimeError(f"{table} returned a non-list page")
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000
        if offset > 20000:
            raise RuntimeError(f"{table} pagination limit reached")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args()
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        print(json.dumps({"status": "FAILED", "code": "OUTPUT_DIRECTORY_NOT_EMPTY"}))
        return 1
    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not URL_RE.fullmatch(base):
        print(json.dumps({"status": "FAILED", "code": "INVALID_PROJECT_URL"}))
        return 1
    if not key:
        print(json.dumps({"status": "FAILED", "code": "MISSING_SERVICE_ROLE_KEY"}))
        return 1
    try:
        cloud_auth.service_headers(key)
    except cloud_auth.ServiceKeyError as error:
        print(json.dumps({"status": "FAILED", "code": str(error)}))
        return 1
    try:
        moment = (datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
                  if args.as_of else datetime.now(timezone.utc))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        dividends = fetch(base, key, "dividends",
                          "c_name,year,amount,ex_date,pay_date,confirmed,type,updated_at")
        formats = fetch(base, key, "format", "name,symbol")
        report = market_health.audit(
            fetch(base, key, "latest_prices", "c_name,pa,date,origin_collection"),
            fetch(base, key, "company", "name,fiscal_year,na,shareholders,date"),
            dividends,
            formats,
            as_of=moment, max_age_days=args.max_age_days)
        books = fetch(base, key, "market_orderbooks", "symbol,captured_at")
        book_summary, book_status, book_ages = market_health.book_health(
            books, formats, as_of=moment)
        report["summary"].update(book_summary)
        for row in report["companies"]:
            symbol = row.get("symbol")
            if not symbol:
                continue
            status = book_status.get(symbol)
            row["book_status"] = status
            row["book_age_hours"] = book_ages.get(symbol)
            if status == "MISSING":
                row["flags"].append("BOOK_MISSING")
            elif status == "STALE":
                row["flags"].append("BOOK_STALE_%dH" % (book_ages.get(symbol) or 0))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "books.json").write_text(
            json.dumps(book_status, ensure_ascii=False, indent=1), encoding="utf-8")
        (args.out_dir / "market_health.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        (args.out_dir / "dividends.json").write_text(
            json.dumps(dividends, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = market_health.to_csv_rows(report)
        with (args.out_dir / "market_health.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (args.out_dir / "market_health.md").write_text(
            market_health.to_markdown(report), encoding="utf-8")
        print(json.dumps({"status": "OK", "summary": report["summary"],
                          "outputs": ["market_health.json", "market_health.csv",
                                      "market_health.md", "dividends.json", "books.json"],
                          "production_writes": 0}, sort_keys=True))
        return 0
    except Exception as error:
        detail = (str(error)[:200] if isinstance(error, RuntimeError)
                  else f"{type(error).__name__}: {str(error)[:180]}")
        print(json.dumps({"status": "FAILED", "code": detail or "AUDIT_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
