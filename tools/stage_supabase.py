#!/usr/bin/env python3
"""Verify recovery artifacts and optionally import them into private staging.

By default this performs local validation only. --apply requires a project-bound
PostgreSQL connection in the ignored .supabase-migration.env file. No API key is
used for SQL, and no application tables, auth users, or source data are changed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_COLLECTIONS = ("company", "format", "dividends", "latest_prices")
PRIVATE_COLLECTIONS = ("achats", "ventes", "portefeuille", "benefits")


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def reject_nonfinite(_):
    raise ValueError("Non-finite JSON values cannot be imported")


def decode(value):
    return json.loads(value, parse_constant=reject_nonfinite)


def local_config(path):
    config = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid local configuration line")
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in {"SUPABASE_PROJECT_URL", "SUPABASE_DATABASE_URL",
                        "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY"}:
            raise ValueError("Unexpected configuration variable")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("Unmatched configuration quotes")
            value = value[1:-1]
        config[name] = value
    return config


def connection_options(config):
    url = urlsplit(config.get("SUPABASE_PROJECT_URL", ""))
    match = re.fullmatch(r"([a-z0-9]{10,40})\.supabase\.co", url.hostname or "")
    if (url.scheme != "https" or not match or url.username or url.password or url.port
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("Set a valid Supabase project URL")
    reference = match[1]
    uri = config.get("SUPABASE_DATABASE_URL", "")
    if not uri.startswith(("postgres://", "postgresql://")):
        raise ValueError("Set the PostgreSQL connection URI")
    options = conninfo_to_dict(uri)
    host, user = options.get("host", ""), options.get("user", "")
    direct = host == f"db.{reference}.supabase.co" and user == "postgres"
    pooled = (host.endswith(".pooler.supabase.com")
              and user == f"postgres.{reference}")
    if not (direct or pooled) or options.get("dbname") != "postgres":
        raise ValueError("Database connection does not match this Supabase project")
    if options.get("hostaddr") or options.get("service"):
        raise ValueError("Connection overrides are not permitted")
    if not options.get("password") or "[YOUR-PASSWORD]" in options["password"]:
        raise ValueError("Replace the database password placeholder locally")
    if options.get("sslmode", "require") not in ("require", "verify-ca", "verify-full"):
        raise ValueError("Database connection must use TLS")
    options.setdefault("sslmode", "require")
    options["connect_timeout"] = 15
    options["application_name"] = "myinterpreter-private-staging"
    options["options"] = "-c statement_timeout=300000 -c lock_timeout=10000"
    return options


@dataclass
class Dataset:
    name: str
    kind: str
    path: Path
    expected_hash: str
    expected_bytes: int
    expected_rows: int | None
    collection: str | None = None

    @property
    def identifier(self):
        return hashlib.sha256(f"{self.kind}\0{self.name}\0{self.expected_hash}".encode()).hexdigest()


def checked_path(root, filename):
    path = root / filename
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes the recovery directory")
    return path


def datasets(recovery, public, include_private=False):
    manifest = decode((recovery / "manifest.json").read_text())
    if manifest.get("status") != "RECOVERED_OBSERVATIONS_NOT_LIVE_SNAPSHOT":
        raise ValueError("Recovery manifest is not recognized")
    records = {entry["path"]: entry for entry in manifest["files"]}
    entry = records["recovered_market.jsonl.gz"]
    result = [Dataset("legacy/data", "recovered_observations",
                      checked_path(recovery, entry["path"]), entry["sha256"], entry["bytes"],
                      manifest["recovered_distinct_market_document_ids"], "data")]
    baseline = recovery / "baseline"
    base = decode((baseline / "manifest.json").read_text())
    for collection in PUBLIC_COLLECTIONS + (PRIVATE_COLLECTIONS if include_private else ()):
        entry = base["collections"][collection]
        result.append(Dataset("legacy/" + collection, "september_baseline",
                              checked_path(baseline, entry["file"]), entry["sha256"],
                              entry["bytes"], entry["documents"], collection))
    if public is not None:
        source_manifest = decode((public / "manifest.json").read_text())
        if source_manifest.get("status") not in (
                "PUBLIC_SOURCE_OBSERVATIONS", "PARTIAL_PUBLIC_SOURCE_OBSERVATIONS"):
            raise ValueError("Public-source manifest is not recognized")
        for entry in source_manifest["files"]:
            # HTML evidence remains in the verified local bundle; normalized
            # responses and their own source provenance go into staging.
            if entry["path"].endswith("_raw.json"):
                continue
            result.append(Dataset("fresh/" + entry["path"], "public_source_response",
                                  checked_path(public, entry["path"]), entry["sha256"],
                                  entry["bytes"], 1))
    return result


def records(dataset):
    if dataset.path.name.endswith(".jsonl.gz"):
        with gzip.open(dataset.path, "rt") as stream:
            for line in stream:
                yield decode(line)
    else:
        payload = decode(dataset.path.read_text())
        if dataset.collection is not None:
            if not isinstance(payload, list):
                raise ValueError("Legacy dataset must be a document array")
            yield from payload
        else:
            yield payload


def record_id(dataset, row):
    if not isinstance(row, dict):
        raise ValueError("Staging accepts only JSON objects")
    if dataset.collection is not None:
        if (not isinstance(row.get("$id"), str) or not row["$id"]
                or row.get("$collectionId") != dataset.collection
                or row.get("$databaseId") != "myinterpreter"
                or not isinstance(row.get("$permissions"), list)):
            raise ValueError("Legacy identity, collection, or permissions are missing")
        return row["$id"]
    return row.get("$id", "response")


def verify(dataset):
    if dataset.path.stat().st_size != dataset.expected_bytes or sha256(dataset.path) != dataset.expected_hash:
        raise ValueError("Dataset no longer matches its verified manifest")
    seen = set()
    for row in records(dataset):
        identifier = record_id(dataset, row)
        if identifier in seen:
            raise ValueError("Duplicate document IDs in dataset")
        seen.add(identifier)
    if dataset.expected_rows is not None and len(seen) != dataset.expected_rows:
        raise ValueError("Dataset row count does not match its manifest")
    return len(seen)


def import_dataset(connection, dataset, count, max_bytes):
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT source_sha256,row_count FROM migration_stage.datasets WHERE dataset_id=%s",
                           (dataset.identifier,))
            previous = cursor.fetchone()
            if previous:
                cursor.execute("SELECT COUNT(*) FROM migration_stage.documents WHERE dataset_id=%s",
                               (dataset.identifier,))
                actual = cursor.fetchone()[0]
                if previous != (dataset.expected_hash, count) or actual != count:
                    raise ValueError("Existing staging dataset failed reconciliation")
                return "already_verified"
            cursor.execute("""
                INSERT INTO migration_stage.datasets
                    (dataset_id,dataset_name,source_kind,source_sha256,source_bytes,row_count,source_metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
            """, (dataset.identifier, dataset.name, dataset.kind, dataset.expected_hash,
                  dataset.expected_bytes, count, Jsonb({
                      "collection": dataset.collection,
                      "authoritative_live_snapshot": False,
                      "private_portfolio_included": dataset.collection in PRIVATE_COLLECTIONS})))
            with cursor.copy("COPY migration_stage.documents(dataset_id,document_id,payload) FROM STDIN") as copy:
                for row in records(dataset):
                    copy.write_row((dataset.identifier, record_id(dataset, row),
                                    json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":"))))
            if sha256(dataset.path) != dataset.expected_hash:
                raise ValueError("Source file changed during import")
            cursor.execute("SELECT COUNT(*) FROM migration_stage.documents WHERE dataset_id=%s",
                           (dataset.identifier,))
            if cursor.fetchone()[0] != count:
                raise ValueError("Imported row count mismatch")
            cursor.execute("SELECT pg_database_size(current_database())")
            if cursor.fetchone()[0] > max_bytes:
                raise ValueError("Staging exceeds the configured database headroom target")
    return "imported"


def apply(config, selected, counts, max_bytes):
    options = connection_options(config)
    report = []
    with psycopg.connect(**options, autocommit=True) as connection:
        before = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        if before > max_bytes:
            raise ValueError("Existing database already exceeds staging size target")
        with connection.transaction():
            connection.execute((ROOT / "migrations/supabase/001_private_staging.sql").read_text(), prepare=False)
        for dataset, count in zip(selected, counts):
            status = import_dataset(connection, dataset, count, max_bytes)
            report.append({"dataset": dataset.name, "records": count, "status": status})
            print(json.dumps(report[-1]), flush=True)
        after = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        grants = connection.execute("""
            SELECT role_name,has_schema_privilege(role_name,'migration_stage','USAGE')
            FROM unnest(ARRAY['anon','authenticated','service_role']) AS checked_roles(role_name)
        """).fetchall()
        if any(allowed for _, allowed in grants):
            raise ValueError("Staging schema is accessible to an application role")
    return {"database_bytes_before": before, "database_bytes_after": after,
            "application_roles_have_staging_access": False, "datasets": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery", type=Path, default=ROOT / "backup_live_recovery_20261022")
    parser.add_argument("--public", type=Path, default=ROOT / "backup_live_public_20261022")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".supabase-migration.env")
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--max-database-mb", type=int, default=350)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.max_database_mb <= 0:
        parser.error("Database size target must be positive")
    os.umask(0o077)
    try:
        selected = datasets(args.recovery, args.public, args.include_private)
        counts = [verify(dataset) for dataset in selected]
        report = {"mode": "apply" if args.apply else "local_validation",
                  "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "datasets": [{"dataset": dataset.name, "records": count}
                               for dataset, count in zip(selected, counts)],
                  "records": sum(counts), "private_portfolio_included": args.include_private}
        if args.apply:
            report["target"] = apply(local_config(args.env_file), selected, counts,
                                     args.max_database_mb * 1000 * 1000)
        output = args.recovery / ("supabase_import_report.json" if args.apply else "supabase_validation_report.json")
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        return 0
    except (ValueError, KeyError, OSError, psycopg.Error) as error:
        # PostgreSQL errors and connection strings can contain private payloads
        # or credentials. Print a category, never exception text or SQL params.
        print(json.dumps({"status": "FAILED", "error_category": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
