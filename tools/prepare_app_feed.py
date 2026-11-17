#!/usr/bin/env python3
"""Prepare isolated app candidates from verified archives; no remote write option."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from stage_supabase import ROOT, datasets, records, verify

sys.path.insert(0, str(ROOT / "automation/managed"))
import app_feed
import price_refresh
import worker


def build_mapping(config, recovery, indices):
    selected = {
        d.collection: d
        for d in datasets(recovery, None)
        if d.collection in {"company", "format"}
    }
    for dataset in selected.values():
        verify(dataset)
    companies = list(records(selected["company"]))
    names = {row["name"]: row for row in companies}
    if len(names) != len(companies) or len({row["$id"] for row in companies}) != len(
        companies
    ):
        raise ValueError("Ambiguous original company identities")
    stocks = []
    for row in records(selected["format"]):
        company = names.get(row["name"])
        if company is None:
            raise ValueError("No exact original company match")
        stocks.append(
            {
                "source_identity": row["symbol"],
                "symbol": row["symbol"],
                "c_name": company["name"],
                "company_id": company["$id"],
                "asset_key": "company:" + company["$id"],
            }
        )
    mapping = {
        "contract": "private-app-mapping/v1",
        "provider_namespace": config["provider_namespace"],
        "stocks": stocks,
        "indices": indices,
        "artifact_hashes": {
            key: dataset.expected_hash for key, dataset in selected.items()
        },
    }
    app_feed.validate_mapping(mapping, config)
    return mapping


def private_output(path):
    if not path.resolve().is_relative_to((ROOT / "private").resolve()):
        raise ValueError("Output must stay in the ignored private directory")
    if path.exists():
        raise ValueError("Refusing to overwrite an existing artifact")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--index-map", type=Path, required=True)
    parser.add_argument(
        "--recovery", type=Path, default=ROOT / "backup_live_recovery_20261022"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--allow-legacy-replay-ids", action="store_true")
    parser.add_argument("--include-price-refresh", action="store_true",
                        help="Also derive legacy application rows and enrichment choices, without writing tables")
    parser.add_argument("--application-bindings", type=Path,
                        help="Private optional market-field bindings for --include-price-refresh")
    args = parser.parse_args(argv)
    try:
        private_output(args.output)
        config = worker.decode(args.config.read_bytes())
        mapping = build_mapping(
            config, args.recovery, worker.decode(args.index_map.read_bytes())
        )
        as_of = worker.utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
        candidate = app_feed.build(
            args.archive.read_bytes(),
            args.sha256,
            config,
            mapping,
            as_of=as_of,
            allow_legacy_replay_ids=args.allow_legacy_replay_ids,
        )
        output = {"mapping": mapping, "candidate": candidate}
        if args.application_bindings and not args.include_price_refresh:
            raise ValueError("Application bindings require price refresh")
        if args.include_price_refresh:
            if args.allow_legacy_replay_ids:
                raise ValueError("Full price refresh requires original observation identities")
            dataset = next(d for d in datasets(args.recovery, None) if d.collection == "company")
            verify(dataset)
            companies = {row["$id"]: row for row in records(dataset)}
            bindings = worker.decode(args.application_bindings.read_bytes()) if args.application_bindings else {}
            output["price_refresh"] = price_refresh.build(
                args.archive.read_bytes(), args.sha256, config, mapping, companies,
                as_of=as_of, field_bindings=bindings,
            )
        args.output.write_text(app_feed.canonical(output) + "\n")
        print(
            json.dumps(
                {
                    "status": "SHADOW_ONLY",
                    "stocks": len(mapping["stocks"]),
                    "indices": len(mapping["indices"]),
                    "coverage": candidate["coverage"],
                    "source_execution": candidate["source_execution"],
                    "remote_data_written": False,
                }
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": str(error)
                    if isinstance(error, (app_feed.FrameError, worker.AcquisitionError))
                    else "APP_FEED_PREPARATION_FAILED",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
