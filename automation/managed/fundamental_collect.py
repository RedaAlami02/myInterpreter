#!/usr/bin/env python3
"""Opt-in fundamental acquisition for one company. Archives raw responses.

Native endpoints, headers and table bindings live in a private JSON
configuration. No response content, endpoint or exception detail is printed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import fundamental_frame as frame
from fundamental_feed import KINDS
import worker

CONTRACT = "private-fundamental-config/v1"
PHASES = ("identity", "company", "symbol")
RECIPE_KEYS = {"kind", "url", "method", "body", "headers"}
MAX_PAGE = 4 * 1024 * 1024
MAX_RECIPES = 30
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,31}")


def config_check(config):
    if (
        not isinstance(config, dict)
        or config.get("contract") != CONTRACT
        or not isinstance(config.get("provider_namespace"), str)
        or not re.fullmatch(r"feed_[a-f0-9]{16}", config["provider_namespace"])
        or not isinstance(config.get("jobs"), dict)
        or set(config["jobs"]) != {"fundamentals"}
        or not isinstance(config["jobs"]["fundamentals"], dict)
        or not config["jobs"]["fundamentals"]
        or set(config["jobs"]["fundamentals"]) - set(PHASES)
        or "identity" not in config["jobs"]["fundamentals"]
    ):
        raise worker.AcquisitionError("INVALID_FUNDAMENTAL_CONFIG")
    seen, total = set(), 0
    for phase, recipes in config["jobs"]["fundamentals"].items():
        if not isinstance(recipes, list) or not recipes:
            raise worker.AcquisitionError("INVALID_FUNDAMENTAL_RECIPES")
        for recipe in recipes:
            total += 1
            if (
                not isinstance(recipe, dict)
                or set(recipe) - RECIPE_KEYS
                or not {"kind", "url"}.issubset(recipe)
                or recipe["kind"] not in KINDS
                or recipe["kind"] in seen
                or not isinstance(recipe["url"], str)
                or urlsplit(recipe["url"]).scheme != "https"
                or recipe.get("method", "GET") not in {"GET", "POST"}
                or (
                    recipe.get("headers") is not None
                    and (
                        not isinstance(recipe["headers"], dict)
                        or any(
                            not isinstance(name, str)
                            or not isinstance(value, str)
                            or re.search(r"[\r\n]", name + value)
                            for name, value in recipe["headers"].items()
                        )
                    )
                )
                or (phase != "company" and "{company}" in json.dumps(recipe))
            ):
                raise worker.AcquisitionError("INVALID_FUNDAMENTAL_RECIPES")
            seen.add(recipe["kind"])
    if total > MAX_RECIPES:
        raise worker.AcquisitionError("INVALID_FUNDAMENTAL_RECIPES")


def substitute(value, symbol, company):
    if isinstance(value, str):
        return value.replace("{symbol}", symbol).replace("{company}", company or "")
    if isinstance(value, list):
        return [substitute(item, symbol, company) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, symbol, company) for key, item in value.items()}
    return value


def envelope(config, symbol, fetched, errors, completed_at, *, subject_scoped=False):
    captures, targets = [], []
    for recipe in [
        recipe
        for phase in PHASES
        for recipe in config["jobs"]["fundamentals"].get(phase, [])
    ]:
        if recipe["kind"] not in fetched:
            continue
        raw, received = fetched[recipe["kind"]]
        digest = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256(
            json.dumps(
                [config["provider_namespace"], digest, received.isoformat()],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        position = len(captures)
        captures.append(
            {
                "request_index": position,
                "capture_id": identity,
                "received_at": received.isoformat(),
                "sha256": digest,
                "raw_hex": raw.hex(),
            }
        )
        targets.append({"request_index": position, "kind": recipe["kind"]})
    slot = min(received for _, received in fetched.values()).replace(
        minute=0, second=0, microsecond=0
    )
    return {
        "contract": "private-acquisition/v3" if subject_scoped else "private-acquisition/v2",
        **({'subject_key': 'symbol:' + symbol} if subject_scoped else {}),
        "provider_namespace": config["provider_namespace"],
        "kind": "fundamentals",
        "symbol": symbol,
        "slot": slot.isoformat(),
        "completed_at": completed_at.isoformat(),
        "execution": "CURRENT_ACQUISITION",
        "completeness": "COMPLETE" if not errors else "INCOMPLETE",
        "errors": errors,
        "captures": captures,
        "targets": targets,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }


def acquire(config, symbol, *, fetcher=worker.fetch, seconds=120, now=None, subject_scoped=False):
    config_check(config)
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise worker.AcquisitionError("INVALID_SYMBOL")
    deadline = time.monotonic() + seconds
    fetched, errors = {}, []

    def run(phase, company):
        for recipe in config["jobs"]["fundamentals"].get(phase, []):
            if "{company}" in json.dumps(recipe) and company is None:
                raise worker.AcquisitionError("UNRESOLVED_COMPANY_IDENTITY")
            try:
                raw, received = fetcher(
                    substitute(recipe, symbol, company), deadline, MAX_PAGE
                )
            except worker.AcquisitionError as error:
                errors.append({"kind": recipe["kind"], "code": str(error)})
                continue
            fetched[recipe["kind"]] = (raw, received)

    def decoded(kind):
        item = fetched.get(kind)
        if item is None:
            return None
        try:
            return worker.decode(item[0])
        except worker.AcquisitionError:
            return None

    run("identity", None)
    company, _sector = frame.identity(symbol, decoded("stock"), decoded("symlinks"))
    if not company:
        raise worker.AcquisitionError("UNRESOLVED_COMPANY_IDENTITY")
    run("company", company)
    run("symbol", company)
    if not fetched:
        raise worker.AcquisitionError("NO_FUNDAMENTAL_RESPONSES")
    completed = now or datetime.now(timezone.utc)
    if completed < max(received for _, received in fetched.values()):
        raise worker.AcquisitionError("INVALID_COMPLETION_TIME")
    return envelope(config, symbol, fetched, errors, completed, subject_scoped=subject_scoped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--isolated-store", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--subject-scoped", action="store_true", help="Default: company-scoped v3 archives")
    mode.add_argument("--legacy-unscoped", action="store_true", help="Explicit legacy v2 compatibility")
    args = parser.parse_args(argv)
    store = None
    try:
        config = worker.decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        config_check(config)
        symbol = args.symbol.strip().upper()
        if not SYMBOL.fullmatch(symbol):
            raise worker.AcquisitionError("INVALID_SYMBOL")
        store = worker.open_store(args.isolated_store, config)
        worker.resume_store(store)
        scoped = not args.legacy_unscoped
        slot = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
        if scoped and (not callable(getattr(store, "subject_complete", None))
                       or not callable(getattr(store, "admit_subject", None))):
            raise worker.AcquisitionError("SUBJECT_ARCHIVE_NOT_CONFIGURED")
        if scoped and store.subject_complete(config["provider_namespace"], "fundamentals", slot, "symbol:" + symbol):
            print(json.dumps({"status": "ALREADY_COMPLETE"}))
            return 0
        if scoped and not store.admit_subject(config["provider_namespace"], "symbol:" + symbol):
            raise worker.AcquisitionError("SUBJECT_ACQUISITION_NOT_ADMITTED")
        if not scoped and not isinstance(store, worker.SQLiteStore):
            raise worker.AcquisitionError('LEGACY_REQUIRES_ISOLATED_STORE')
        value = acquire(config, symbol, subject_scoped=scoped)
        if not scoped and store.complete(config["provider_namespace"], "fundamentals", value["slot"]):
            print(json.dumps({"status": "ALREADY_COMPLETE"}))
            return 0
        digest = store.save(value)
        print(
            json.dumps(
                {
                    "status": value["completeness"],
                    "symbol": value["symbol"],
                    "responses": len(value["captures"]),
                    "errors": len(value["errors"]),
                    "archive_digest": digest,
                    "prediction_eligible": False,
                }
            )
        )
        return 0 if value["completeness"] == "COMPLETE" else 2
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, worker.AcquisitionError)
            else "WORKER_FAILURE"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1
    finally:
        if isinstance(store, worker.SQLiteStore):
            store.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
