"""Strict historical close reader for the private versioned SQL archive.

This is a privileged backend/research reader, not a public API or live adapter.
Rows remain retrospective candidates with UNKNOWN original observation times.
No preceding-day fallback, mixed versions, duplicate selection or authority grant.
"""

from datetime import date
from decimal import Decimal
import re


def historical_closes(db, batch_id, namespace, period_day, expected_symbols):
    if not re.fullmatch("[a-f0-9]{64}", batch_id):
        raise ValueError("Invalid batch identity")
    day = date.fromisoformat(period_day)
    if day.isoformat() != period_day:
        raise ValueError("Invalid economic date")
    symbols = tuple(expected_symbols)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Explicit unique instrument universe required")
    batch = db.execute(
        "SELECT manifest FROM market_history_v1.batches WHERE batch_id=%s", (batch_id,)
    ).fetchone()
    if not batch or batch[0].get("namespace") != namespace:
        raise ValueError("Source namespace mismatch")
    if (
        batch[0].get("contract") != "private-source-history-v1"
        or batch[0].get("classification") != "RETROSPECTIVE_SOURCE_HISTORY"
        or batch[0].get("production_eligible") is not False
    ):
        raise ValueError("Unsupported history contract")
    observations = db.execute(
        """
        SELECT o.symbol,o.observation_id,o.source_ordinal,o.close_text,
               o.source_daily_label,o.quality_warnings,o.observed_at,
               o.observation_time_status,o.price_definition,c.completed_at,c.raw_sha256
        FROM market_history_v1.observations o
        JOIN market_history_v1.captures c USING(batch_id,symbol)
        WHERE o.batch_id=%s AND o.period_day=%s
        ORDER BY o.symbol,o.source_ordinal
    """,
        (batch_id, day),
    ).fetchall()
    grouped = {symbol: [] for symbol in symbols}
    for row in observations:
        if row[0] in grouped:
            grouped[row[0]].append(row)
    missing = sorted(symbol for symbol, values in grouped.items() if not values)
    duplicates = sorted(symbol for symbol, values in grouped.items() if len(values) > 1)
    result = {
        "contract": "retrospective-close-query-v1",
        "batch_id": batch_id,
        "namespace": namespace,
        "market_date": period_day,
        "classification": "RETROSPECTIVE_SOURCE_HISTORY",
        "production_eligible": False,
        "original_observation_times": "UNKNOWN",
        "missing_symbols": missing,
        "duplicate_symbols": duplicates,
        "readiness": "HISTORICAL_CLOSES_AVAILABLE",
        "prices": [],
    }
    if missing or duplicates:
        result["readiness"] = "HISTORICAL_CLOSES_INCOMPLETE_OR_AMBIGUOUS"
        return result
    for symbol in symbols:
        row = grouped[symbol][0]
        close = Decimal(row[3])
        if (
            not close.is_finite()
            or close <= 0
            or row[6] is not None
            or row[7] != "UNKNOWN"
            or row[8] != "PROVIDER_DAILY_CLOSE_CANDIDATE"
        ):
            raise ValueError("Invalid historical close provenance")
        result["prices"].append(
            {
                "symbol": symbol,
                "observation_id": row[1],
                "source_ordinal": row[2],
                "close_decimal": row[3],
                "source_daily_label": row[4],
                "quality_warnings": row[5],
                "observed_at": None,
                "capture_completed_at": row[9].isoformat(),
                "raw_sha256": row[10],
            }
        )
    return result
