#!/usr/bin/env python3
"""Export a sanitized, immutable history preview without changing remote grants.

The caller pins the source bundle. Optional SQL verification is TLS READ ONLY.
Only generic historical-close fields are exported; raw evidence stays private.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
import re

from import_versioned_history import (
    ROOT,
    canonical,
    connect,
    digest,
    instant,
    local_config,
    read_json,
    require,
    validate,
    verify_remote,
)

CONTRACT = "daily-close-preview-v1"


def build_projection(bundle):
    validate(bundle)
    captures = {c[0]: c for c in bundle["captures"]}
    grouped = defaultdict(lambda: defaultdict(list))
    for symbol, ordinal, identity, day, label, close, bar, warnings in bundle["rows"]:
        require(re.fullmatch("[A-Z0-9]{1,12}", symbol) is not None)
        grouped[symbol][day].append(
            {
                "observation_id": identity,
                "close_decimal": close,
                "quality_warnings": warnings,
            }
        )
    result = {}
    for symbol, days in sorted(grouped.items()):
        points = []
        for day, candidates in sorted(days.items()):
            candidates = sorted(candidates, key=lambda r: r["observation_id"])
            distinct = {Decimal(c["close_decimal"]) for c in candidates}
            status = "AVAILABLE"
            if len(candidates) > 1:
                status = (
                    "CONFLICTING_CLOSES"
                    if len(distinct) > 1
                    else "DUPLICATE_OBSERVATIONS"
                )
            points.append(
                {
                    "date": day,
                    "status": status,
                    "close_decimal": candidates[0]["close_decimal"]
                    if status == "AVAILABLE"
                    else None,
                    "candidates": candidates,
                }
            )
        result[symbol] = {
            "contract": CONTRACT,
            "version": bundle["batch_id"],
            "symbol": symbol,
            "kind": "INDEX" if symbol == "MASI" else "SECURITY",
            "classification": "RETROSPECTIVE_SOURCE_HISTORY",
            "price_definition": "DAILY_CLOSE_CANDIDATE",
            "not_live": True,
            "original_observation_times": "UNKNOWN",
            "captured_at": instant(captures[symbol][1]).isoformat(),
            "first_date": points[0]["date"],
            "last_date": points[-1]["date"],
            "observation_count": sum(len(p["candidates"]) for p in points),
            "duplicate_days": sum(p["status"] != "AVAILABLE" for p in points),
            "conflicting_days": sum(
                p["status"] == "CONFLICTING_CLOSES" for p in points
            ),
            "points": points,
        }
    return result


def write_projection(bundle, folder):
    """Write into a new directory only; a partial export is never published."""
    require(not folder.exists() and not folder.is_symlink())
    series = build_projection(bundle)
    folder.mkdir(mode=0o700, parents=True)
    manifest = {
        "contract": CONTRACT,
        "version": bundle["batch_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": "RETROSPECTIVE_SOURCE_HISTORY",
        "not_live": True,
        "original_observation_times": "UNKNOWN",
        "instruments": [],
    }
    for symbol, values in series.items():
        filename = "s_" + digest(symbol.encode())[:16] + ".json"
        encoded = canonical(values)
        with (folder / filename).open("xb") as stream:
            stream.write(encoded)
        manifest["instruments"].append(
            {
                "symbol": symbol,
                "kind": values["kind"],
                "file": filename,
                "sha256": digest(encoded),
                "observation_count": values["observation_count"],
                "first_date": values["first_date"],
                "last_date": values["last_date"],
                "duplicate_days": values["duplicate_days"],
                "conflicting_days": values["conflicting_days"],
            }
        )
    raw = canonical(manifest)
    # Manifest is the final commit marker; readers additionally require its pin.
    with (folder / "manifest.json").open("xb") as stream:
        stream.write(raw)
    return {
        "contract": CONTRACT,
        "manifest_sha256": digest(raw),
        "version": bundle["batch_id"],
        "instruments": len(series),
        "observations": sum(v["observation_count"] for v in series.values()),
        "duplicate_days": sum(v["duplicate_days"] for v in series.values()),
        "conflicting_days": sum(v["conflicting_days"] for v in series.values()),
        "not_live": True,
        "remote_writes": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--verify-remote", action="store_true")
    parser.add_argument(
        "--archive-id", help="Explicit SQL archive version, including sparse v2 batches"
    )
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".supabase-migration.env"
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        require(not args.receipt.exists() and not args.receipt.is_symlink())
        require(args.archive_id is None or args.verify_remote)
        raw = args.bundle.read_bytes()
        require(digest(raw) == args.bundle_sha256)
        bundle = read_json(gzip.decompress(raw))
        validate(bundle)
        checked = None
        if args.verify_remote:
            with connect(local_config(args.env_file)) as db:
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                if args.archive_id is None:
                    checked = verify_remote(db, bundle)
                else:
                    from history_delta import load_archive

                    remote_bundle, checked = load_archive(db, args.archive_id)
                    require(canonical(remote_bundle) == canonical(bundle))
                db.rollback()
        result = write_projection(bundle, args.output)
        result["remote_read_only_verification"] = checked
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
