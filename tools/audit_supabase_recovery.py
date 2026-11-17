#!/usr/bin/env python3
"""Reconcile restored application data with verified Appwrite recovery files.

Read-only repeatable-read SQL; never calls Appwrite, imports portfolios, changes
prices or prints credentials/document payloads. Counts describe saved recovery,
not the inaccessible live Appwrite database. Detailed public coverage is saved
only in the ignored recovery directory.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os

import psycopg
from psycopg import sql

from migrate_supabase_market import TABLES, prepare, row_hash
from stage_supabase import ROOT, connection_options, datasets, local_config, sha256, verify


def compare_rows(expected, actual):
    pending = {row["id"]: row_hash(row) for row in expected}
    if len(pending) != len(expected):
        raise ValueError("Duplicate expected identities")
    matched = changed = extra = count = 0
    for row in actual:
        count += 1
        previous = pending.pop(row["id"], None)
        if previous is None:
            extra += 1
        elif previous == row_hash(row):
            matched += 1
        else:
            changed += 1
    return {"expected_rows": len(expected), "actual_rows": count,
            "matching_rows": matched, "changed_rows": changed,
            "missing_rows": len(pending), "extra_rows": extra,
            "all_typed_values_match": changed == extra == len(pending) == 0}


def table_rows(connection, table):
    fields = ["id", *TABLES[table]["fields"]]
    with connection.cursor(name="recovery_audit_" + table) as cursor:
        cursor.itersize = 1000
        cursor.execute(sql.SQL("SELECT {} FROM public.{}").format(
            sql.SQL(",").join(map(sql.Identifier, fields)), sql.Identifier(table)))
        for row in cursor:
            yield dict(zip(fields, row))


def compare_daily_reference(prepared, reference_rows):
    """Find evidenced daily gaps; differences are not automatically corrections.

    A recovered day's latest capture can be intraday and the independent bar can
    be adjusted. Neither timestamp nor financial ratios are invented here.
    """
    symbols = {row["name"]: row["symbol"] for row in prepared["format"]}
    latest = {}
    for row in prepared["data"]:
        symbol = symbols.get(row["c_name"])
        if symbol is None:
            continue
        key = (symbol, row["date"].date().isoformat())
        previous = latest.get(key)
        if previous is None or (row["date"], row["id"]) > (previous["date"], previous["id"]):
            latest[key] = row
    seen = set()
    result = {"reference_rows": 0, "overlapping_company_days": 0,
              "missing_company_days": 0, "exact_last_capture_price_matches": 0,
              "different_last_capture_prices": 0, "unmapped_symbols": 0,
              "invalid_reference_prices": 0, "rows_imported": 0}
    for row in reference_rows:
        day = str(row["date"])[:10]
        key = (row["symbol"], day)
        if key in seen:
            raise ValueError("Independent history has duplicate symbol/day rows")
        seen.add(key)
        result["reference_rows"] += 1
        price = Decimal(str(row["close"]))
        if not price.is_finite() or price <= 0:
            result["invalid_reference_prices"] += 1
            continue
        if row["symbol"] not in symbols.values():
            result["unmapped_symbols"] += 1
            continue
        original = latest.get(key)
        if original is None:
            result["missing_company_days"] += 1
        else:
            result["overlapping_company_days"] += 1
            if original["pa"] == price:
                result["exact_last_capture_price_matches"] += 1
            else:
                result["different_last_capture_prices"] += 1
    return result


def check(config, recovery):
    _, _, prepared, summary = prepare(recovery)
    selected = datasets(recovery, ROOT / "backup_live_public_20261022")
    source_counts = [verify(dataset) for dataset in selected]
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "read_only": True, "appwrite_contacted": False,
              "comparison_scope": "verified_saved_recovery_not_current_Appwrite",
              "tables": [], "private_portfolio_restore_requested": False}
    with psycopg.connect(**connection_options(config)) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS is required")
        connection.execute("SET LOCAL statement_timeout='300s'")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        for table, rows in prepared.items():
            result = {"table": table, **compare_rows(rows, table_rows(connection, table))}
            report["tables"].append(result)
            print(json.dumps(result), flush=True)
        for dataset, count in zip(selected, source_counts):
            result = connection.execute("""SELECT source_sha256,source_bytes,row_count,
                (SELECT count(*) FROM migration_stage.documents d WHERE d.dataset_id=s.dataset_id)
                FROM migration_stage.datasets s WHERE dataset_id=%s""", (dataset.identifier,)).fetchone()
            if result != (dataset.expected_hash, dataset.expected_bytes, count, count):
                raise ValueError("Staging inventory differs from verified sources")
        report["staging"] = {"expected_datasets_present": len(selected),
                             "records": sum(source_counts), "metadata_and_counts_match": True,
                             "original_payloads_previously_fully_verified": True,
                             "full_staging_payload_readback_repeated": False}
        report["history"] = dict(zip(
            ("observations", "series", "first_observation_utc", "last_observation_utc",
             "invalid_prices", "null_per", "negative_per"),
            connection.execute("""SELECT count(*),count(DISTINCT c_name),min(date),max(date),
                count(*) FILTER (WHERE pa IS NULL OR pa<=0),
                count(*) FILTER (WHERE per IS NULL),count(*) FILTER (WHERE per<0)
                FROM public.data""").fetchone()))
        coverage = connection.execute("""SELECT f.symbol,c.name,count(d.id),min(d.date),max(d.date)
            FROM public.company c LEFT JOIN public.format f ON f.name=c.name
            LEFT JOIN public.data d ON d.c_name=c.name
            GROUP BY f.symbol,c.name ORDER BY c.name""").fetchall()
        report["directory"] = {
            "companies": len(coverage),
            "companies_with_symbols": sum(row[0] is not None for row in coverage),
            "companies_with_history": sum(row[2] > 0 for row in coverage),
            "history_series_without_company": connection.execute("""SELECT count(DISTINCT d.c_name)
                FROM public.data d WHERE NOT EXISTS(SELECT 1 FROM public.company c WHERE c.name=d.c_name)""").fetchone()[0],
        }
        dividends = connection.execute("""SELECT year,count(*),count(*) FILTER(WHERE confirmed),
            count(*) FILTER(WHERE amount IS NULL) FROM public.dividends GROUP BY year ORDER BY year""").fetchall()
        report["dividends_by_payment_year"] = [dict(zip(
            ("year", "rows", "confirmed", "amount_unknown"), row)) for row in dividends]
        report["fundamentals"] = dict(zip(
            ("companies", "bpa_present", "roe_present", "shares_present", "equity_present",
             "growth_present", "dividend_per_share_present", "fiscal_year_present",
             "company_date_min_utc", "company_date_max_utc"),
            connection.execute("""SELECT count(*),count(bpa),count(roe),count(na),count(cp),
                count(tc5),count(dpa),count(fiscal_year),min(date),max(date) FROM public.company""").fetchone()))
        report["quotes"] = dict(zip(("rows", "first_observation_utc", "last_observation_utc"),
            connection.execute("SELECT count(*),min(date),max(date) FROM public.latest_prices").fetchone()))
        report["database_bytes"] = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        connection.rollback()
    # Preserve coverage details privately; no account IDs or portfolio data.
    coverage_report = [dict(zip(("symbol", "company", "history_rows", "first_utc", "last_utc"), row))
                       for row in coverage]
    (recovery / "supabase_company_coverage.json").write_text(json.dumps(coverage_report, default=str, indent=2) + "\n")
    baseline = json.loads((recovery / "baseline/manifest.json").read_text())
    report["saved_collection_inventory"] = [{"collection": name, "saved_rows": entry["documents"],
        "application_state": "restored_public" if name in TABLES
        else "fresh_account_reset_kept_in_local_backup" if name in {"achats", "ventes", "portefeuille", "benefits"}
        else "diagnostic_log_kept_in_local_backup"}
        for name, entry in baseline["collections"].items()]
    report["app_rows_verified"] = sum(row["matching_rows"] for row in report["tables"])
    report["recovered_company_days"] = summary["company_days"]
    reference = recovery / "independent_daily_history.parquet"
    manifest = json.loads((recovery / "manifest.json").read_text())
    evidence = next((entry for entry in manifest["files"] if entry["path"] == reference.name), None)
    if evidence is not None:
        if reference.stat().st_size != evidence["bytes"] or sha256(reference) != evidence["sha256"]:
            raise ValueError("Independent history changed from its verified manifest")
        import pyarrow.parquet as parquet
        reference_rows = parquet.read_table(reference, columns=["date", "symbol", "close"]).to_pylist()
        report["independent_history_comparison"] = compare_daily_reference(prepared, reference_rows)
    else:
        report["independent_history_comparison"] = {"status": "not_in_verified_manifest", "rows_imported": 0}
    report["ok"] = all(row["all_typed_values_match"] for row in report["tables"])
    report["current_cloud_snapshot_recreated"] = False
    (recovery / "supabase_recovery_audit.json").write_text(json.dumps(report, default=str, indent=2) + "\n")
    return report


if __name__ == "__main__":
    os.umask(0o077)
    try:
        report = check(local_config(ROOT / ".supabase-migration.env"), ROOT / "backup_live_recovery_20261022")
        print(json.dumps(report, default=str), flush=True)
        raise SystemExit(0 if report["ok"] else 1)
    except Exception as error:
        print(json.dumps({"ok": False, "error_category": type(error).__name__}), flush=True)
        raise SystemExit(1)
