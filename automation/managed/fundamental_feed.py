"""Verified fundamental bundle -> company projection. Never invents a figure."""

from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math

import fundamental_frame as frame
import worker

CONTRACT = "fundamental-projection/v1"
INDEX_CONTRACT = "private-fundamental-index/v1"
MAX_PAGE = 4 * 1024 * 1024
MAX_EXPANDED = 24 * 1024 * 1024
KINDS = {
    "stock", "financial", "symlinks", "rnpg", "ca", "ebe", "ebit", "fp", "dn",
    "tn", "dpa", "fcf", "actif", "nmt", "trim", "sem", "coursref", "beta",
    "desc", "holders",
}
NUMERIC_FIELDS = [
    "bpa", "dpa", "tc5", "roe", "na", "cp", "beta_3y", "beta_5y", "revenue",
    "ebitda", "ebit", "net_profit", "fcf", "net_debt", "net_cash",
    "total_assets", "rev_growth_5y", "rnpg_growth_5y", "profit_margin", "rnpg_est",
]
TEXT_FIELDS = ["ext_name", "sector", "description"]
INT_FIELDS = ["fiscal_year", "fy_est"]


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True
    )


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def clean(value, maximum=200):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and not any(ord(c) < 32 for c in value)
    )


def clean_text(value, maximum):
    """Profile prose may contain tabs/newlines; identifiers may not."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and not any(ord(c) < 32 and c not in "\t\n\r" for c in value)
    )


def validate_index(index, provider):
    if (
        not isinstance(index, dict)
        or index.get("contract") != INDEX_CONTRACT
        or index.get("provider_namespace") != provider
        or not isinstance(index.get("symbols"), dict)
        or not 1 <= len(index["symbols"]) <= 2000
        or any(
            not clean(symbol, 32) or not clean(name, 200)
            for symbol, name in index["symbols"].items()
        )
    ):
        raise ValueError("INVALID_FUNDAMENTAL_INDEX")
    return index["symbols"]


def verified_archive(blob, digest, config):
    if (
        len(blob) > worker.MAX_BATCH
        or not isinstance(digest, str)
        or hashlib.sha256(blob).hexdigest() != digest
    ):
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            decoded = stream.read(MAX_EXPANDED + 1)
        if len(decoded) > MAX_EXPANDED:
            raise ValueError("ARCHIVE_EXPANSION_LIMIT")
        value = worker.decode(decoded)
    except (OSError, EOFError, worker.AcquisitionError):
        raise ValueError("INVALID_ARCHIVE") from None
    if (
        not isinstance(value, dict)
        or value.get("contract") not in {"private-acquisition/v2", "private-acquisition/v3"}
        or (value.get('contract') == 'private-acquisition/v3'
            and value.get('subject_key') != 'symbol:' + str(value.get('symbol')))
        or (value.get('contract') == 'private-acquisition/v2' and 'subject_key' in value)
        or value.get("provider_namespace") != config["provider_namespace"]
        or value.get("kind") != "fundamentals"
        or value.get("execution") != "CURRENT_ACQUISITION"
        or value.get("authority") != "UNPROMOTED"
        or value.get("prediction_eligible") is not False
        or value.get("completeness") not in {"COMPLETE", "INCOMPLETE"}
        or not clean(value.get("symbol"), 32)
        or not isinstance(value.get("captures"), list)
        or not 1 <= len(value["captures"]) <= 30
        or not isinstance(value.get("targets"), list)
        or not 1 <= len(value["targets"]) <= 30
    ):
        raise ValueError("INVALID_FUNDAMENTAL_ARCHIVE")
    try:
        slot, completed = worker.utc(value["slot"]), worker.utc(value["completed_at"])
    except (worker.AcquisitionError, KeyError):
        raise ValueError("INVALID_FUNDAMENTAL_ARCHIVE") from None
    raws, identities = {}, set()
    for capture in value["captures"]:
        if (
            not isinstance(capture, dict)
            or not isinstance(capture.get("request_index"), int)
            or capture["request_index"] in raws
        ):
            raise ValueError("INVALID_CAPTURE")
        try:
            raw = bytes.fromhex(capture["raw_hex"])
            received = worker.utc(capture["received_at"])
        except (KeyError, TypeError, ValueError, worker.AcquisitionError):
            raise ValueError("INVALID_CAPTURE") from None
        identity = hashlib.sha256(
            json.dumps(
                [config["provider_namespace"], capture.get("sha256"), capture["received_at"]],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            len(raw) > MAX_PAGE
            or hashlib.sha256(raw).hexdigest() != capture.get("sha256")
            or identity != capture.get("capture_id")
            or identity in identities
            or not slot <= received <= completed
        ):
            raise ValueError("INVALID_CAPTURE")
        identities.add(identity)
        raws[capture["request_index"]] = raw
    pages, used = {}, set()
    for target in value["targets"]:
        if (
            not isinstance(target, dict)
            or not isinstance(target.get("request_index"), int)
            or target["request_index"] not in raws
            or target["request_index"] in used
            or target.get("kind") not in KINDS
            or target["kind"] in pages
        ):
            raise ValueError("INVALID_CAPTURE_TARGET")
        try:
            pages[target["kind"]] = worker.decode(raws[target["request_index"]])
        except worker.AcquisitionError:
            pages[target["kind"]] = None
        used.add(target["request_index"])
    if used != set(raws):
        raise ValueError("UNREFERENCED_CAPTURE")
    return value, pages


def _checked(fields):
    for name in NUMERIC_FIELDS:
        value = fields[name]
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or abs(value) > 1e15
        ):
            raise ValueError("INVALID_FUNDAMENTAL_VALUE")
        fields[name] = float(value)
    for name in INT_FIELDS:
        value = fields[name]
        if value is None:
            continue
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 1900 <= value <= 2100
        ):
            raise ValueError("INVALID_FUNDAMENTAL_VALUE")
    for name in TEXT_FIELDS:
        value = fields[name]
        maximum = 3800 if name == "description" else 200
        valid = clean_text(value, maximum) if name == "description" else clean(value, maximum)
        if value is not None and not valid:
            raise ValueError("INVALID_FUNDAMENTAL_VALUE")
    if fields["shareholders"] is not None:
        try:
            holders = json.loads(fields["shareholders"])
        except (TypeError, ValueError):
            raise ValueError("INVALID_FUNDAMENTAL_VALUE") from None
        if (
            not isinstance(holders, list)
            or not 1 <= len(holders) <= 100
            or len(fields["shareholders"]) > 4000
            or any(
                not isinstance(holder, dict)
                or set(holder) != {"name", "pct"}
                or not clean(holder["name"], 200)
                or isinstance(holder["pct"], bool)
                or not isinstance(holder["pct"], (int, float))
                or not math.isfinite(holder["pct"])
                or not 0 < holder["pct"] <= 100
                for holder in holders
            )
        ):
            raise ValueError("INVALID_FUNDAMENTAL_VALUE")
    if fields["na"] is not None and fields["na"] <= 0:
        raise ValueError("INVALID_FUNDAMENTAL_VALUE")
    return fields


def build(blob, digest, config, index, *, as_of=None):
    symbols = validate_index(index, config["provider_namespace"])
    value, pages = verified_archive(blob, digest, config)
    completed = worker.utc(value["completed_at"])
    now = as_of or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now < completed:
        raise ValueError("INVALID_PROJECTION_CUTOFF")
    derived = frame.derive(
        value["symbol"],
        pages.get("stock"),
        pages.get("symlinks"),
        pages.get("financial"),
        pages,
    )
    c_name = symbols.get(value["symbol"])
    if c_name is None:
        raise ValueError("SYMBOL_NOT_MAPPED")
    computed = derived["computed"]
    fields = {
        "ext_name": derived["ext_name"],
        "sector": derived["sector"],
        "description": derived["description"],
        "shareholders": computed["shareholders"],
        **{name: computed[name] for name in NUMERIC_FIELDS},
        "fiscal_year": computed["fiscal_year"],
        "fy_est": computed["fy_est"],
    }
    _checked(fields)
    errors = [
        {"kind": kind}
        for kind, payload in sorted(pages.items())
        if payload is None
    ]
    for error in value.get("errors") or []:
        if (
            isinstance(error, dict)
            and clean(error.get("kind"), 32)
            and clean(error.get("code"), 80)
        ):
            errors.append({"kind": error["kind"], "code": error["code"]})
    document = {
        "contract": CONTRACT,
        "mode": "PROJECTION_ONLY",
        "provider_namespace": config["provider_namespace"],
        "archive_sha256": digest,
        "index_sha256": fingerprint(index),
        "built_at": now.astimezone(timezone.utc).isoformat(),
        "source_execution": value["execution"],
        "symbol": value["symbol"],
        "c_name": c_name,
        "fields": fields,
        "errors": errors,
        "completeness": (
            "COMPLETE"
            if value["completeness"] == "COMPLETE" and not errors
            else "INCOMPLETE"
        ),
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
    }
    encoded = canonical(document)
    if len(encoded.encode()) > 2 * 1024 * 1024:
        raise ValueError("FUNDAMENTAL_PROJECTION_LIMIT")
    document["candidate_sha256"] = fingerprint(document)
    return document
