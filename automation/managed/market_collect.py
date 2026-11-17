#!/usr/bin/env python3
"""Opt-in market acquisition; recorded replays can only use isolated local storage."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

import market_frame
import worker


def validate(config):
    if (
        not isinstance(config, dict)
        or config.get("contract") != "private-market-config/v2"
        or not isinstance(config.get("provider_namespace"), str)
        or not re.fullmatch(r"feed_[a-f0-9]{16}", config["provider_namespace"])
    ):
        raise market_frame.FrameError("INVALID_MARKET_CONFIGURATION")
    market_frame.recipe_check(config.get("recipe"))


def envelope(config, raw, captured, slot, *, execution):
    validate(config)
    if captured.tzinfo is None or execution not in {
        "CURRENT_ACQUISITION",
        "RECORDED_REPLAY",
    }:
        raise market_frame.FrameError("INVALID_EXECUTION")
    errors = []
    try:
        normalized = market_frame.normalize(
            raw,
            config["recipe"],
            captured,
            market_date=captured.astimezone(worker.ZONE).date(),
        )
    except market_frame.FrameError as error:
        normalized = None
        errors.append({"code": str(error)})
    capture_id = hashlib.sha256(
        json.dumps(
            [
                config["provider_namespace"],
                hashlib.sha256(raw).hexdigest(),
                captured.isoformat(),
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if normalized is not None:
        for kind, rows in normalized["views"].items():
            for row in rows:
                location = config["recipe"]["views"][kind]["rows_path"] + [
                    row["raw_row_index"]
                ]
                row["observation_id"] = hashlib.sha256(
                    json.dumps([capture_id, location], separators=(",", ":")).encode()
                ).hexdigest()
    return {
        "contract": "private-acquisition/v2",
        "provider_namespace": config["provider_namespace"],
        "kind": "quotes",
        "slot": slot,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "completeness": normalized["completeness"] if normalized else "INCOMPLETE",
        "errors": errors,
        "captures": [
            {
                "request_index": 0,
                "capture_id": capture_id,
                "received_at": captured.isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "raw_hex": raw.hex(),
            }
        ],
        "market_frame": normalized,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }


def replay(config, raw, receipt):
    validate(config)
    expected = receipt.get("sha256")
    if not isinstance(expected, str) or expected != hashlib.sha256(raw).hexdigest():
        raise market_frame.FrameError("RECORDED_RAW_HASH_MISMATCH")
    captured = worker.utc(receipt.get("received_at"))
    slot = captured.replace(
        minute=captured.minute // 15 * 15, second=0, microsecond=0
    ).isoformat()
    return envelope(config, raw, captured, slot, execution="RECORDED_REPLAY")


def summary(value, digest, compressed_bytes):
    frame = value.get("market_frame")
    coverage = frame["coverage"] if frame else {}
    return {
        "status": value["completeness"],
        "contract": value["contract"],
        "execution": value["execution"],
        "archive_digest": digest,
        "compressed_envelope_bytes": compressed_bytes,
        "stock_references": coverage.get("referenced_stocks", 0),
        "stock_quotes": coverage.get("observed_stocks", 0),
        "same_date_stock_quotes": coverage.get("same_date_stocks", 0),
        "missing_stock_quotes": len(coverage.get("missing_quote_identities", [])),
        "index_same_date": coverage.get("index_same_date", False),
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
    }


def dispatch_enrichment(args, printed):
    if args.enrichment_config is not None:
        import enrichment_jobs
        try:
            printed['enrichment'] = enrichment_jobs.execute(args.enrichment_config,args.enrichment_index,
                args.enrichment_spool,max_jobs=args.enrichment_max_jobs)
        except Exception:
            printed['enrichment'] = {'status':'FAILED','code':'ENRICHMENT_EXECUTION_FAILED'}
    return printed.get('enrichment',{}).get('status','COMPLETE') == 'COMPLETE'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--isolated-store", type=Path)
    parser.add_argument("--recorded-response", type=Path)
    parser.add_argument("--recorded-receipt", type=Path)
    parser.add_argument("--publish-profile", type=Path)
    parser.add_argument("--publication-spool", type=Path)
    parser.add_argument("--companies", type=Path)
    parser.add_argument("--application-bindings", type=Path)
    parser.add_argument("--company-index", type=Path)
    parser.add_argument("--enrichment-config", type=Path)
    parser.add_argument("--enrichment-index", type=Path)
    parser.add_argument("--enrichment-spool", type=Path)
    parser.add_argument("--enrichment-max-jobs", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.publication_spool is not None and args.publish_profile is None:
            raise market_frame.FrameError('PUBLICATION_PROFILE_REQUIRED')
        if any(v is not None for v in [args.companies,args.application_bindings,args.company_index]) and args.publish_profile is None:
            raise market_frame.FrameError('PUBLICATION_PROFILE_REQUIRED')
        enrich = [args.enrichment_config,args.enrichment_index,args.enrichment_spool]
        if any(item is not None for item in enrich) and (
                not all(item is not None for item in enrich) or args.publish_profile is None
                or not 1<=args.enrichment_max_jobs<=5):
            raise market_frame.FrameError('INVALID_ENRICHMENT_OPTIONS')
        if args.publish_profile is not None and (
            args.isolated_store is not None
            or args.recorded_response is not None
            or args.recorded_receipt is not None
        ):
            raise market_frame.FrameError("PUBLISH_REQUIRES_MANAGED_STORE")
        config = worker.decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        validate(config)
        recorded = (
            args.recorded_response is not None or args.recorded_receipt is not None
        )
        if recorded:
            # Refuse remote initialization, even if a database credential is present.
            if (
                args.isolated_store is None
                or args.recorded_response is None
                or args.recorded_receipt is None
            ):
                raise market_frame.FrameError(
                    "REPLAY_REQUIRES_ISOLATED_STORE_AND_RECEIPT"
                )
            value = replay(
                config,
                args.recorded_response.read_bytes(),
                worker.decode(args.recorded_receipt.read_bytes()),
            )
            store = worker.SQLiteStore(args.isolated_store)
        else:
            slot = worker.scheduled_slot(datetime.now(timezone.utc), "quotes")
            if slot is None:
                import quote_recovery
                slot = quote_recovery.slot(datetime.now(timezone.utc), os.environ.get("APP_QUOTE_RECOVERY_UNTIL"))
            if slot is None:
                print(
                    json.dumps(
                        {"status": "OUTSIDE_WINDOW", "prediction_eligible": False}
                    )
                )
                return 0
            store = worker.open_store(args.isolated_store, config)
            publications = None
            if args.publish_profile is not None:
                import price_publication
                publications = price_publication.Publications(config,
                    worker.decode(args.publish_profile.read_bytes()),args.publication_spool)
                publications.available(store,other_spools=[args.enrichment_spool])
                publications.flush(store)
            worker.resume_store(store)
            if store.complete(config["provider_namespace"], "quotes", slot):
                if publications is not None and not publications.complete(slot):
                    print(json.dumps({'status':'PUBLICATION_UNVERIFIED',
                        'code':'ARCHIVE_COMPLETE_WITHOUT_PUBLICATION_RECEIPT','prediction_eligible':False}))
                    return 2
                printed = {"status": "ALREADY_COMPLETE", "prediction_eligible": False}
                enriched = dispatch_enrichment(args, printed)
                print(json.dumps(printed))
                return 0 if enriched else 2
            companies,bindings,context = (price_publication.company_inputs(config,publications.profile,
                companies_path=args.companies,bindings_path=args.application_bindings,index_path=args.company_index)
                if publications is not None else (None,None,None))
            worker.require_acquisition_admission(store, config['provider_namespace'], 'quotes', slot,
                shadow=publications is not None,
                projection=bool(publications is not None and publications.profile.get('application_fields_sha256')))
            raw, captured = worker.fetch(config["recipe"], time.monotonic() + 80)
            value = envelope(
                config, raw, captured, slot, execution="CURRENT_ACQUISITION"
            )
        if args.publish_profile is not None:
            digest,blob=publications.enqueue(value,companies=companies,field_bindings=bindings,company_context=context)
            published=publications.flush(store)
        else:
            digest=store.save(value)
            _,blob=worker.packed(value)
        printed = summary(value, digest, len(blob))
        if args.publish_profile is not None:
            printed["published"] = published["status"]
        enriched = dispatch_enrichment(args, printed)
        display_published = (os.environ.get('APP_SCHEDULE_CONTRACT') == 'recurring-casablanca/v1'
            and args.publish_profile is not None and published.get('status') == 'PUBLISHED')
        if display_published and value['completeness'] != 'COMPLETE':
            printed['status'] = 'PARTIAL_DISPLAY_PUBLISHED'
            printed['acquisition_completeness'] = value['completeness']
        print(json.dumps(printed))
        if not enriched:
            return 2
        return 0 if value["completeness"] == "COMPLETE" or display_published else 2
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, (market_frame.FrameError, worker.AcquisitionError))
            else "WORKER_FAILURE"
        )
        print(
            json.dumps({"status": "FAILED", "code": code, "prediction_eligible": False})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
