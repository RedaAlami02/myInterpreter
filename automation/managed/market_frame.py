"""Versioned normalization of private market recipes, with no source assumptions.

Native paths/formats belong to ignored configuration. A response receipt is not
an exchange timestamp. Normalization never confers authority or permits inference.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from zoneinfo import ZoneInfo

CONTRACT = "private-market-frame/v2"
VIEWS = {"instruments", "quotes", "indices", "status"}
FORMATS = {"%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"}
FIELDS = {
    "instruments": {"source_identity", "display_name", "reported_price_decimal"},
    "quotes": {"source_identity", "price_decimal", "reported_time", "source_event_at"},
    "indices": {"source_identity", "price_decimal", "reported_time", "source_event_at"},
    "status": {"state_code", "state_text", "reported_time"},
}
REQUIRED = {
    "instruments": {"source_identity"},
    "quotes": {"source_identity", "price_decimal"},
    "indices": {"source_identity", "price_decimal"},
    "status": {"state_code"},
}


class FrameError(ValueError):
    pass


def read_json(raw):
    def invalid(_):
        raise FrameError("INVALID_JSON")

    try:
        return json.loads(raw, parse_float=Decimal, parse_constant=invalid)
    except (ValueError, UnicodeError):
        raise FrameError("INVALID_JSON") from None


def get(value, path):
    try:
        for item in path:
            value = value[item]
        return value
    except (KeyError, IndexError, TypeError):
        raise FrameError("MISSING_FIELD") from None


def valid_path(value):
    return (
        isinstance(value, list)
        and len(value) <= 12
        and all(isinstance(key, str) or (type(key) is int and key >= 0) for key in value)
    )


def recipe_check(recipe):
    views = recipe.get("views") if isinstance(recipe, dict) else None
    if not isinstance(views, dict) or set(views) != VIEWS:
        raise FrameError("INVALID_VIEWS")
    expected = recipe.get("expected_stock_identities")
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) > 2000
        or any(not isinstance(item, str) or not 1 <= len(item) <= 200 for item in expected)
        or len(set(expected)) != len(expected)
    ):
        raise FrameError("INVALID_EXPECTED_UNIVERSE")
    indices = recipe.get("expected_index_identities")
    if (
        not isinstance(indices, list)
        or not indices
        or any(not isinstance(item, str) or not 1 <= len(item) <= 200 for item in indices)
        or len(set(indices)) != len(indices)
    ):
        raise FrameError("INVALID_EXPECTED_INDICES")
    if (
        type(recipe.get("max_event_age_seconds", 3600)) is not int
        or not 1 <= recipe.get("max_event_age_seconds", 3600) <= 86400
    ):
        raise FrameError("INVALID_EVENT_AGE_LIMIT")
    for kind, spec in views.items():
        fields = spec.get("fields") if isinstance(spec, dict) else None
        constants = spec.get("constants", {}) if isinstance(spec, dict) else {}
        if (
            not isinstance(fields, dict)
            or set(fields) - FIELDS[kind]
            or not isinstance(constants, dict)
            or set(constants) - {"source_identity"}
            or set(constants) & set(fields)
            or not valid_path(spec.get("rows_path"))
            or not REQUIRED[kind].issubset(set(fields) | set(constants))
        ):
            raise FrameError("INVALID_BINDING")
        if constants and kind not in {"indices"}:
            raise FrameError("INVALID_CONSTANT")
        for name, binding in fields.items():
            if (
                not isinstance(binding, dict)
                or not valid_path(binding.get("path"))
                or binding.get("type")
                not in {"text", "code", "decimal", "reported_time", "aware_time"}
            ):
                raise FrameError("INVALID_BINDING")
            if binding["type"] == "reported_time" and binding.get("format") not in FORMATS:
                raise FrameError("INVALID_TIME_FORMAT")
            if binding["type"] == "decimal" and binding.get("locale", "plain") not in {
                "plain",
                "comma",
                "comma_dot_grouping",
            }:
                raise FrameError("INVALID_NUMBER_FORMAT")
            if binding.get("scope", "row") not in {"row", "document"}:
                raise FrameError("INVALID_BINDING")
            expected_type = (
                "decimal"
                if name.endswith("_decimal")
                else "reported_time"
                if name == "reported_time"
                else "aware_time"
                if name == "source_event_at"
                else "code"
                if name == "state_code"
                else "text"
            )
            if binding["type"] != expected_type:
                raise FrameError("INVALID_FIELD_TYPE")
        for check in spec.get("checks", []):
            if (
                not isinstance(check, dict)
                or not valid_path(check.get("path"))
                or set(check) != {"path", "equals"}
            ):
                raise FrameError("INVALID_VALIDITY_CHECK")


def decimal_value(value, locale):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise FrameError("INVALID_NUMBER")
    text = str(value)
    if isinstance(value, str):
        if locale == "plain":
            pattern = r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
        elif locale == "comma":
            pattern = r"[+-]?(?:\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:,\d+)?"
        else:
            pattern = r"[+-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?"
        if not re.fullmatch(pattern, text):
            raise FrameError("INVALID_NUMBER")
        if locale == "comma_dot_grouping":
            text = text.replace(".", "")
        if locale != "plain":
            text = re.sub(r"[ \u00a0\u202f]", "", text).replace(",", ".")
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise FrameError("INVALID_NUMBER") from None
    if (
        not result.is_finite()
        or result.adjusted() > 28
        or result.as_tuple().exponent < -28
        or len(result.as_tuple().digits) > 40
    ):
        raise FrameError("INVALID_NUMBER")
    return format(result, "f")


def extract(binding, row, document):
    try:
        value = get(document if binding.get("scope") == "document" else row, binding["path"])
    except FrameError:
        if binding.get("optional") is True:
            return None
        raise
    if (value is None or (value == "" and binding.get("blank_is_null") is True)) and binding.get(
        "optional"
    ) is True:
        return None
    kind = binding["type"]
    if kind == "decimal":
        return decimal_value(value, binding.get("locale", "plain"))
    if kind == "code":
        if type(value) is int:
            return str(value)
        if isinstance(value, str) and 1 <= len(value) <= 100:
            return value
        raise FrameError("INVALID_CODE")
    if not isinstance(value, str) or not 1 <= len(value) <= 500:
        raise FrameError("INVALID_TEXT")
    if kind == "text":
        return value
    if kind == "aware_time":
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError()
            return stamp.astimezone(timezone.utc).isoformat()
        except ValueError:
            raise FrameError("UNKNOWN_TIMEZONE") from None
    try:
        stamp = datetime.strptime(value, binding["format"])
        if stamp.strftime(binding["format"]) != value:
            raise ValueError()
    except ValueError:
        raise FrameError("INVALID_REPORTED_TIME") from None
    # Calendar extraction is allowed; UTC conversion of a naive source time is not.
    return {"text": value, "date": stamp.date().isoformat(), "timezone": "UNKNOWN", "utc": None}


def normalize(raw, recipe, captured_at, *, market_date):
    recipe_check(recipe)
    if captured_at.tzinfo is None or type(market_date) is not date:
        raise FrameError("INVALID_CAPTURE_TIME")
    document = read_json(raw)
    captured = captured_at.astimezone(timezone.utc)
    # Source clock stays unknown; only actual receipt is converted to business time.
    if market_date != captured.astimezone(ZoneInfo("Africa/Casablanca")).date():
        raise FrameError("INVALID_MARKET_DATE")
    views = {}
    issues = []
    for kind, spec in recipe["views"].items():
        output = []
        try:
            for check in spec.get("checks", []):
                actual = get(document, check["path"])
                if type(actual) is not type(check["equals"]) or actual != check["equals"]:
                    raise FrameError("SOURCE_SECTION_INVALID")
            rows = get(document, spec["rows_path"])
            if not isinstance(rows, list) or not rows or len(rows) > 5000:
                raise FrameError("EMPTY_OR_INVALID_VIEW")
            for index, row in enumerate(rows):
                try:
                    values = {
                        name: extract(binding, row, document)
                        for name, binding in spec["fields"].items()
                    }
                    values.update(spec.get("constants", {}))
                    if any(values.get(name) is None for name in REQUIRED[kind]):
                        raise FrameError("MISSING_REQUIRED_VALUE")
                    identity = values.get("source_identity")
                    if identity is not None and (
                        not isinstance(identity, str) or not 1 <= len(identity) <= 200
                    ):
                        raise FrameError("INVALID_IDENTITY")
                    price = values.get("price_decimal")
                    if price is not None and not 0 < Decimal(price) <= Decimal("1e12"):
                        raise FrameError("INVALID_PRICE")
                    values.update(raw_row_index=index, captured_at=captured.isoformat())
                    if kind in {"quotes", "indices"}:
                        reported = values.get("reported_time")
                        event = values.get("source_event_at")
                        if event is not None:
                            parsed = datetime.fromisoformat(event)
                            if parsed > captured:
                                raise FrameError("FUTURE_SOURCE_EVENT")
                            if (captured - parsed).total_seconds() > recipe.get(
                                "max_event_age_seconds", 3600
                            ):
                                raise FrameError("STALE_SOURCE_EVENT")
                        values["source_date_matches_capture"] = bool(
                            reported and reported["date"] == market_date.isoformat()
                        )
                        values["price_basis"] = "REPORTED_QUOTE"
                        values["source_timezone_known"] = event is not None
                        values["authority"] = "UNPROMOTED"
                    output.append(values)
                except FrameError as error:
                    issues.append({"view": kind, "row_index": index, "code": str(error)})
        except FrameError as error:
            issues.append({"view": kind, "code": str(error)})
        views[kind] = output
    expected = set(recipe["expected_stock_identities"])
    for kind in ["instruments", "quotes", "indices"]:
        identities = [row["source_identity"] for row in views[kind]]
        if len(identities) != len(set(identities)):
            issues.append({"view": kind, "code": "CONFLICTING_IDENTITIES"})
    references = {row["source_identity"] for row in views["instruments"]}
    observed = {row["source_identity"] for row in views["quotes"]}
    dated = {
        row["source_identity"] for row in views["quotes"] if row["source_date_matches_capture"]
    }
    index_ids = {row["source_identity"] for row in views["indices"]}
    index_current = index_ids == set(recipe["expected_index_identities"]) and all(
        row["source_date_matches_capture"] for row in views["indices"]
    )
    coverage = {
        "expected_stocks": len(expected),
        "referenced_stocks": len(references),
        "observed_stocks": len(observed),
        "same_date_stocks": len(dated),
        "missing_quote_identities": sorted(expected - observed),
        "missing_same_date_identities": sorted(expected - dated),
        "unexpected_identities": sorted((observed | references) - expected),
        "reference_universe_complete": references == expected,
        "quote_universe_complete": observed == expected,
        "same_date_quote_universe_complete": dated == expected,
        "index_same_date": index_current,
    }
    complete = not issues and references == expected and dated == expected and index_current
    return {
        "contract": CONTRACT,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at": captured.isoformat(),
        "market_date": market_date.isoformat(),
        "views": views,
        "issues": issues,
        "coverage": coverage,
        "completeness": "COMPLETE" if complete else "INCOMPLETE",
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
    }
