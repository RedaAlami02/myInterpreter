"""Append-only forward prediction/outcome ledger for frozen V3 validation."""

from __future__ import annotations

import csv
from pathlib import Path


PREDICTION_FIELDS = [
    "record_id", "created_at", "market_date", "model_hashes", "data_hash",
    "symbol", "company", "score_5d", "signal_rank_5d", "actionable_rank_5d",
    "score_20d", "signal_rank_20d", "model_agreement_5d",
    "tradability_class", "trade_evidence_status", "execution_policy",
    "intended_order", "confidence",
]

OUTCOME_FIELDS = [
    "outcome_id", "prediction_record_id", "appended_at", "label_end_date",
    "realized_5d_excess", "execution_status", "entry_date", "exit_date",
    "execution_aware_return", "notes",
]


def _existing_keys(path: Path, field: str) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="") as handle:
        return {row[field] for row in csv.DictReader(handle)}


def append_rows(path: Path, rows: list[dict], fields: list[str], key: str) -> None:
    """Append unique immutable records; existing rows are never rewritten."""
    existing = _existing_keys(path, key)
    incoming = [str(row[key]) for row in rows]
    if len(incoming) != len(set(incoming)) or existing.intersection(incoming):
        raise ValueError(f"Duplicate immutable ledger key: {key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def initialize_ledger(path: Path, fields: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writeheader()

