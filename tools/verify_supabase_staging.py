#!/usr/bin/env python3
"""Read back staging payloads and privileges without emitting data or secrets."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import psycopg

from stage_supabase import (
    ROOT, connection_options, datasets, local_config, record_id, records, verify,
)


def normalized(value):
    """Ignore JSON object order and equivalent PostgreSQL numeric formatting.

    Tag every type so booleans and strings cannot compare equal to numbers.
    Decimal ratios avoid precision loss for large integers and decimal prices.
    """
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, (int, float)):
        numerator, denominator = Decimal(str(value)).as_integer_ratio()
        return ["number", str(numerator), str(denominator)]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, list):
        return ["array", [normalized(item) for item in value]]
    if isinstance(value, dict):
        return ["object", [[key, normalized(value[key])] for key in sorted(value)]]
    raise ValueError("Unsupported JSON value")


def fingerprint(payload):
    canonical = json.dumps(normalized(payload), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).digest()


def compare_payloads(dataset, remote_rows):
    expected = {record_id(dataset, row): fingerprint(row) for row in records(dataset)}
    count = 0
    for identifier, payload in remote_rows:
        expected_hash = expected.pop(identifier, None)
        if expected_hash is None or fingerprint(payload) != expected_hash:
            raise ValueError("Remote payload differs from verified source")
        count += 1
    if expected:
        raise ValueError("Remote dataset is missing source documents")
    return count


def check(config, selected):
    counts = [verify(dataset) for dataset in selected]
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "read_only": True, "datasets": []}
    with psycopg.connect(**connection_options(config)) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS is required")
        connection.execute("SET LOCAL statement_timeout = '300s'")
        for index, (dataset, expected_count) in enumerate(zip(selected, counts)):
            metadata = connection.execute("""
                SELECT source_sha256,source_bytes,row_count FROM migration_stage.datasets
                WHERE dataset_id=%s
            """, (dataset.identifier,)).fetchone()
            if metadata != (dataset.expected_hash, dataset.expected_bytes, expected_count):
                raise ValueError("Remote dataset metadata differs from source")
            with connection.cursor(name=f"verify_dataset_{index}") as cursor:
                cursor.itersize = 1000
                cursor.execute("""
                    SELECT document_id,payload FROM migration_stage.documents
                    WHERE dataset_id=%s
                """, (dataset.identifier,))
                actual = compare_payloads(dataset, cursor)
            if actual != expected_count:
                raise ValueError("Remote record count differs from source")
            report["datasets"].append({"dataset": dataset.name, "records": actual,
                                       "all_payloads_match": True})
            print(json.dumps(report["datasets"][-1]), flush=True)
        roles = connection.execute("""
            SELECT role_name,
                   has_schema_privilege(role_name,'migration_stage','USAGE'),
                   has_table_privilege(role_name,'migration_stage.datasets',
                                       'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
                   has_table_privilege(role_name,'migration_stage.documents',
                                       'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            FROM unnest(ARRAY['anon','authenticated','service_role']) AS roles(role_name)
        """).fetchall()
        if len(roles) != 3 or any(any(row[1:]) for row in roles):
            raise ValueError("Application roles have staging privileges")
        tables = connection.execute("""
            SELECT c.relname,c.relrowsecurity,
                   (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid),
                   pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='migration_stage' AND c.relkind='r'
        """).fetchall()
        if ({row[0] for row in tables} != {"datasets", "documents"}
                or any(not row[1] or row[2] != 0 for row in tables)):
            raise ValueError("Unexpected staging tables or row-security configuration")
        report["database_bytes"] = connection.execute(
            "SELECT pg_database_size(current_database())").fetchone()[0]
        report["staging_bytes_including_indexes"] = sum(row[3] for row in tables)
        report["application_roles_have_staging_access"] = False
        report["row_security_enabled_without_policies"] = True
        report["records_verified"] = sum(counts)
        report["ok"] = True
        connection.rollback()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery", type=Path, default=ROOT / "backup_live_recovery_20261022")
    parser.add_argument("--public", type=Path, default=ROOT / "backup_live_public_20261022")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".supabase-migration.env")
    parser.add_argument("--include-private", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        selected = datasets(args.recovery, args.public, args.include_private)
        report = check(local_config(args.env_file), selected)
        (args.recovery / "supabase_verification_report.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        return 0
    except Exception as error:
        # Do not print remote payloads, exception text, or connection options.
        print(json.dumps({"ok": False, "error_category": type(error).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
