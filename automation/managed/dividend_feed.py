"""Verified dividend-calendar archive -> projection rows.

No date, amount, confirmation state or company match is ever invented. Rows with
conflicting payment periods are retained as exclusions and never projected.
"""

from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import re

import dividend_calendar as calendar
import worker

CONTRACT = "dividend-projection/v1"
INDEX_CONTRACT = "private-dividend-index/v1"
MAX_PAGE = 4 * 1024 * 1024
MAX_EXPANDED = 24 * 1024 * 1024
MAX_ROWS = 2000
DATES = ("ex_date", "pay_date", "pay_date_end")


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


def validate_index(index, provider):
    if (
        not isinstance(index, dict)
        or index.get("contract") != INDEX_CONTRACT
        or index.get("provider_namespace") != provider
        or not isinstance(index.get("index"), dict)
        or not 1 <= len(index["index"]) <= MAX_ROWS
        or any(
            not clean(key, 200) or not clean(name, 200)
            for key, name in index["index"].items()
        )
    ):
        raise ValueError("INVALID_DIVIDEND_INDEX")
    return index["index"]


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
        or value.get("contract") != "private-acquisition/v2"
        or value.get("provider_namespace") != config["provider_namespace"]
        or value.get("kind") != "dividends"
        or value.get("execution") != "CURRENT_ACQUISITION"
        or value.get("authority") != "UNPROMOTED"
        or value.get("prediction_eligible") is not False
        or value.get("completeness") not in {"COMPLETE", "INCOMPLETE"}
        or not isinstance(value.get("captures"), list)
        or not 1 <= len(value["captures"]) <= 20
        or not isinstance(value.get("targets"), list)
        or not 1 <= len(value["targets"]) <= 20
    ):
        raise ValueError("INVALID_DIVIDEND_ARCHIVE")
    try:
        slot, completed = worker.utc(value["slot"]), worker.utc(value["completed_at"])
    except (worker.AcquisitionError, KeyError):
        raise ValueError("INVALID_DIVIDEND_ARCHIVE") from None
    raws = {}
    for index, capture in enumerate(value["captures"]):
        if not isinstance(capture, dict):
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
            or not slot <= received <= completed
        ):
            raise ValueError("INVALID_CAPTURE")
        raws[index] = (raw, received)
    pages, used, decode_errors = {}, set(), []
    for target in value["targets"]:
        if (
            not isinstance(target, dict)
            or not isinstance(target.get("request_index"), int)
            or target["request_index"] not in raws
            or target["request_index"] in used
            or not isinstance(target.get("year"), int)
            or isinstance(target.get("year"), bool)
            or not 1900 <= target["year"] <= 2100
            or target["year"] in pages
            or (
                target.get("charset") is not None
                and not clean(target.get("charset"), 40)
            )
        ):
            raise ValueError("INVALID_CAPTURE_TARGET")
        raw, _received = raws[target["request_index"]]
        try:
            pages[target["year"]] = calendar.decode_page(raw, target.get("charset"))
        except ValueError as error:
            pages[target["year"]] = None
            decode_errors.append({"year": target["year"], "code": str(error)})
        used.add(target["request_index"])
    if used != set(raws):
        raise ValueError("UNREFERENCED_CAPTURE")
    return value, pages, decode_errors


def _checked(record, *, require_company):
    if (
        (require_company and not clean(record["c_name"], 200))
        or (
            record["c_name"] is not None
            and not clean(record["c_name"], 200)
        )
        or not clean(record["issuer"], 200)
        or (
            record["amount"] is not None
            and (
                isinstance(record["amount"], bool)
                or not isinstance(record["amount"], (int, float))
                or not 0 < record["amount"] <= 1e12
            )
        )
        or not isinstance(record["confirmed"], bool)
        or (record["confirmed"] and not record["ex_date"])
        or any(
            record[field] is not None
            and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record[field])
            for field in DATES
        )
        or any(
            record[field] is not None and not clean(record[field], 100)
            for field in ("type", "frequency")
        )
    ):
        raise ValueError("INVALID_PROJECTED_ROW")
    return record


def _row(item, c_name):
    return _checked(
        {
            "c_name": c_name,
            "issuer": item["issuer"],
            "year": item["year"],
            "amount": item["amount"],
            "ex_date": item["ex_date"],
            "pay_date": item["pay_date"],
            "pay_date_end": item["pay_date_end"],
            "confirmed": item["confirmed"],
            "type": item["type"],
            "frequency": item["frequency"],
        },
        require_company=True,
    )


def _review_row(item, issue=None):
    record = {
        "c_name": item.get("c_name"),
        "issuer": item["issuer"],
        "year": item["year"],
        "amount": item["amount"],
        "ex_date": item["ex_date"],
        "pay_date": item["pay_date"],
        "pay_date_end": item["pay_date_end"],
        "confirmed": item["confirmed"],
        "type": item["type"],
        "frequency": item["frequency"],
    }
    if issue is not None:
        record["issue"] = issue
    return _checked(record, require_company=False)


def build(blob, digest, config, index, *, as_of=None):
    resolved = validate_index(index, config["provider_namespace"])
    value, pages, errors = verified_archive(blob, digest, config)
    completed = worker.utc(value["completed_at"])
    now = as_of or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now < completed:
        raise ValueError("INVALID_PROJECTION_CUTOFF")
    rows, excluded, unmatched = [], [], []
    by_year = {}
    for year in sorted(pages):
        page = pages[year]
        if page is None:
            by_year[str(year)] = {"rows": 0, "excluded": 1, "unmatched": 0}
            continue
        try:
            parsed = calendar.parse_calendar(page, year)
        except ValueError:
            errors.append({"year": year, "code": "CALENDAR_SHAPE_INVALID"})
            by_year[str(year)] = {"rows": 0, "excluded": 1, "unmatched": 0}
            continue
        for item in parsed:
            item["c_name"] = calendar.resolve(
                item["key"], resolved, item.get("ticker")
            )
        counts = {"rows": 0, "excluded": 0, "unmatched": 0}
        for item in parsed:
            if item.get("verification_issue"):
                excluded.append(_review_row(item, item["verification_issue"]))
                counts["excluded"] += 1
            elif not item["c_name"]:
                unmatched.append(_review_row(item))
                counts["unmatched"] += 1
        matched = calendar.dedupe(
            [
                item
                for item in parsed
                if item["c_name"] and not item.get("verification_issue")
            ]
        )
        for item in matched:
            rows.append(_row(item, item["c_name"]))
            counts["rows"] += 1
        by_year[str(year)] = counts
    keys = [(row["c_name"], row["year"], row["type"]) for row in rows]
    if len(keys) != len(set(keys)) or len(rows) > MAX_ROWS:
        raise ValueError("DUPLICATE_DIVIDEND_ROWS")
    rows.sort(key=lambda row: (row["year"], row["c_name"], row["type"] or ""))
    document = {
        "contract": CONTRACT,
        "mode": "PROJECTION_ONLY",
        "provider_namespace": config["provider_namespace"],
        "archive_sha256": digest,
        "index_sha256": fingerprint(index),
        "built_at": now.astimezone(timezone.utc).isoformat(),
        "source_execution": value["execution"],
        "years": sorted(pages),
        "rows": rows,
        "excluded": excluded,
        "unmatched": unmatched,
        "errors": errors,
        "coverage": {
            "rows": len(rows),
            "excluded": len(excluded),
            "unmatched": len(unmatched),
            "by_year": by_year,
        },
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
        raise ValueError("DIVIDEND_PROJECTION_LIMIT")
    document["candidate_sha256"] = fingerprint(document)
    return document
