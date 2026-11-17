#!/usr/bin/env python3
"""Build and verify typed public market tables; never changes client settings.

Original payloads stay in private staging. Only fields in market_contract.json
are promoted. Fresh source responses and private portfolios are not promoted.
"""

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from stage_supabase import ROOT, connection_options, datasets, local_config, records, verify
from verify_supabase_staging import fingerprint


CONTRACT = json.loads((ROOT / "migrations/supabase/market_contract.json").read_text())
TABLES = CONTRACT["tables"]
MARKER = "myInterpreter public market pilot v1"
MAX_BYTES = 350_000_000


def convert(value, kind):
    if value is None:
        return None
    if kind == "text":
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError("Expected valid text")
        return value
    if kind == "boolean":
        if type(value) is not bool:
            raise ValueError("Expected boolean")
        return value
    if kind in ("integer", "bigint", "numeric"):
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("Expected number")
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("Expected finite number")
        if kind == "numeric":
            return number
        bits = 32 if kind == "integer" else 64
        if number != number.to_integral_value() or not -(2**(bits-1)) <= number < 2**(bits-1):
            raise ValueError("Integer out of range")
        return int(number)
    if not isinstance(value, str):
        raise ValueError("Expected source date string")
    if kind == "date":
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError("Expected ISO date without time")
        return result
    if kind == "timestamptz":
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("Timestamp must include an offset")
        return result.astimezone(timezone.utc)
    raise ValueError("Unsupported field type")


def normalize(table, row):
    if not isinstance(row.get("$id"), str) or not row["$id"]:
        raise ValueError("Original document identity is required")
    result = {"id": row["$id"]}
    spec = TABLES[table]
    for field, kind in spec["fields"].items():
        result[field] = convert(row.get(field), kind)
    if any(result[field] is None or result[field] == "" for field in spec["required"]):
        raise ValueError("Missing required source value")
    return result


def comparable(row):
    # Numeric strings preserve Decimal precision; the public contract fixes types.
    return {key: value.isoformat() if isinstance(value, (date, datetime))
            else str(value) if isinstance(value, Decimal) else value
            for key, value in row.items()}


def row_hash(row):
    # Decimal.normalize uses a context that can round very large numbers. Ratios
    # preserve all source digits, including prices and large share counts.
    result = comparable(row)
    for key, value in row.items():
        if isinstance(value, Decimal):
            n, d = value.as_integer_ratio()
            result[key] = [str(n), str(d)]
    return fingerprint(result)


def choose_latest(candidates):
    """Choose actual newest observations; fail on conflicting equal-time prices."""
    latest = {}
    for row, origin in candidates:
        candidate = normalize("latest_prices", dict(row, origin_collection=origin))
        name = candidate["c_name"]
        previous = latest.get(name)
        if previous is None or candidate["date"] > previous["date"]:
            latest[name] = candidate
        elif candidate["date"] == previous["date"]:
            if candidate["pa"] != previous["pa"]:
                raise ValueError("Conflicting equal-time quote prices require reconciliation")
            # Stable IDs make repeat runs independent of input ordering.
            if (candidate["origin_collection"], candidate["id"]) < (previous["origin_collection"], previous["id"]):
                latest[name] = candidate
    return list(latest.values())


def prepare(recovery):
    selected = datasets(recovery, None)
    counts = [verify(dataset) for dataset in selected]
    by_collection = {dataset.collection: dataset for dataset in selected}
    prepared = {}
    for table in TABLES:
        if table == "latest_prices":
            continue
        prepared[table] = [normalize(table, row) for row in records(by_collection[table])]
    def quote_candidates():
        for collection in ("latest_prices", "data"):
            for row in records(by_collection[collection]):
                yield row, collection
    prepared["latest_prices"] = choose_latest(quote_candidates())
    for table, rows in prepared.items():
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate normalized IDs")
    names = {row["name"] for row in prepared["company"]}
    observations = prepared["data"]
    company_days = Counter((row["c_name"], row["date"].date()) for row in observations)
    report = {"tables": {table: len(rows) for table, rows in prepared.items()},
              "records": sum(len(rows) for rows in prepared.values()),
              "history_names_without_company": len({r["c_name"] for r in observations} - names),
              "company_days": len(company_days),
              "company_days_with_multiple_observations": sum(n > 1 for n in company_days.values()),
              "quote_oldest_date": min(row["date"] for row in prepared["latest_prices"]).isoformat(),
              "quote_newest_date": max(row["date"] for row in prepared["latest_prices"]).isoformat(),
              "quotes_from_recovered_history": sum(row["origin_collection"] == "data" for row in prepared["latest_prices"]),
              "private_portfolio_included": False, "fresh_source_responses_promoted": False,
              "authoritative_live_snapshot": False}
    return selected, counts, prepared, report


def verify_table(connection, table, expected):
    columns = ["id", *TABLES[table]["fields"]]
    pending = {row["id"]: row_hash(row) for row in expected}
    with connection.cursor(name="market_verify_" + table) as cursor:
        cursor.itersize = 1000
        cursor.execute(sql.SQL("SELECT {} FROM public.{}").format(
            sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table)))
        for values in cursor:
            row = dict(zip(columns, values))
            if pending.pop(row["id"], None) != row_hash(row):
                raise ValueError("Public table differs from recovery candidate")
    if pending:
        raise ValueError("Public table is missing candidate rows")


def apply(config, selected, counts, prepared):
    with psycopg.connect(**connection_options(config)) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS is required")
        connection.execute("SET LOCAL statement_timeout = '300s'")
        connection.execute("SET LOCAL lock_timeout = '10s'")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        # One transaction covers DDL, all tables, payload reconciliation and ACLs.
        connection.execute("SELECT pg_advisory_xact_lock(182736451,2)")
        before = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        if before > MAX_BYTES:
            raise ValueError("Database exceeds pilot headroom target")
        for dataset, count in zip(selected, counts):
            result = connection.execute("""SELECT source_sha256,source_bytes,row_count
                FROM migration_stage.datasets WHERE dataset_id=%s""", (dataset.identifier,)).fetchone()
            if result != (dataset.expected_hash, dataset.expected_bytes, count):
                raise ValueError("Expected private staging dataset is missing or changed")
        for table in TABLES:
            existing = connection.execute("""SELECT obj_description(c.oid,'pg_class')
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=%s""", (table,)).fetchone()
            if existing is not None and existing != (MARKER,):
                raise ValueError("Refusing to change a table not owned by this migration")
        connection.execute((ROOT / "migrations/supabase/002_public_market.sql").read_text(), prepare=False)
        results = []
        for table, rows in prepared.items():
            count = connection.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))).fetchone()[0]
            status = "already_verified"
            if count == 0:
                columns = ["id", *TABLES[table]["fields"]]
                with connection.cursor() as cursor:
                    with cursor.copy(sql.SQL("COPY public.{} ({}) FROM STDIN").format(
                            sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)))) as copy:
                        for row in rows:
                            copy.write_row([row[key] for key in columns])
                status = "imported"
            verify_table(connection, table, rows)
            results.append({"table": table, "records": len(rows), "status": status,
                            "all_typed_values_match": True})
            print(json.dumps(results[-1]), flush=True)
        for dataset in selected:
            verify(dataset)  # Detect local changes while building/importing.
        for table in TABLES:
            for role in ("anon", "authenticated"):
                privileges = connection.execute("""SELECT
                    has_table_privilege(%s,%s,'SELECT'),
                    has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')""",
                    (role, "public." + table, role, "public." + table)).fetchone()
                if privileges != (role != "anon", False):
                    raise ValueError("Unexpected public table privileges")
            security = connection.execute("""SELECT c.relrowsecurity,
                (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=%s""", (table,)).fetchone()
            if security != (True, 1):
                raise ValueError("Unexpected public row-security policies")
        after = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        if after > MAX_BYTES:
            raise ValueError("Import exceeds pilot headroom target")
        connection.execute("NOTIFY pgrst,'reload schema'")
    return {"database_bytes_before": before, "database_bytes_after": after,
            "authenticated_market_read_only": True, "anonymous_access_denied": True, "tables": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery", type=Path,
                        default=ROOT / "backup_live_recovery_20261022")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        selected, counts, prepared, report = prepare(args.recovery)
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["mode"] = "apply" if args.apply else "local_validation"
        report["contract_sha256"] = hashlib.sha256(json.dumps(CONTRACT, sort_keys=True).encode()).hexdigest()
        if args.apply:
            report["target"] = apply(local_config(ROOT / ".supabase-migration.env"), selected, counts, prepared)
        filename = "supabase_market_import_report.json" if args.apply else "supabase_market_validation_report.json"
        (args.recovery / filename).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_category": type(error).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
