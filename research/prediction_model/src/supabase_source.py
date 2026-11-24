"""Read the live Supabase market tables into the frozen research panel shape.

The research panel was originally built from an Appwrite JSON export. The
production market tables now live in Supabase with the same column layout, so
this module re-creates the export shape rather than teaching the frozen
feature code about a second database.

Two deliberate differences from the Appwrite export, both recorded in the
snapshot manifest:

* Supabase rows have no capture timestamp, so ``captured_at`` is left NaT. It
  was only used to order same-session duplicates; rows are paginated by primary
  key so the order stays deterministic.
* There is no ``errors`` collection, so ingestion errors are not part of the
  snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from .common import clean_name, numeric

PAGE = 1000
MARKET_NUMERIC = [
    "pa", "open_price", "high", "low", "volume", "qty_traded", "market_cap",
    "variation", "variation_v", "per", "pb", "pr", "peg", "cb",
]

TABLES = {
    "data": (
        "c_name,cb,cours_ref,date,high,low,market_cap,open_price,pa,pb,peg,"
        "per,pr,qty_traded,symbol,variation,variation_v,volume,id"
    ),
    "format": "id,name,symbol,isin",
    "company": "id,name,sector",
    "dividends": (
        "id,c_name,issuer,year,amount,ex_date,pay_date,pay_date_end,"
        "confirmed,type,frequency,updated_at"
    ),
    "latest_prices": "id,c_name,date,pa",
}


class SourceError(RuntimeError):
    """The live market source is unreachable or returned an unusable shape."""


def settings(env_file: Path | None = None) -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY") or ""
    if env_file is not None:
        values = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                values[name] = value.strip().strip('"').strip("'")
        url = url or (values.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
        key = key or values.get("SUPABASE_SECRET_KEY") or values.get("SUPABASE_PUBLISHABLE_KEY") or ""
    if not url.startswith("https://") or not key:
        raise SourceError("SUPABASE_PROJECT_URL and a service key are required")
    return url, key


def _fetch_page(url: str, key: str, table: str, select: str, after: str | None):
    params = {"select": select, "order": "id.asc", "limit": PAGE}
    if after is not None:
        params["id"] = f"gt.{after}"
    endpoint = f"{url}/rest/v1/{table}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        endpoint,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SourceError(f"{table}: HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise SourceError(f"{table}: {error.reason}") from error


def fetch_all(url: str, key: str, table: str) -> list[dict]:
    select = TABLES[table]
    rows: list[dict] = []
    after = None
    while True:
        page = _fetch_page(url, key, table, select, after)
        if not page:
            break
        rows.extend(page)
        after = page[-1]["id"]
        if len(page) < PAGE:
            break
    return rows


def latest_date(env_file: Path | None = None) -> str | None:
    """One request: the newest observation timestamp in the live table."""
    url, key = settings(env_file)
    endpoint = f"{url}/rest/v1/data?select=date&order=date.desc&limit=1"
    request = urllib.request.Request(
        endpoint,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            rows = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SourceError(f"data: HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise SourceError(f"data: {error.reason}") from error
    return str(rows[0]["date"])[:10] if rows else None


def snapshot(out_dir: Path, env_file: Path | None = None) -> dict:
    """Write every table the panel needs to ``out_dir`` and return a manifest."""
    url, key = settings(env_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"tables": {}, "source": "supabase"}
    for table in TABLES:
        rows = fetch_all(url, key, table)
        for row in rows:
            if table == "data":
                # Appwrite shape: `$createdAt` carried the capture time. Supabase
                # has no equivalent, so it is explicitly unknown, not backdated.
                row["$createdAt"] = None
                row["$id"] = row.pop("id")
        raw = json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
        path = out_dir / f"{table}.json"
        path.write_bytes(raw)
        manifest["tables"][table] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    manifest["data_latest"] = max(
        (str(row["date"]) for row in json.loads((out_dir / "data.json").read_text())),
        default=None,
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _frame(out_dir: Path, table: str) -> pd.DataFrame:
    rows = json.loads((out_dir / f"{table}.json").read_text(encoding="utf-8"))
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=TABLES[table].split(","))


def tables(out_dir: Path) -> dict[str, pd.DataFrame]:
    """Normalize the snapshot exactly as the Appwrite export was normalized."""
    market = _frame(out_dir, "data")
    market["c_name"] = clean_name(market["c_name"])
    market["observation_ts"] = pd.to_datetime(market["date"], utc=True, errors="coerce")
    market["captured_at"] = pd.to_datetime(market["$createdAt"], utc=True, errors="coerce")
    market["date"] = market["observation_ts"].dt.tz_localize(None).dt.normalize()
    numeric(market, MARKET_NUMERIC)

    dividends = _frame(out_dir, "dividends")
    dividends["c_name"] = clean_name(dividends["c_name"])
    for column in ("ex_date", "pay_date", "pay_date_end"):
        dividends[column] = pd.to_datetime(dividends[column], errors="coerce")
    dividends["updated_at"] = pd.to_datetime(dividends["updated_at"], utc=True, errors="coerce")
    numeric(dividends, ["amount", "year"])

    companies = _frame(out_dir, "company")
    companies["name"] = clean_name(companies["name"])
    mapping = _frame(out_dir, "format")
    mapping["name"] = clean_name(mapping["name"])

    latest = _frame(out_dir, "latest_prices")
    latest["c_name"] = clean_name(latest["c_name"])
    latest["date"] = pd.to_datetime(latest["date"], utc=True, errors="coerce")
    numeric(latest, ["pa"])

    return {
        "market": market,
        "dividends": dividends,
        "companies": companies,
        "mapping": mapping,
        "latest_prices": latest,
    }
