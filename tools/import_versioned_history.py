#!/usr/bin/env python3
"""Verify and append retrospective source history into a private SQL archive.

No source HTTP, model execution, original market-table updates or API grants.
Native field bindings are supplied in a private file, never hardcoded here.
Prepare is local-only; verify uses TLS READ ONLY; apply is an explicit opt-in.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pyarrow.parquet as pq

from stage_supabase import ROOT, connection_options, local_config
from verify_supabase_staging import fingerprint

CONTRACT = "private-source-history-v1"
SCHEMA = ROOT / "migrations/supabase/006_versioned_history.sql"
TABLES = ("batches", "captures", "observations")
MAX_BYTES = 350_000_000  # Internal conservative budget, NOT a service plan limit.


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_json(raw):
    def invalid(_):
        raise ValueError("Nonfinite JSON")

    return json.loads(raw, parse_constant=invalid)


def require(condition):
    if not condition:
        raise ValueError("History integrity check failed")


def number(value):
    require(not isinstance(value, bool) and value is not None)
    result = Decimal(str(value))
    require(result.is_finite())
    return result


def instant(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None)
    return parsed.astimezone(timezone.utc)


def raw_rows(raw, bindings):
    value = read_json(raw)
    for component in bindings["rows_path"]:
        value = value[component]
    require(isinstance(value, list) and all(isinstance(r, dict) for r in value))
    return value


def native_projection(row, bindings):
    source_label = row[bindings["date_field"]]
    parsed = datetime.strptime(source_label, bindings["date_format"])
    require(parsed.time().isoformat() == "00:00:00")
    close = number(row[bindings["close_field"]])
    require(close > 0)
    warnings = []
    try:
        high = number(row[bindings["high_field"]])
        low = number(row[bindings["low_field"]])
        if high < low or not low <= close <= high:
            warnings.append("SOURCE_OHLC_INCONSISTENT")
    except (ValueError, KeyError, ArithmeticError):
        warnings.append("SOURCE_OHLC_UNAVAILABLE")
    return parsed.date().isoformat(), source_label, str(close), warnings


def artifact(connection, identity):
    require(re.fullmatch("[a-f0-9]{64}", identity) is not None)
    result = connection.execute(
        "SELECT body FROM artifacts WHERE sha=?", (identity,)
    ).fetchone()
    require(result is not None and digest(result[0]) == identity)
    return result[0]


def prepare(report_path, index_path, parquet_path, store_path, bindings_path):
    """Bind every normalized row to an exact immutable raw response and ordinal."""
    report_raw, index_raw, bindings_raw = (
        p.read_bytes() for p in (report_path, index_path, bindings_path)
    )
    report, index, bindings = map(read_json, (report_raw, index_raw, bindings_raw))
    require(report["contract"] == "provider-daily-history-recovery-v2")
    require(report["classification"] == "RETROSPECTIVE_SOURCE_HISTORY")
    require(not report["failed_instruments"])
    parquet_hash = digest(parquet_path.read_bytes())
    require(parquet_hash == report["parquet_sha256"])
    projected = pq.read_table(parquet_path).to_pylist()
    require(len(projected) == report["source_rows"])
    groups = defaultdict(list)
    for row in projected:
        groups[row["symbol"]].append(row)
    require(set(groups) == set(index) and len(index) == report["expected_instruments"])
    providers = {r["provider"] for r in projected}
    namespaces = {r["namespace"] for r in projected}
    require(len(providers) == len(namespaces) == 1)
    namespace = next(iter(namespaces))
    captures, rows = [], []
    connection = sqlite3.connect(store_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for symbol in sorted(index):
            entry = index[symbol]
            raw, request, receipt = (
                artifact(connection, entry[k])
                for k in ("raw_sha256", "request_sha256", "receipt_sha256")
            )
            meta = read_json(receipt)
            require(
                meta["sha256"] == digest(raw)
                and meta["request_sha256"] == digest(request)
            )
            require(meta["completed_at"] == entry["capture_completed_at"])
            require(meta["kind"] == "HTTP_CAPTURED_NOW")
            instant(meta["completed_at"])
            originals = raw_rows(raw, bindings)
            require(len(originals) == entry["source_rows"] == len(groups[symbol]))
            by_ordinal = {r["source_ordinal"]: r for r in groups[symbol]}
            require(set(by_ordinal) == set(range(len(originals))))
            for ordinal, original in enumerate(originals):
                row = by_ordinal[ordinal]
                day, label, close, warnings = native_projection(original, bindings)
                identity = digest(canonical([namespace, symbol, digest(raw), ordinal]))
                require(row["record_identity"] == identity)
                require(read_json(row["raw_row_json"]) == original)
                require(row["market_date"] == day and row["source_daily_date"] == label)
                require(
                    row["close_decimal"] == close and row["raw_sha256"] == digest(raw)
                )
                require(row["capture_completed_at"] == meta["completed_at"])
                require(
                    row["observed_at"] is None
                    and row["observation_time_status"] == "UNKNOWN"
                )
                require(row["price_definition"] == "PROVIDER_DAILY_CLOSE_CANDIDATE")
                require(
                    row["quantity"] is None
                    and read_json(row["quality_warnings"]) == warnings
                )
                for field in ("close", "open", "high", "low", "volume_mad"):
                    key = bindings[field + "_field"]
                    if row[field] is None:
                        require(
                            field != "close"
                            and original[key]
                            in bindings.get("nullable_source_values", {}).get(
                                field, [None]
                            )
                        )
                    else:
                        require(number(row[field]) == number(original[key]))
                require(date.fromisoformat(day) <= instant(meta["completed_at"]).date())
                rows.append(
                    [symbol, ordinal, identity, day, label, close, original, warnings]
                )
            captures.append(
                [
                    symbol,
                    meta["completed_at"],
                    digest(raw),
                    digest(request),
                    digest(receipt),
                    *[
                        base64.b64encode(gzip.compress(v, mtime=0)).decode()
                        for v in (raw, request, receipt)
                    ],
                ]
            )
    finally:
        connection.close()
    manifest = {
        "contract": CONTRACT,
        "classification": "RETROSPECTIVE_SOURCE_HISTORY",
        "provider": next(iter(providers)),
        "namespace": namespace,
        "parquet_sha256": parquet_hash,
        "capture_index_sha256": digest(index_raw),
        "recovery_report_sha256": digest(report_raw),
        "bindings": bindings,
        "bindings_sha256": digest(bindings_raw),
        "schema_sha256": digest(SCHEMA.read_bytes()),
        "rows_sha256": digest(canonical(rows)),
        "captures_sha256": digest(canonical(captures)),
        "row_count": len(rows),
        "capture_count": len(captures),
        "original_observation_times": "UNKNOWN",
        "production_eligible": False,
    }
    bundle = {
        "manifest": manifest,
        "batch_id": digest(canonical(manifest)),
        "captures": captures,
        "rows": rows,
    }
    require(digest(parquet_path.read_bytes()) == parquet_hash)
    validate(bundle)
    return bundle


def validate(bundle):
    m = bundle["manifest"]
    require(
        m["contract"] == CONTRACT
        and m["classification"] == "RETROSPECTIVE_SOURCE_HISTORY"
    )
    require(
        m["original_observation_times"] == "UNKNOWN"
        and m["production_eligible"] is False
    )
    require(m["schema_sha256"] == digest(SCHEMA.read_bytes()))
    require(bundle["batch_id"] == digest(canonical(m)))
    require(digest(canonical(bundle["rows"])) == m["rows_sha256"])
    require(digest(canonical(bundle["captures"])) == m["captures_sha256"])
    require(
        len(bundle["rows"]) == m["row_count"]
        and len(bundle["captures"]) == m["capture_count"]
    )
    expected, seen = {}, set()
    for symbol, completed, raw_hash, request_hash, receipt_hash, *compressed in bundle[
        "captures"
    ]:
        require(symbol not in seen and len(compressed) == 3)
        seen.add(symbol)
        raw, request, receipt = [
            gzip.decompress(base64.b64decode(v, validate=True)) for v in compressed
        ]
        require(
            [digest(v) for v in (raw, request, receipt)]
            == [raw_hash, request_hash, receipt_hash]
        )
        meta = read_json(receipt)
        require(meta["sha256"] == raw_hash and meta["request_sha256"] == request_hash)
        require(
            meta["completed_at"] == completed and meta["kind"] == "HTTP_CAPTURED_NOW"
        )
        for ordinal, bar in enumerate(raw_rows(raw, m["bindings"])):
            day, label, close, warnings = native_projection(bar, m["bindings"])
            require(date.fromisoformat(day) <= instant(completed).date())
            identity = digest(canonical([m["namespace"], symbol, raw_hash, ordinal]))
            expected[(symbol, ordinal)] = [
                symbol,
                ordinal,
                identity,
                day,
                label,
                close,
                bar,
                warnings,
            ]
    identities = set()
    for row in bundle["rows"]:
        require(expected.pop((row[0], row[1]), None) == row)
        require(row[2] not in identities)
        identities.add(row[2])
    require(not expected)


def summary(bundle):
    keys, closes = Counter(), defaultdict(set)
    for row in bundle["rows"]:
        key = row[0], row[3]
        keys[key] += 1
        closes[key].add(number(row[5]))
    # Conservative planning estimate: expanded JSON + large per-row/index allowance.
    # The actual database-size guard is also checked inside the atomic transaction.
    estimated = sum(len(canonical(r)) + 768 for r in bundle["rows"])
    estimated += (
        sum(
            sum(len(base64.b64decode(v)) for v in c[5:]) + 4096
            for c in bundle["captures"]
        )
        + 2_000_000
    )
    return {
        "batch_id": bundle["batch_id"],
        "rows": len(bundle["rows"]),
        "captures": len(bundle["captures"]),
        "duplicate_economic_keys": sum(n > 1 for n in keys.values()),
        "conflicting_close_keys": sum(len(v) > 1 for v in closes.values()),
        "economic_date_first": min(r[3] for r in bundle["rows"]),
        "economic_date_last": max(r[3] for r in bundle["rows"]),
        "estimated_added_database_bytes": estimated,
        "internal_database_budget_bytes": MAX_BYTES,
        "service_plan_limit_verified": False,
        "original_observation_times": "UNKNOWN",
        "application_access_enabled": False,
    }


def privileges(db):
    tables = db.execute("""SELECT c.relname,c.relrowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='market_history_v1' AND c.relkind='r'""").fetchall()
    require({row[0] for row in tables} == set(TABLES) and all(row[1] for row in tables))
    require(
        db.execute("""SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='market_history_v1'""").fetchone()[
            0
        ]
        == 0
    )
    for role in ("anon", "authenticated", "service_role"):
        require(
            not db.execute(
                "SELECT has_schema_privilege(%s,'market_history_v1','USAGE')", (role,)
            ).fetchone()[0]
        )
        for table in TABLES:
            require(
                not db.execute(
                    "SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
                    (role, "market_history_v1." + table),
                ).fetchone()[0]
            )


def verify_remote(db, bundle):
    """Read back every source byte and typed projection; fail on extra/missing rows."""
    batch = bundle["batch_id"]
    require(
        db.execute(
            "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s", (batch,)
        ).fetchone()
        == (bundle["manifest"],)
    )
    captures = {c[0]: c for c in bundle["captures"]}
    for values in db.execute(
        "SELECT symbol,completed_at,raw_sha256,request_sha256,receipt_sha256,raw_gzip,request_gzip,receipt_gzip FROM market_history_v1.captures WHERE batch_id=%s",
        (batch,),
    ):
        expected = captures.pop(values[0], None)
        require(expected is not None and values[1] == instant(expected[1]))
        require(list(values[2:5]) == expected[2:5])
        for actual, encoded in zip(values[5:], expected[5:]):
            require(bytes(actual) == base64.b64decode(encoded))
    require(not captures)
    rows = {(r[0], r[1]): r for r in bundle["rows"]}
    with db.cursor(name="verify_versioned_history") as cur:
        cur.itersize = 1000
        cur.execute(
            "SELECT symbol,source_ordinal,observation_id,period_day,source_daily_label,close_text,bar,quality_warnings,observed_at,observation_time_status,price_definition FROM market_history_v1.observations WHERE batch_id=%s",
            (batch,),
        )
        for actual in cur:
            expected = rows.pop((actual[0], actual[1]), None)
            require(expected is not None)
            require(
                list(actual[:3]) == expected[:3]
                and actual[3].isoformat() == expected[3]
            )
            require(
                list(actual[4:6]) == expected[4:6]
                and fingerprint(actual[6]) == fingerprint(expected[6])
            )
            require(
                actual[7] == expected[7]
                and actual[8:] == (None, "UNKNOWN", "PROVIDER_DAILY_CLOSE_CANDIDATE")
            )
    require(not rows)
    privileges(db)
    return {
        "rows_verified": len(bundle["rows"]),
        "captures_verified": len(bundle["captures"]),
        "all_values_and_raw_bytes_match": True,
        "application_roles_have_access": False,
    }


def public_fingerprints(db):
    """Check all existing public-table contents without returning any payloads."""
    tables = db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ).fetchall()
    return {
        name: db.execute(
            sql.SQL(
                "SELECT count(*),md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(t)::text) h FROM public.{} t) hashes"
            ).format(sql.Identifier(name))
        ).fetchone()
        for (name,) in tables
    }


def connect(config):
    db = psycopg.connect(**connection_options(config))
    if not db.pgconn.ssl_in_use:
        db.close()
        raise ValueError("TLS is required")
    return db


def remote(bundle, config, apply=False, max_bytes=MAX_BYTES):
    validate(bundle)
    plan = summary(bundle)
    with connect(config) as db:
        db.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            + ("" if apply else ", READ ONLY")
        )
        before = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        exists = db.execute(
            "SELECT to_regnamespace('market_history_v1') IS NOT NULL"
        ).fetchone()[0]
        report = {
            "read_only": not apply,
            "database_bytes_before": before,
            "tls_active": bool(db.pgconn.ssl_in_use),
        }
        if not apply:
            report["schema_exists"] = exists
            report["estimated_capacity_ok"] = (
                before + plan["estimated_added_database_bytes"] <= max_bytes
            )
            if exists:
                privileges(db)
                report["batch_present"] = (
                    db.execute(
                        "SELECT 1 FROM market_history_v1.batches WHERE batch_id=%s",
                        (bundle["batch_id"],),
                    ).fetchone()
                    is not None
                )
                if report["batch_present"]:
                    report["verification"] = verify_remote(db, bundle)
            db.rollback()
            return report
        require(before < max_bytes)
        db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('private-source-history-v1',0))"
        )
        before_public = public_fingerprints(db)
        if not exists:
            require(before + plan["estimated_added_database_bytes"] <= max_bytes)
            db.execute(SCHEMA.read_text(), prepare=False)
        previous = db.execute(
            "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s",
            (bundle["batch_id"],),
        ).fetchone()
        if previous is None:
            require(before + plan["estimated_added_database_bytes"] <= max_bytes)
            privileges(db)
            db.execute(
                "INSERT INTO market_history_v1.batches(batch_id,manifest) VALUES(%s,%s)",
                (bundle["batch_id"], Jsonb(bundle["manifest"])),
            )
            with db.cursor().copy(
                "COPY market_history_v1.captures(batch_id,symbol,completed_at,raw_sha256,request_sha256,receipt_sha256,raw_gzip,request_gzip,receipt_gzip) FROM STDIN"
            ) as copy:
                for c in bundle["captures"]:
                    copy.write_row(
                        (
                            bundle["batch_id"],
                            c[0],
                            instant(c[1]),
                            *c[2:5],
                            *[base64.b64decode(v) for v in c[5:]],
                        )
                    )
            with db.cursor().copy(
                "COPY market_history_v1.observations(batch_id,symbol,source_ordinal,observation_id,period_day,source_daily_label,close_text,bar,quality_warnings) FROM STDIN"
            ) as copy:
                for r in bundle["rows"]:
                    copy.write_row(
                        (
                            bundle["batch_id"],
                            *r[:3],
                            date.fromisoformat(r[3]),
                            *r[4:6],
                            Jsonb(r[6]),
                            r[7],
                        )
                    )
            report["status"] = "APPENDED"
        else:
            require(previous == (bundle["manifest"],))
            report["status"] = "ALREADY_PRESENT_VERIFIED"
        report["verification"] = verify_remote(db, bundle)
        require(public_fingerprints(db) == before_public)
        report["public_table_contents_unchanged"] = True
        after = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        require(after <= max_bytes)
        report["database_bytes_after"] = after
        # Context manager commits only after all readback, privilege and size gates.
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "apply"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--recovery-report", type=Path)
    parser.add_argument("--capture-index", type=Path)
    parser.add_argument("--parquet", type=Path)
    parser.add_argument("--capture-store", type=Path)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".supabase-migration.env"
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        # Reserve no remote work when a receipt could not be saved safely.
        require(not args.report.exists() and not args.report.is_symlink())
        require(args.report.parent.is_dir())
        if args.mode == "prepare":
            require(
                all(
                    (
                        args.recovery_report,
                        args.capture_index,
                        args.parquet,
                        args.capture_store,
                        args.bindings,
                    )
                )
            )
            bundle = prepare(
                args.recovery_report,
                args.capture_index,
                args.parquet,
                args.capture_store,
                args.bindings,
            )
            encoded = gzip.compress(canonical(bundle), mtime=0)
            if args.bundle.exists():
                require(args.bundle.read_bytes() == encoded)
            else:
                with args.bundle.open("xb") as stream:
                    stream.write(encoded)
        else:
            bundle = read_json(gzip.decompress(args.bundle.read_bytes()))
            validate(bundle)
        result = {
            "ok": True,
            "mode": args.mode,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "bundle_sha256": digest(args.bundle.read_bytes()),
            **summary(bundle),
        }
        if args.mode != "prepare":
            result["remote"] = remote(
                bundle, local_config(args.env_file), apply=args.mode == "apply"
            )
        # Receipts are append-only too: refuse to overwrite earlier results.
        with args.report.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        return 0
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error_category": type(exc).__name__}), flush=True
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
