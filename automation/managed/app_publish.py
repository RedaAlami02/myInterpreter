#!/usr/bin/env python3
"""Trusted shadow-feed publisher. Refuses replays and unapproved pins."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import app_feed
import price_refresh
import worker

CONTRACT = "private-app-publish/v1"


def approved_mapping(profile, config):
    if (
        not isinstance(profile, dict)
        or profile.get("contract") != CONTRACT
        or profile.get("provider_namespace") != config.get("provider_namespace")
        or not isinstance(profile.get("mapping"), dict)
        or not isinstance(profile.get("mapping_sha256"), str)
        or not isinstance(profile.get("recipe_sha256"), str)
        or ('display_fallbacks' in profile and not isinstance(profile['display_fallbacks'], bool))
    ):
        raise app_feed.FrameError("INVALID_PUBLISH_PROFILE")
    mapping = profile["mapping"]
    app_feed.validate_mapping(mapping, config)
    if app_feed.fingerprint(mapping) != profile["mapping_sha256"]:
        raise app_feed.FrameError("MAPPING_PIN_MISMATCH")
    if app_feed.fingerprint(config["recipe"]) != profile["recipe_sha256"]:
        raise app_feed.FrameError("RECIPE_PIN_MISMATCH")
    return mapping


def open_publisher(config, *, session=None, url=None, token=None):
    url = url or os.environ.get("APP_PUBLISHER_URL")
    token = token or os.environ.get("APP_PUBLISHER_TOKEN")
    if not url or not token:
        raise app_feed.FrameError("PUBLISHER_NOT_CONFIGURED")
    if os.environ.get("APP_WORKER_DATABASE_URL"):
        raise app_feed.FrameError("AMBIGUOUS_PUBLISHER_CONFIGURATION")
    from publish_store import AppPublisherStore

    return AppPublisherStore(
        url, token, config.get("archive_project_reference"), session=session
    )


def prepare(blob, digest, config, profile, *, as_of=None, companies=None, field_bindings=None):
    mapping = approved_mapping(profile, config)
    if profile.get('application_fields_sha256') is not None and (companies is None or field_bindings is None):
        raise app_feed.FrameError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
    if not isinstance(as_of, datetime):
        as_of = datetime.now(timezone.utc)
    builder = app_feed.build_with_references if profile.get('display_fallbacks') is True else app_feed.build
    candidate = builder(blob, digest, config, mapping, as_of=as_of)
    if candidate["source_execution"] != "CURRENT_ACQUISITION":
        raise app_feed.FrameError("PUBLISH_REQUIRES_CURRENT_ACQUISITION")
    if candidate["identity_evidence"] != "NORMALIZER_IDS_VERIFIED":
        raise app_feed.FrameError("PUBLISH_REQUIRES_ORIGINAL_IDS")
    if (
        candidate.get("mode") != "SHADOW_ONLY"
        or candidate.get("prediction_eligible") is not False
        or candidate.get("portfolio_valuation_eligible") is not False
    ):
        raise app_feed.FrameError("INVALID_SHADOW_CANDIDATE")
    full_rows = None
    if companies is not None or field_bindings is not None:
        if companies is None or field_bindings is None:
            raise app_feed.FrameError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
        if app_feed.fingerprint(field_bindings) != profile.get('application_fields_sha256'):
            raise app_feed.FrameError('APPLICATION_FIELDS_PIN_MISMATCH')
        full_rows = price_refresh.publication(blob, digest, config, mapping, companies, candidate,
                                              as_of=as_of, field_bindings=field_bindings)
    return {'candidate':candidate,'mapping':mapping,'application_rows':full_rows}


def publish_prepared(prepared, config, *, publisher=None):
    candidate, mapping = prepared['candidate'], prepared['mapping']
    target = publisher or open_publisher(config)
    receipt = (target.publish(candidate,mapping,application_rows=prepared['application_rows'])
               if prepared['application_rows'] is not None else target.publish(candidate,mapping))
    return {
        "status": receipt["status"],
        "sha256": receipt["sha256"],
        "captured_at": receipt["captured_at"],
        "coverage": candidate["coverage"],
        "prediction_eligible": False,
        **({'application_rows_sha256': receipt['application_rows_sha256']}
           if 'application_rows_sha256' in receipt else {}),
    }


def publish(blob, digest, config, profile, *, as_of=None, publisher=None, companies=None, field_bindings=None):
    prepared = prepare(blob,digest,config,profile,as_of=as_of,companies=companies,field_bindings=field_bindings)
    return publish_prepared(prepared,config,publisher=publisher)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--companies", type=Path, help="Private company-input snapshot keyed by company ID")
    parser.add_argument("--application-bindings", type=Path, help="Private opt-in full-row field bindings")
    args = parser.parse_args(argv)
    try:
        config = worker.decode(args.config.read_bytes())
        profile = worker.decode(args.profile.read_bytes())
        if bool(args.companies) != bool(args.application_bindings):
            raise app_feed.FrameError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
        as_of = worker.utc(args.as_of) if args.as_of else None
        summary = publish(
            args.archive.read_bytes(), args.sha256, config, profile, as_of=as_of,
            companies=worker.decode(args.companies.read_bytes()) if args.companies else None,
            field_bindings=worker.decode(args.application_bindings.read_bytes()) if args.application_bindings else None,
        )
        print(json.dumps(summary))
        return 0
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, (app_feed.FrameError, worker.AcquisitionError))
            else "PUBLISH_FAILED"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
