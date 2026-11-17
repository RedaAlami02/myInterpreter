"""Provider-neutral depth normalization and immutable batch manifests.

Paths live in private recipes. Empty books, auction-like crossings and source
clock text are retained; they are not silently repaired or called tradable.
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from market_frame import FrameError, extract, get, read_json, valid_path

SIDE_FIELDS = {"price_decimal", "quantity_decimal", "orders_decimal", "level_time_text"}
SUMMARY_FIELDS = {
    "source_identity",
    "reported_time",
    "last_trade_price_decimal",
    "state_code",
    "phase_code",
}


def validate_spec(spec):
    if not isinstance(spec, dict) or not valid_path(spec.get("summary_path")):
        raise FrameError("INVALID_DEPTH_RECIPE")
    fields = spec.get("summary_fields")
    if (
        not isinstance(fields, dict)
        or not {"source_identity"}.issubset(fields)
        or set(fields) - SUMMARY_FIELDS
    ):
        raise FrameError("INVALID_DEPTH_RECIPE")
    for side in ["bids", "asks"]:
        view = spec.get(side, {})
        if (
            not isinstance(view, dict)
            or not valid_path(view.get("rows_path"))
            or not isinstance(view.get("fields"), dict)
            or not {"price_decimal", "quantity_decimal"}.issubset(view["fields"])
            or set(view["fields"]) - SIDE_FIELDS
        ):
            raise FrameError("INVALID_DEPTH_RECIPE")
    for fields in [fields, spec["bids"]["fields"], spec["asks"]["fields"]]:
        for name, binding in fields.items():
            expected = (
                "decimal"
                if name.endswith("_decimal")
                else "reported_time"
                if name == "reported_time"
                else "code"
                if name.endswith("_code")
                else "text"
            )
            if (
                not isinstance(binding, dict)
                or not valid_path(binding.get("path"))
                or binding.get("type") != expected
            ):
                raise FrameError("INVALID_DEPTH_BINDING")


def normalize(raw, spec, expected_identity, captured_at):
    validate_spec(spec)
    if (
        captured_at.tzinfo is None
        or not isinstance(expected_identity, str)
        or not 1 <= len(expected_identity) <= 200
    ):
        raise FrameError("INVALID_DEPTH_CAPTURE")
    document = read_json(raw)
    for check in spec.get("checks", []):
        actual = get(document, check["path"])
        if type(actual) is not type(check["equals"]) or actual != check["equals"]:
            raise FrameError("SOURCE_SECTION_INVALID")
    summary = get(document, spec["summary_path"])
    values = {
        key: extract(binding, summary, document) for key, binding in spec["summary_fields"].items()
    }
    if values["source_identity"] != expected_identity:
        raise FrameError("RESPONSE_SECURITY_MISMATCH")
    issues = []
    last = values.get("last_trade_price_decimal")
    if last is not None and not 0 <= Decimal(last) <= Decimal("1e12"):
        issues.append({"code": "INVALID_LAST_TRADE_PRICE"})
    sides = {}
    for side in ["bids", "asks"]:
        view = spec[side]
        rows = get(document, view["rows_path"])
        if not isinstance(rows, list) or len(rows) > 5:
            raise FrameError("INVALID_DEPTH_LEVEL_COUNT")
        output = []
        for index, row in enumerate(rows):
            try:
                level = {
                    key: extract(view["fields"][key], row, document)
                    for key in ["price_decimal", "quantity_decimal"]
                }
                p, q = level["price_decimal"], level["quantity_decimal"]
                if (p is None or Decimal(p) == 0) and (q is None or Decimal(q) == 0):
                    continue
                level.update(
                    {
                        key: extract(binding, row, document)
                        for key, binding in view["fields"].items()
                        if key not in level
                    }
                )
                if p is None or q is None or not 0 < Decimal(p) <= Decimal("1e12"):
                    raise FrameError("INVALID_DEPTH_PRICE")
                quantity = Decimal(q)
                if not 0 < quantity <= Decimal("1e12") or quantity != quantity.to_integral_value():
                    raise FrameError("INVALID_DEPTH_QUANTITY")
                if level.get("orders_decimal") is not None:
                    orders = Decimal(level["orders_decimal"])
                    if not 0 < orders <= Decimal("1e12") or orders != orders.to_integral_value():
                        raise FrameError("INVALID_DEPTH_ORDER_COUNT")
                level["raw_level_index"] = index
                output.append(level)
            except FrameError as error:
                issues.append({"side": side, "raw_level_index": index, "code": str(error)})
        prices = [Decimal(row["price_decimal"]) for row in output]
        if prices != sorted(prices, reverse=side == "bids"):
            issues.append({"side": side, "code": "UNORDERED_SOURCE_LEVELS"})
        sides[side] = output
    bid = sides["bids"][0]["price_decimal"] if sides["bids"] else None
    ask = sides["asks"][0]["price_decimal"] if sides["asks"] else None
    crossed = bid is not None and ask is not None and Decimal(bid) > Decimal(ask)
    empty = not sides["bids"] and not sides["asks"]
    return {
        "contract": "private-depth-frame/v2",
        "source_identity": expected_identity,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
        "summary": values,
        **sides,
        "issues": issues,
        "book_state": "EMPTY" if empty else "CROSSED_UNCLASSIFIED" if crossed else "REPORTED",
        "completeness": "INCOMPLETE" if issues else "COMPLETE",
        "source_timezone": "UNKNOWN",
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }


def manifest(namespace, expected, attempts, *, started_at, finished_at):
    if (
        not isinstance(namespace, str)
        or re.fullmatch(r"feed_[a-f0-9]{16}", namespace) is None
        or not isinstance(expected, list)
        or not expected
        or len(set(expected)) != len(expected)
        or any(not isinstance(identity, str) or not identity for identity in expected)
        or started_at.tzinfo is None
        or finished_at.tzinfo is None
        or finished_at < started_at
    ):
        raise FrameError("INVALID_DEPTH_BATCH")
    expected_set = set(expected)
    seen = {}
    errors = []
    entries = []
    for attempt in attempts:
        identity = attempt.get("source_identity")
        if identity not in expected_set:
            errors.append({"code": "UNEXPECTED_SECURITY"})
            frame = attempt.get("frame")
            entries.append(
                {
                    "source_identity": identity,
                    "status": "UNEXPECTED",
                    "raw_sha256": frame.get("raw_sha256") if isinstance(frame, dict) else None,
                    "captured_at": frame.get("captured_at") if isinstance(frame, dict) else None,
                }
            )
            continue
        if identity in seen:
            errors.append({"code": "DUPLICATE_SECURITY_CAPTURE"})
        seen[identity] = True
        frame = attempt.get("frame")
        if frame is not None and (
            frame.get("source_identity") != identity
            or frame.get("contract") != "private-depth-frame/v2"
        ):
            errors.append({"code": "FRAME_SECURITY_MISMATCH"})
            frame = None
        if frame is not None:
            stamp = datetime.fromisoformat(frame["captured_at"])
            if not started_at <= stamp <= finished_at:
                errors.append({"code": "CAPTURE_OUTSIDE_BATCH"})
        entries.append(
            {
                "source_identity": identity,
                "status": frame["completeness"] if frame else "FAILED",
                "raw_sha256": frame["raw_sha256"] if frame else attempt.get("raw_sha256"),
                "captured_at": frame["captured_at"] if frame else attempt.get("captured_at"),
                **({"error_code": attempt["code"]} if "code" in attempt else {}),
            }
        )
    missing = sorted(expected_set - set(seen))
    complete = (
        not missing
        and not errors
        and len(entries) == len(expected)
        and all(entry["status"] == "COMPLETE" for entry in entries)
    )
    content = {
        "contract": "private-depth-batch/v2",
        "provider_namespace": namespace,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "finished_at": finished_at.astimezone(timezone.utc).isoformat(),
        "expected": len(expected),
        "attempted": len(attempts),
        "entries": entries,
        "missing_identities": missing,
        "issues": errors,
        "completeness": "COMPLETE" if complete else "INCOMPLETE",
        "prediction_eligible": False,
        "authority": "UNPROMOTED",
    }
    content["manifest_sha256"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return content
