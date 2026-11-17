"""Verified archive -> shadow application quotes. Never updates recovered history."""

from collections import Counter
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import re
import sqlite3

import market_collect
from market_frame import FrameError
import worker


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True
    )


def clean(value, maximum=200):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and not any(ord(c) < 32 for c in value)
    )


def validate_mapping(mapping, config):
    market_collect.validate(config)
    if (
        not isinstance(mapping, dict)
        or mapping.get("contract") != "private-app-mapping/v1"
        or mapping.get("provider_namespace") != config["provider_namespace"]
    ):
        raise FrameError("INVALID_APP_MAPPING")
    for kind, expected in [
        ("stocks", config["recipe"]["expected_stock_identities"]),
        ("indices", config["recipe"]["expected_index_identities"]),
    ]:
        rows = mapping.get(kind)
        if not isinstance(rows, list) or len(rows) != len(expected):
            raise FrameError("MAPPING_UNIVERSE_MISMATCH")
        identities = []
        for row in rows:
            keys = {"source_identity", "asset_key", "c_name", "symbol", "company_id"}
            if not isinstance(row, dict) or set(row) != keys:
                raise FrameError("INVALID_APP_MAPPING_ROW")
            if any(not clean(row[k]) for k in keys - {"company_id"}):
                raise FrameError("INVALID_APP_MAPPING_ROW")
            if kind == "stocks" and (
                not clean(row["company_id"])
                or row["asset_key"] != "company:" + row["company_id"]
            ):
                raise FrameError("INVALID_COMPANY_IDENTITY")
            if kind == "indices" and (
                row["company_id"] is not None
                or not row["asset_key"].startswith("index:")
            ):
                raise FrameError("INVALID_INDEX_IDENTITY")
            identities.append(row["source_identity"])
        if len(set(identities)) != len(rows) or set(identities) != set(expected):
            raise FrameError("MAPPING_UNIVERSE_MISMATCH")
    all_rows = mapping["stocks"] + mapping["indices"]
    for key in ["asset_key", "c_name", "symbol"]:
        if len({row[key] for row in all_rows}) != len(all_rows):
            raise FrameError("AMBIGUOUS_APP_MAPPING")


def verified_archive(blob, digest, config, *, allow_legacy_replay_ids=False):
    if (
        len(blob) > worker.MAX_BATCH
        or not isinstance(digest, str)
        or hashlib.sha256(blob).hexdigest() != digest
    ):
        raise FrameError("ARCHIVE_HASH_MISMATCH")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            decoded = stream.read(24 * 1024 * 1024 + 1)
        if len(decoded) > 24 * 1024 * 1024:
            raise FrameError("ARCHIVE_EXPANSION_LIMIT")
        value = worker.decode(decoded)
    except (OSError, EOFError, worker.AcquisitionError):
        raise FrameError("INVALID_ARCHIVE") from None
    if (
        not isinstance(value, dict)
        or value.get("contract") != "private-acquisition/v2"
        or value.get("provider_namespace") != config["provider_namespace"]
        or value.get("kind") != "quotes"
        or value.get("authority") != "UNPROMOTED"
        or value.get("prediction_eligible") is not False
        or value.get("execution") not in {"CURRENT_ACQUISITION", "RECORDED_REPLAY"}
        or not isinstance(value.get("captures"), list)
        or len(value["captures"]) != 1
    ):
        raise FrameError("INVALID_QUOTE_ARCHIVE")
    capture = value["captures"][0]
    try:
        raw = bytes.fromhex(capture["raw_hex"])
        captured = worker.utc(capture["received_at"])
        slot, completed = worker.utc(value["slot"]), worker.utc(value["completed_at"])
    except (ValueError, KeyError, TypeError, worker.AcquisitionError):
        raise FrameError("INVALID_ARCHIVE_CAPTURE") from None
    if (
        len(raw) > worker.MAX_BODY
        or hashlib.sha256(raw).hexdigest() != capture.get("sha256")
        or not slot <= captured <= completed
    ):
        raise FrameError("ARCHIVE_CAPTURE_MISMATCH")
    rebuilt = market_collect.envelope(
        config, raw, captured, value["slot"], execution=value["execution"]
    )
    comparable_frame = rebuilt["market_frame"]
    identity_evidence = "NORMALIZER_IDS_VERIFIED"
    if (
        "capture_id" not in capture
        and allow_legacy_replay_ids
        and value["execution"] == "RECORDED_REPLAY"
    ):
        original_frame = value.get("market_frame")
        original_rows = (
            [row for rows in original_frame.get("views", {}).values() for row in rows]
            if isinstance(original_frame, dict)
            else []
        )
        if (
            not original_rows
            or any(
                not isinstance(row, dict) or "observation_id" in row
                for row in original_rows
            )
            or comparable_frame is None
        ):
            raise FrameError("UNSUPPORTED_LEGACY_IDENTITY_SHAPE")
        comparable_frame = copy.deepcopy(comparable_frame)
        for rows in comparable_frame["views"].values():
            for row in rows:
                del row["observation_id"]
        identity_evidence = "REPLAY_IDS_EXPLICITLY_DERIVED"
    elif rebuilt["captures"][0]["capture_id"] != capture.get("capture_id"):
        raise FrameError("ARCHIVE_NORMALIZATION_MISMATCH")
    if canonical(comparable_frame) != canonical(value.get("market_frame")) or rebuilt[
        "completeness"
    ] != value.get("completeness"):
        raise FrameError("ARCHIVE_NORMALIZATION_MISMATCH")
    if rebuilt["market_frame"] is None:
        raise FrameError("NO_NORMALIZED_MARKET_FRAME")
    return value, rebuilt["market_frame"], captured, identity_evidence


def build(
    blob,
    digest,
    config,
    mapping,
    *,
    as_of,
    capture_max_age_seconds=1200,
    allow_legacy_replay_ids=False,
):
    validate_mapping(mapping, config)
    value, frame, captured, identity_evidence = verified_archive(
        blob, digest, config, allow_legacy_replay_ids=allow_legacy_replay_ids
    )
    if (
        not isinstance(as_of, datetime)
        or as_of.tzinfo is None
        or as_of < captured
        or type(capture_max_age_seconds) is not int
        or not 1 <= capture_max_age_seconds <= 3600
    ):
        raise FrameError("INVALID_APP_CUTOFF")
    now = as_of.astimezone(timezone.utc)
    capture_day = captured.astimezone(worker.ZONE).date()
    current_day = now.astimezone(worker.ZONE).date()
    rows = []
    for kind, view in [("stocks", "quotes"), ("indices", "indices")]:
        for identity in mapping[kind]:
            observations = [
                row
                for row in frame["views"][view]
                if row["source_identity"] == identity["source_identity"]
            ]
            status = "MISSING_QUOTE"
            observed, display = None, None
            row = observations[0] if len(observations) == 1 else None
            if len(observations) > 1:
                status = "CONFLICTING_QUOTES"
            elif row is not None:
                observed = row["price_decimal"]
                if not row["source_date_matches_capture"]:
                    status = "STALE_OR_MISSING_SOURCE_DATE"
                elif capture_day != current_day:
                    status = "STALE_CAPTURE_DATE"
                elif (now - captured).total_seconds() >= capture_max_age_seconds:
                    status = "STALE_CAPTURE"
                elif row.get("source_event_at") is not None and (
                    now - worker.utc(row["source_event_at"])
                ).total_seconds() >= config["recipe"].get(
                    "max_event_age_seconds", 3600
                ):
                    status = "STALE_SOURCE_EVENT"
                else:
                    status = (
                        "REPORTED_EVENT_VERIFIED"
                        if row.get("source_event_at")
                        else "REPORTED_DATE_ONLY"
                    )
                    display = observed
            rows.append(
                {
                    "asset_key": identity["asset_key"],
                    "company_id": identity["company_id"],
                    "c_name": identity["c_name"],
                    "symbol": identity["symbol"],
                    "instrument_type": "STOCK" if kind == "stocks" else "INDEX",
                    "status": status,
                    "observed_price_decimal": observed,
                    "display_price_decimal": display,
                    "captured_at": row["captured_at"] if row else None,
                    "reported_time": row.get("reported_time") if row else None,
                    "source_event_at": row.get("source_event_at") if row else None,
                    "price_basis": "REPORTED_QUOTE",
                    "portfolio_valuation_eligible": False,
                    "prediction_eligible": False,
                    "observations": [
                        {
                            k: original.get(k)
                            for k in [
                                "observation_id",
                                "raw_row_index",
                                "price_decimal",
                                "captured_at",
                                "reported_time",
                                "source_event_at",
                            ]
                        }
                        for original in observations
                    ],
                }
            )
    candidate = {
        "contract": "app-market-candidate/v1",
        "mode": "SHADOW_ONLY",
        "provider_namespace": config["provider_namespace"],
        "archive_sha256": digest,
        "mapping_sha256": fingerprint(mapping),
        "recipe_sha256": fingerprint(config["recipe"]),
        "captured_at": captured.isoformat(),
        "as_of": now.isoformat(),
        "source_execution": value["execution"],
        "market_date": capture_day.isoformat(),
        "identity_evidence": identity_evidence,
        "capture_max_age_seconds": capture_max_age_seconds,
        "source_max_age_seconds": config["recipe"].get("max_event_age_seconds", 3600),
        "acquisition_completeness": frame["completeness"],
        "market_session_state": "UNKNOWN",
        "rows": rows,
        "coverage": dict(Counter(row["status"] for row in rows)),
        "portfolio_valuation_eligible": False,
        "prediction_eligible": False,
    }
    candidate["candidate_sha256"] = fingerprint(candidate)
    return candidate


def _reference_decimal(value):
    """Legacy positive-price rule without a float conversion or invented zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
        if len(text) > 128:
            return None
        number = Decimal(text)
        if number.is_finite() and Decimal('1e-28') <= number <= Decimal('1000000000000'):
            return format(number, 'f')
    except (InvalidOperation, ValueError):
        pass
    return None


def build_display_prices(blob, digest, config, mapping, *, as_of, last_known=()):
    """Port legacy quote -> instrument list -> saved-price display precedence.

    This is an opt-in display calculation, not the certified quote candidate.
    Catalog prices have unknown trade dates. Saved records keep their original
    record dates. Neither fallback becomes a fresh quote, valuation or model input.
    The accepted build() contract and its acquisition completeness are unchanged.
    """
    candidate = build(blob, digest, config, mapping, as_of=as_of)
    last_known = tuple(last_known)
    _, frame, captured, _ = verified_archive(blob, digest, config)
    cutoff = worker.utc(candidate['as_of'])
    instruments = {}
    for row in frame['views']['instruments']:
        instruments.setdefault(row['source_identity'], []).append(row)
    identities = {row['asset_key']: row for kind in ('stocks', 'indices') for row in mapping[kind]}
    output = []
    for quote in candidate['rows']:
        item = {key: quote[key] for key in ('asset_key', 'company_id', 'c_name', 'symbol', 'instrument_type')}
        item.update(price_decimal=None, price_basis='UNAVAILABLE', quote_status=quote['status'],
            fresh_quote_available=quote['display_price_decimal'] is not None,
            source_event_at=None, source_reported_day=None, captured_at=None,
            original_recorded_at=None, original_document_ids=[], observations=[],
            prediction_eligible=False, portfolio_valuation_eligible=False)
        # Keep a real observed quote even when showing it as a dated/stale value.
        observed = _reference_decimal(quote['observed_price_decimal'])
        if observed is not None and quote['status'] != 'CONFLICTING_QUOTES':
            item.update(price_decimal=observed, price_basis='OBSERVED_QUOTE',
                captured_at=quote['captured_at'], source_event_at=quote['source_event_at'],
                source_reported_day=(quote.get('reported_time') or {}).get('date'),
                observations=copy.deepcopy(quote['observations']))
        elif quote['status'] == 'MISSING_QUOTE' and quote['instrument_type'] == 'STOCK':
            refs = instruments.get(identities[quote['asset_key']]['source_identity'], [])
            positives = [(r, _reference_decimal(r.get('reported_price_decimal'))) for r in refs]
            positives = [(r, price) for r, price in positives if price is not None]
            if len({Decimal(price) for _, price in positives}) > 1:
                item['price_basis'] = 'CONFLICTING_INSTRUMENT_PRICES'
            elif positives:
                item.update(price_decimal=positives[0][1], price_basis='INSTRUMENT_REFERENCE',
                    captured_at=captured.isoformat(), observations=[{
                        'observation_id': r['observation_id'], 'raw_row_index': r['raw_row_index'],
                        'price_decimal': price,
                    } for r, price in positives])
            else:
                saved = []
                for record in last_known:
                    if record.get('c_name') != item['c_name'] or (record.get('symbol') and record['symbol'] != item['symbol']):
                        continue
                    price = _reference_decimal(record.get('pa'))
                    try:
                        recorded = worker.utc(record.get('date'))
                    except (ValueError, TypeError, worker.AcquisitionError):
                        continue
                    identifier = record.get('id', record.get('$id'))
                    if price is not None and recorded <= cutoff and clean(identifier):
                        saved.append((recorded, record, price))
                if saved:
                    latest = max(row[0] for row in saved)
                    heads = [row for row in saved if row[0] == latest]
                    if len({Decimal(row[2]) for row in heads}) > 1:
                        item['price_basis'] = 'CONFLICTING_SAVED_PRICES'
                    else:
                        item.update(price_decimal=heads[0][2], price_basis='RECOVERED_LAST_KNOWN',
                            original_recorded_at=latest.isoformat(),
                            original_document_ids=sorted({row[1].get('id', row[1].get('$id')) for row in heads}))
        output.append(item)
    return {'mode': 'REFERENCE_ONLY', 'as_of': candidate['as_of'],
        'archive_sha256': digest, 'captured_at': candidate['captured_at'],
        'acquisition_completeness': candidate['acquisition_completeness'],
        'rows': output, 'coverage': dict(Counter(row['price_basis'] for row in output)),
        'prediction_eligible': False, 'portfolio_valuation_eligible': False}


def build_with_references(blob, digest, config, mapping, *, as_of):
    """Opt-in v2 candidate: preserve quotes and attach dated-as-unknown references."""
    candidate = build(blob, digest, config, mapping, as_of=as_of)
    display = build_display_prices(blob, digest, config, mapping, as_of=as_of)
    candidate['contract'] = 'app-market-candidate/v2'
    for row, resolved in zip(candidate['rows'], display['rows']):
        row['reference_price'] = None
        row['reference_conflict'] = resolved['price_basis'] == 'CONFLICTING_INSTRUMENT_PRICES'
        if resolved['price_basis'] == 'INSTRUMENT_REFERENCE':
            row['reference_price'] = {
                'price_decimal': resolved['price_decimal'],
                'price_basis': 'INSTRUMENT_REFERENCE',
                'captured_at': resolved['captured_at'],
                'source_event_at': None, 'reported_day': None,
                'observations': resolved['observations'],
                'prediction_eligible': False, 'portfolio_valuation_eligible': False,
            }
    del candidate['candidate_sha256']
    candidate['candidate_sha256'] = fingerprint(candidate)
    return candidate


class IsolatedFeedStore:
    """Bounded latest candidate per explicitly allowed provider; no genuine ledgers."""

    def __init__(self, path, allowed_providers):
        if (
            not isinstance(allowed_providers, set)
            or not 1 <= len(allowed_providers) <= 8
            or any(
                not re.fullmatch(r"feed_[a-f0-9]{16}", key) for key in allowed_providers
            )
        ):
            raise FrameError("INVALID_APP_PROVIDER_ALLOWLIST")
        self.allowed = allowed_providers
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS shadow_feed(provider TEXT PRIMARY KEY,captured_at TEXT,archive_digest TEXT,candidate_digest TEXT,body TEXT)"
        )

    def save(self, candidate):
        body = {k: v for k, v in candidate.items() if k != "candidate_sha256"}
        if (
            candidate.get("contract") != "app-market-candidate/v1"
            or candidate.get("mode") != "SHADOW_ONLY"
            or candidate.get("provider_namespace") not in self.allowed
            or candidate.get("candidate_sha256") != fingerprint(body)
            or candidate.get("prediction_eligible") is not False
            or candidate.get("portfolio_valuation_eligible") is not False
        ):
            raise FrameError("INVALID_SHADOW_CANDIDATE")
        encoded = canonical(candidate)
        if len(encoded.encode()) > 2 * 1024 * 1024:
            raise FrameError("APP_CANDIDATE_LIMIT")
        stamp = worker.utc(candidate["captured_at"])
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute(
                "SELECT captured_at,candidate_digest FROM shadow_feed WHERE provider=?",
                (candidate["provider_namespace"],),
            ).fetchone()
            if old:
                if stamp < worker.utc(old[0]):
                    raise FrameError("OLDER_FEED_REJECTED")
                if stamp == worker.utc(old[0]):
                    if old[1] == candidate["candidate_sha256"]:
                        return "ALREADY_STORED"
                    raise FrameError("EQUAL_TIME_FEED_CONFLICT")
            self.db.execute(
                "INSERT OR REPLACE INTO shadow_feed VALUES(?,?,?,?,?)",
                (
                    candidate["provider_namespace"],
                    stamp.isoformat(),
                    candidate["archive_sha256"],
                    candidate["candidate_sha256"],
                    encoded,
                ),
            )
        return "STORED"
