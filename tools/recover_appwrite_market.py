#!/usr/bin/env python3
"""Preserve a verified baseline and recover later local Appwrite observations.

This does not contact Appwrite, infer deletions, or regenerate user portfolios.
The output is a recovery candidate, never an authoritative live snapshot.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DATABASE = "myinterpreter"


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def iso(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Missing timezone in observation timestamp")
    return timestamp.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def initialize(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market (
            document_id TEXT PRIMARY KEY,
            server_updated_at TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            market_date TEXT,
            company TEXT,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            payload TEXT NOT NULL
        );
    """)


def ingest(connection, path, observed_at, source_kind):
    source_name = str(path.resolve().relative_to(ROOT))
    source_hash = sha256(path)
    prior = connection.execute("SELECT sha256 FROM sources WHERE path = ?", (source_name,)).fetchone()
    if prior:
        if prior[0] != source_hash:
            raise ValueError("A previously imported source file changed")
        return False
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError("Expected a raw Appwrite document list")
    prepared = []
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not row.get("$id")
                or row.get("$databaseId") != DATABASE or row.get("$collectionId") != "data"):
            raise ValueError("Unexpected collection or missing identity in raw export")
        if row["$id"] in seen:
            raise ValueError("Duplicate document ID within a source file")
        seen.add(row["$id"])
        updated = iso(row.get("$updatedAt") or row["$createdAt"])
        # Preserve the entire original document, including its permissions.
        prepared.append((row["$id"], updated, observed_at, row.get("date"),
                         row.get("c_name"), json.dumps(row, sort_keys=True,
                                                       ensure_ascii=False, separators=(",", ":"))))
    with connection:
        cursor = connection.execute(
            "INSERT INTO sources(path,sha256,bytes,observed_at,source_kind,rows) VALUES(?,?,?,?,?,?)",
            (source_name, source_hash, path.stat().st_size, observed_at, source_kind, len(rows)))
        source_id = cursor.lastrowid
        connection.executemany("""
            INSERT INTO market(document_id,server_updated_at,observed_at,market_date,company,source_id,payload)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
                server_updated_at=excluded.server_updated_at,
                observed_at=excluded.observed_at,
                market_date=excluded.market_date,
                company=excluded.company,
                source_id=excluded.source_id,
                payload=excluded.payload
            WHERE excluded.server_updated_at > market.server_updated_at
               OR (excluded.server_updated_at = market.server_updated_at
                   AND excluded.observed_at > market.observed_at)
        """, [(a, b, c, d, e, source_id, payload) for a, b, c, d, e, payload in prepared])
    return True


def recover(baseline, incremental, output, cycle_start):
    if output.is_symlink() or (output.exists() and not (output / "recovery.sqlite").exists()):
        raise ValueError("Choose a new output directory or an existing recovery directory")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    baseline_manifest = json.loads((baseline / "manifest.json").read_text())
    if baseline_manifest.get("database") != DATABASE:
        raise ValueError("Baseline belongs to another database")
    verified_baseline = {}
    for name, entry in baseline_manifest["collections"].items():
        source = baseline / entry["file"]
        if not source.resolve().is_relative_to(baseline.resolve()):
            raise ValueError("Baseline manifest path escapes its directory")
        if sha256(source) != entry["sha256"] or source.stat().st_size != entry["bytes"]:
            raise ValueError("Baseline hash or size mismatch")
        rows = json.loads(source.read_text())
        if len(rows) != entry["documents"]:
            raise ValueError("Baseline document count mismatch")
        destination = output / "baseline" / entry["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(destination) != entry["sha256"]:
            raise ValueError("Baseline copy verification failed")
        verified_baseline[name] = entry
    shutil.copyfile(baseline / "manifest.json", output / "baseline/manifest.json")
    connection = sqlite3.connect(output / "recovery.sqlite")
    connection.execute("PRAGMA foreign_keys=ON")
    initialize(connection)
    ingest(connection, baseline / baseline_manifest["collections"]["data"]["file"],
           iso(baseline_manifest["generated_at_utc"]), "baseline")
    paths = sorted(incremental.glob("*.json"))
    for index, path in enumerate(paths, 1):
        match = re.match(r"(\d{8}T\d{6}Z)_", path.name)
        if not match:
            raise ValueError("Cannot determine when a raw export was captured")
        observed = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        ingest(connection, path, iso(observed.isoformat()), "incremental_snapshot")
        if index % 100 == 0 or index == len(paths):
            print(json.dumps({"local_snapshots_processed": index,
                              "local_snapshots_total": len(paths)}), flush=True)
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("Recovery database failed its integrity check")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Recovery provenance links failed verification")
    recovered = output / "recovered_market.jsonl.gz"
    with recovered.with_suffix(".part").open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            for (payload,) in connection.execute("SELECT payload FROM market ORDER BY document_id"):
                compressed.write((payload + "\n").encode())
    recovered.with_suffix(".part").replace(recovered)
    count, first_date, last_date, companies = connection.execute(
        "SELECT COUNT(*),MIN(market_date),MAX(market_date),COUNT(DISTINCT company) FROM market").fetchone()
    source_rows, source_bytes, source_files = connection.execute(
        "SELECT COALESCE(SUM(rows),0),COALESCE(SUM(bytes),0),COUNT(*) FROM sources "
        "WHERE source_kind='incremental_snapshot'").fetchone()
    cycle_rows = connection.execute(
        "SELECT COALESCE(SUM(rows),0) FROM sources WHERE source_kind='incremental_snapshot' AND observed_at>=?",
        (cycle_start,)).fetchone()[0]
    source_list = [dict(zip(("path", "sha256", "bytes", "observed_at", "kind", "rows"), row))
                   for row in connection.execute(
                       "SELECT path,sha256,bytes,observed_at,source_kind,rows FROM sources ORDER BY observed_at,path")]
    connection.close()
    verified_rows = 0
    with gzip.open(recovered, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if not row.get("$id") or "$permissions" not in row:
                raise ValueError("Portable recovery lost document identity or permissions")
            verified_rows += 1
    if verified_rows != count:
        raise ValueError("Portable recovery row count mismatch")
    summary = {
        "status": "RECOVERED_OBSERVATIONS_NOT_LIVE_SNAPSHOT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_generated_at_utc": baseline_manifest["generated_at_utc"],
        "baseline_collections_verified_and_copied": len(verified_baseline),
        "recovered_distinct_market_document_ids": count,
        "market_date_min": first_date, "market_date_max": last_date,
        "distinct_market_names_including_indices": companies,
        "incremental_snapshot_files": source_files, "incremental_source_bytes": source_bytes,
        "observed_returned_rows_across_incremental_snapshots": source_rows,
        "billing_cycle_start": cycle_start,
        "observed_returned_rows_in_billing_cycle": cycle_rows,
        "source_deletions_known": False,
        "user_accounts_recovered": False,
        "private_collections_as_of": baseline_manifest["generated_at_utc"],
        "files": [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                  for path in (output / "recovery.sqlite", recovered)],
    }
    (output / "sources.json").write_text(json.dumps(source_list, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "README.txt").write_text(
        "LOCAL RECOVERY CANDIDATE — not an authoritative current Appwrite snapshot.\n"
        "baseline/ contains a byte-verified copy of the September export, including private collections.\n"
        "recovered_market.jsonl.gz contains the latest saved observation per original market document ID.\n"
        "Recovery preserves original fields, IDs, timestamps and permissions; it does not infer remote deletions.\n"
        "Old intraday rows may have since been deleted from Appwrite. Reconcile before production import.\n"
        "Private portfolio data is only current as of the baseline date; user accounts/hashes are absent.\n"
        "recovery.sqlite and sources.json preserve provenance for the selected observations.\n"
        "No public-source replacement data or recalculated financial values have been mixed into this copy.\n"
        "Keep this directory out of Git and deployment.\n")
    print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "backup_live_20260919")
    parser.add_argument("--incremental", type=Path,
                        default=ROOT / "research/prediction_model/data/external/appwrite_incremental/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "backup_live_recovery_20261022")
    parser.add_argument("--cycle-start", default="2026-10-06T00:00:00.000+00:00")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.parent != ROOT or not output.name.startswith("backup_live_"):
        parser.error("Use an ignored backup_live_* directory directly under the project root")
    os.umask(0o077)
    recover(args.baseline, args.incremental, output, iso(args.cycle_start))


if __name__ == "__main__":
    main()
