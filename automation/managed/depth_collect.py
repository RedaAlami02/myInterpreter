#!/usr/bin/env python3
"""Bounded private depth batches. Request templates/bindings stay in CI secrets."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

import depth_frame
from market_frame import FrameError, valid_path
import worker


def validate(config):
    if (
        not isinstance(config, dict)
        or config.get("contract") != "private-depth-config/v2"
        or not re.fullmatch(r"feed_[a-f0-9]{16}", config.get("provider_namespace", ""))
    ):
        raise FrameError("INVALID_DEPTH_CONFIGURATION")
    expected = config.get("expected_source_identities")
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) > 2000
        or any(
            not isinstance(identity, str) or not 1 <= len(identity) <= 200
            for identity in expected
        )
        or len(set(expected)) != len(expected)
    ):
        raise FrameError("INVALID_EXPECTED_UNIVERSE")
    paths = config.get("request_identity_paths")
    if (
        not isinstance(paths, list)
        or not paths
        or any(not valid_path(path) or not path for path in paths)
    ):
        raise FrameError("INVALID_REQUEST_IDENTITY_PATHS")
    depth_frame.validate_spec(config.get("spec"))
    for identity in expected:
        request_for(config, identity)


def request_for(config, identity):
    recipe = copy.deepcopy(config.get("request_template"))
    if not isinstance(recipe, dict) or not isinstance(recipe.get("body"), (dict, list)):
        raise FrameError("INVALID_REQUEST_TEMPLATE")
    for path in config["request_identity_paths"]:
        value = recipe["body"]
        try:
            for key in path[:-1]:
                value = value[key]
            if isinstance(value, dict) and path[-1] not in value:
                raise KeyError()
            value[path[-1]] = identity
        except (KeyError, IndexError, TypeError):
            raise FrameError("INVALID_REQUEST_IDENTITY_PATH") from None
    return recipe


def acquire(
    config,
    slot,
    *,
    fetcher=worker.fetch,
    clock=lambda: datetime.now(timezone.utc),
    pause=time.sleep,
    seconds=120,
    execution="CURRENT_ACQUISITION",
):
    validate(config)
    worker.utc(slot)
    started = clock()
    if execution not in {"CURRENT_ACQUISITION", "AFTER_HOURS_DIAGNOSTIC"}:
        raise FrameError("INVALID_EXECUTION")
    if (
        execution == "CURRENT_ACQUISITION"
        and worker.scheduled_slot(started, "depth") != slot
    ):
        raise FrameError("OUTSIDE_WINDOW_OR_WRONG_SLOT")
    deadline = time.monotonic() + seconds
    attempts = []
    captures = []
    frames = []
    stop_reason = "UNIVERSE_ATTEMPTED"
    for index, identity in enumerate(config["expected_source_identities"]):
        if time.monotonic() >= deadline:
            stop_reason = "TIME_BUDGET"
            break
        remaining = worker.MAX_BATCH - sum(len(c["raw_hex"]) // 2 for c in captures)
        if remaining <= 0:
            stop_reason = "BYTE_BUDGET"
            break
        receipt = {}
        try:
            recipe = request_for(config, identity)
            raw, captured = fetcher(recipe, deadline, min(worker.MAX_BODY, remaining))
            if captured.tzinfo is None:
                raise FrameError("INVALID_CAPTURE_TIME")
            digest = hashlib.sha256(raw).hexdigest()
            capture_id = hashlib.sha256(
                json.dumps(
                    [config["provider_namespace"], digest, captured.isoformat()],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            captures.append(
                {
                    "request_index": index,
                    "requested_identity": identity,
                    "capture_id": capture_id,
                    "received_at": captured.isoformat(),
                    "sha256": digest,
                    "raw_hex": raw.hex(),
                }
            )
            receipt = {"raw_sha256": digest, "captured_at": captured.isoformat()}
            frame = depth_frame.normalize(raw, config["spec"], identity, captured)
            frame["capture_id"] = capture_id
            frames.append(frame)
            attempts.append({"source_identity": identity, "frame": frame})
        except (FrameError, worker.AcquisitionError) as error:
            attempts.append(
                {
                    "source_identity": identity,
                    "frame": None,
                    "code": str(error),
                    **receipt,
                }
            )
        if index + 1 < len(config["expected_source_identities"]):
            pause(min(0.5, max(0, deadline - time.monotonic())))
    finished = clock()
    batch = depth_frame.manifest(
        config["provider_namespace"],
        config["expected_source_identities"],
        attempts,
        started_at=started,
        finished_at=finished,
    )
    return {
        "contract": "private-acquisition/v2",
        "kind": "depth",
        "provider_namespace": config["provider_namespace"],
        "slot": slot,
        "completed_at": finished.isoformat(),
        "execution": execution,
        "captures": captures,
        "depth_frames": frames,
        "depth_manifest": batch,
        "acquisition_summary": {
            "stop_reason": stop_reason,
            "budget_seconds": seconds,
            "attempted": len(attempts),
            "failed": sum(a.get("frame") is None for a in attempts),
            "unattempted": len(config["expected_source_identities"]) - len(attempts),
        },
        "errors": [
            {"request_index": i, "code": a["code"]}
            for i, a in enumerate(attempts)
            if "code" in a
        ],
        "completeness": batch["completeness"],
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--isolated-store", type=Path)
    args = parser.parse_args(argv)
    try:
        config = worker.decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        validate(config)
        slot = worker.scheduled_slot(datetime.now(timezone.utc), "depth")
        if slot is None:
            print(json.dumps({"status": "OUTSIDE_WINDOW"}))
            return 0
        store = worker.open_store(args.isolated_store, config)
        worker.resume_store(store)
        if store.complete(config["provider_namespace"], "depth", slot):
            print(json.dumps({"status": "ALREADY_COMPLETE"}))
            return 0
        worker.require_acquisition_admission(store, config['provider_namespace'], 'depth', slot)
        value = acquire(config, slot)
        digest = store.save(value)
        print(
            json.dumps(
                {
                    "status": value["completeness"],
                    "archive_digest": digest,
                    "requests": len(value["captures"]),
                    "snapshots": len(value["depth_frames"]),
                    "missing": len(value["depth_manifest"]["missing_identities"]),
                    **value["acquisition_summary"],
                    "prediction_eligible": False,
                }
            )
        )
        return 0 if value["completeness"] == "COMPLETE" else 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": str(error)
                    if isinstance(error, (FrameError, worker.AcquisitionError))
                    else "WORKER_FAILURE",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
