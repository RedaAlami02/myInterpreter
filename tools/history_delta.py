#!/usr/bin/env python3
"""Versioned, append-only economic-value deltas with full raw source evidence.

The v1 archive contract remains unchanged. A v2 manifest explicitly distinguishes
complete raw source observations from the smaller normalized delta projection.
No source identity is inferred from a symbol/date pair or silently discarded.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re

from psycopg.types.json import Jsonb

import import_versioned_history as v1
from verify_supabase_staging import fingerprint

CONTRACT = "private-source-history-delta-v2"
NORMALIZATION = "typed-json-numeric-ratio-v1"


def value_identity(namespace, row):
    """Economic payload identity, NOT a replacement for raw source identity.

    The whole native row is included. Unchanged price with revised volume, OHLC,
    date label or any other source field is still a new economic payload version.
    Raw captures retain every source identity/ordinal and occurrence multiplicity.
    """
    return fingerprint([NORMALIZATION, namespace, row[0], row[6]])


def plan_delta(parent, current, parent_archive_id=None):
    v1.validate(parent)
    v1.validate(current)
    for field in ("provider", "namespace", "bindings", "classification"):
        v1.require(parent["manifest"][field] == current["manifest"][field])
    v1.require(
        {r[0] for r in parent["captures"]} == {r[0] for r in current["captures"]}
    )
    previous_times = {r[0]: v1.instant(r[1]) for r in parent["captures"]}
    v1.require(
        all(v1.instant(r[1]) >= previous_times[r[0]] for r in current["captures"])
    )
    archive_id = parent_archive_id or parent["batch_id"]
    v1.require(re.fullmatch("[a-f0-9]{64}", archive_id) is not None)
    namespace = current["manifest"]["namespace"]
    before = Counter(value_identity(namespace, r) for r in parent["rows"])
    unused = before.copy()
    delta = []
    for row in current["rows"]:
        identity = value_identity(namespace, row)
        if unused[identity]:
            unused[identity] -= 1
        else:
            delta.append(row)
    old_keys, new_keys = defaultdict(Counter), defaultdict(Counter)
    for source, target in ((parent, old_keys), (current, new_keys)):
        for row in source["rows"]:
            target[(row[0], row[3])][value_identity(namespace, row)] += 1
    counts = {
        "source_observations": len(current["rows"]),
        "delta_projection_rows": len(delta),
        "inherited_economic_occurrences": len(current["rows"]) - len(delta),
        "absent_from_current_capture": sum(unused.values()),
        "new_instrument_date_keys": len(new_keys.keys() - old_keys.keys()),
        "changed_existing_instrument_date_keys": sum(
            old_keys[k] != new_keys[k] for k in old_keys.keys() & new_keys.keys()
        ),
    }
    manifest = {
        "contract": CONTRACT,
        "classification": "RETROSPECTIVE_SOURCE_HISTORY",
        "normalization": NORMALIZATION,
        "parent_batch_id": archive_id,
        "parent_full_version_id": parent["batch_id"],
        "full_source_manifest": current["manifest"],
        "delta_rows_sha256": v1.digest(v1.canonical(delta)),
        "counts": counts,
        "original_observation_times": "UNKNOWN",
        "production_eligible": False,
    }
    return {
        "manifest": manifest,
        "batch_id": v1.digest(v1.canonical(manifest)),
        "full_source": current,
        "delta_rows": delta,
    }


def validate_delta(delta, parent):
    expected = plan_delta(
        parent, delta["full_source"], delta["manifest"]["parent_batch_id"]
    )
    v1.require(v1.canonical(delta) == v1.canonical(expected))


def projection(delta):
    return {
        "batch_id": delta["batch_id"],
        "manifest": delta["manifest"],
        "captures": delta["full_source"]["captures"],
        "rows": delta["delta_rows"],
    }


def summary(delta):
    estimated = sum(len(v1.canonical(r)) + 768 for r in delta["delta_rows"])
    estimated += (
        sum(
            sum(len(base64.b64decode(v)) for v in c[5:]) + 4096
            for c in delta["full_source"]["captures"]
        )
        + 2_000_000
    )
    return {
        "batch_id": delta["batch_id"],
        **delta["manifest"]["counts"],
        "raw_captures": len(delta["full_source"]["captures"]),
        "estimated_added_database_bytes": estimated,
        "internal_database_budget_bytes": v1.MAX_BYTES,
        "raw_source_observations_preserved": True,
        "old_observations_deleted": False,
        "production_eligible": False,
    }


def reconstruct_full(manifest, captures):
    rows = []
    namespace = manifest["namespace"]
    for (
        symbol,
        completed,
        raw_hash,
        request_hash,
        receipt_hash,
        raw_zip,
        request_zip,
        receipt_zip,
    ) in captures:
        raw = gzip.decompress(base64.b64decode(raw_zip, validate=True))
        for ordinal, bar in enumerate(v1.raw_rows(raw, manifest["bindings"])):
            day, label, close, warnings = v1.native_projection(
                bar, manifest["bindings"]
            )
            identity = v1.digest(v1.canonical([namespace, symbol, raw_hash, ordinal]))
            rows.append([symbol, ordinal, identity, day, label, close, bar, warnings])
    result = {
        "manifest": manifest,
        "batch_id": v1.digest(v1.canonical(manifest)),
        "captures": captures,
        "rows": rows,
    }
    v1.validate(result)
    return result


def load_archive(db, archive_id):
    """Verify a pinned complete source version, whether v1 or sparse v2.

    Complete source membership comes from exact raw bytes, not a ticker/date join
    or an implicit union across batches. No recursive ancestor-price selection is
    needed: each version archives its complete raw capture set.
    """
    v1.require(re.fullmatch("[a-f0-9]{64}", archive_id) is not None)
    found = db.execute(
        "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s",
        (archive_id,),
    ).fetchone()
    v1.require(found is not None)
    metadata = found[0]
    v1.require(v1.digest(v1.canonical(metadata)) == archive_id)
    contract = metadata.get("contract")
    v1.require(contract in (v1.CONTRACT, CONTRACT))
    full_manifest = (
        metadata if contract == v1.CONTRACT else metadata["full_source_manifest"]
    )
    captures = []
    for row in db.execute(
        """SELECT symbol,completed_at,raw_sha256,request_sha256,
            receipt_sha256,raw_gzip,request_gzip,receipt_gzip
            FROM market_history_v1.captures WHERE batch_id=%s ORDER BY symbol""",
        (archive_id,),
    ):
        # Receipt binds the exact original timezone string, not SQL's display zone.
        receipt = v1.read_json(gzip.decompress(bytes(row[7])))
        v1.require(row[1] == v1.instant(receipt["completed_at"]))
        captures.append(
            [
                row[0],
                receipt["completed_at"],
                *row[2:5],
                *[base64.b64encode(bytes(value)).decode() for value in row[5:]],
            ]
        )
    full = reconstruct_full(full_manifest, captures)
    if contract == v1.CONTRACT:
        v1.require(full["batch_id"] == archive_id)
        materialized = full["rows"]
    else:
        v1.require(
            metadata["classification"] == "RETROSPECTIVE_SOURCE_HISTORY"
            and metadata["normalization"] == NORMALIZATION
            and metadata["production_eligible"] is False
            and metadata["original_observation_times"] == "UNKNOWN"
        )
        parent_record = db.execute(
            "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s",
            (metadata["parent_batch_id"],),
        ).fetchone()
        v1.require(parent_record is not None)
        parent_metadata = parent_record[0]
        v1.require(
            v1.digest(v1.canonical(parent_metadata)) == metadata["parent_batch_id"]
        )
        v1.require(parent_metadata.get("contract") in (v1.CONTRACT, CONTRACT))
        parent_full = (
            parent_metadata
            if parent_metadata["contract"] == v1.CONTRACT
            else parent_metadata["full_source_manifest"]
        )
        v1.require(
            v1.digest(v1.canonical(parent_full)) == metadata["parent_full_version_id"]
        )
        v1.require(
            all(
                parent_full[field] == full_manifest[field]
                for field in ("provider", "namespace", "bindings")
            )
        )
        by_key = {(r[0], r[1]): r for r in full["rows"]}
        keys = db.execute(
            "SELECT symbol,source_ordinal FROM market_history_v1.observations WHERE batch_id=%s ORDER BY symbol,source_ordinal",
            (archive_id,),
        ).fetchall()
        v1.require(all(key in by_key for key in keys))
        materialized = [by_key[key] for key in keys]
        v1.require(len(materialized) == metadata["counts"]["delta_projection_rows"])
        v1.require(len(full["rows"]) == metadata["counts"]["source_observations"])
        v1.require(
            v1.digest(v1.canonical(materialized)) == metadata["delta_rows_sha256"]
        )
    verified = v1.verify_remote(
        db,
        {
            "batch_id": archive_id,
            "manifest": metadata,
            "captures": captures,
            "rows": materialized,
        },
    )
    verified["full_source_observations_verified"] = len(full["rows"])
    return full, verified


def verify_delta(db, delta):
    full, verified = load_archive(db, delta["batch_id"])
    v1.require(v1.canonical(full) == v1.canonical(delta["full_source"]))
    actual = db.execute(
        "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s",
        (delta["batch_id"],),
    ).fetchone()[0]
    v1.require(actual == delta["manifest"])
    # Full, independent comparison of materialized rows against the local plan.
    v1.verify_remote(db, projection(delta))
    return verified


def insert_projection(db, bundle):
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
                    v1.instant(c[1]),
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


def remote(delta, parent, config, *, apply=False, max_bytes=v1.MAX_BYTES):
    validate_delta(delta, parent)
    plan = summary(delta)
    with v1.connect(config) as db:
        db.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            + ("" if apply else ", READ ONLY")
        )
        if apply:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('private-source-history-v1',0))"
            )
        before = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        saved_parent, parent_verification = load_archive(
            db, delta["manifest"]["parent_batch_id"]
        )
        v1.require(v1.canonical(saved_parent) == v1.canonical(parent))
        present = (
            db.execute(
                "SELECT 1 FROM market_history_v1.batches WHERE batch_id=%s",
                (delta["batch_id"],),
            ).fetchone()
            is not None
        )
        report = {
            "read_only": not apply,
            "tls_active": bool(db.pgconn.ssl_in_use),
            "database_bytes_before": before,
            "batch_present": present,
            "parent_verification": parent_verification,
            "estimated_capacity_ok": before
            + (0 if present else plan["estimated_added_database_bytes"])
            <= max_bytes,
        }
        if present:
            report["verification"] = verify_delta(db, delta)
            report["status"] = "ALREADY_PRESENT_VERIFIED"
        elif not apply:
            report["status"] = "READ_ONLY_PLAN_VERIFIED"
        elif not delta["delta_rows"]:
            # Additional capture receipts remain in the isolated acquisition store.
            report["status"] = "NO_ECONOMIC_PAYLOAD_CHANGES"
        else:
            v1.require(report["estimated_capacity_ok"])
            original_public = v1.public_fingerprints(db)
            insert_projection(db, projection(delta))
            report["verification"] = verify_delta(db, delta)
            # Parent observations/raw bytes and every public table must survive.
            checked_parent, _ = load_archive(db, delta["manifest"]["parent_batch_id"])
            v1.require(v1.canonical(checked_parent) == v1.canonical(parent))
            v1.require(v1.public_fingerprints(db) == original_public)
            report["existing_public_and_parent_contents_unchanged"] = True
            after = db.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0]
            v1.require(after <= max_bytes)
            report.update(status="DELTA_APPENDED", database_bytes_after=after)
        if not apply:
            db.rollback()
    return report


def read_bundle(path):
    return v1.read_json(gzip.decompress(path.read_bytes()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "apply"))
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--parent-archive-id")
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--env-file", type=Path, default=v1.ROOT / ".supabase-migration.env"
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        v1.require(not args.receipt.exists() and not args.receipt.is_symlink())
        parent = read_bundle(args.parent)
        if args.mode == "prepare":
            v1.require(args.current is not None)
            delta = plan_delta(
                parent, read_bundle(args.current), args.parent_archive_id
            )
            with args.delta.open("xb") as stream:
                stream.write(gzip.compress(v1.canonical(delta), mtime=0))
        else:
            delta = read_bundle(args.delta)
            validate_delta(delta, parent)
        result = {
            "mode": args.mode,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "delta_file_sha256": v1.digest(args.delta.read_bytes()),
            **summary(delta),
        }
        if args.mode != "prepare":
            result["remote"] = remote(
                delta,
                parent,
                v1.local_config(args.env_file),
                apply=args.mode == "apply",
            )
        with args.receipt.open("x") as stream:
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
