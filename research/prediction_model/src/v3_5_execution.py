"""Point-in-time trade evidence and execution timing for the frozen V3 audit."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .common import PROJECT_ROOT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_v3(config: dict) -> None:
    for relative, expected in config["frozen_v3_artifacts"].items():
        actual = sha256(PROJECT_ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"Frozen V3 artifact changed: {relative}: {actual} != {expected}")


def attach_trade_evidence(panel: pd.DataFrame) -> pd.DataFrame:
    """Classify evidence without treating a price change as proof of a trade."""
    output = panel.sort_values(["c_name", "date"]).copy()
    verified = output["volume"].gt(0) | output["qty_traded"].gt(0)
    likely = (
        ~verified
        & output["volume_known"]
        & (
            output["high"].gt(output["low"])
            | output["open_price"].ne(output["pa"])
        )
    )
    stale = ~verified & ~likely & output["stale_price_flag"]
    output["trade_evidence_status"] = np.select(
        [verified, likely, stale],
        ["VERIFIED_TRADED", "LIKELY_TRADED", "STALE_OR_NO_EVIDENCE"],
        default="UNKNOWN",
    )
    output["verified_trade"] = verified
    output["latest_known_volume"] = output["volume"].where(output["volume_known"])
    output["latest_known_qty_traded"] = output["qty_traded"].where(
        output["volume_known"]
    )
    verified_date = output["date"].where(verified)
    last_verified = verified_date.groupby(output["c_name"]).ffill()
    output["days_since_verified_trade"] = (output["date"] - last_verified).dt.days
    return output


def session_calendar(panel: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(pd.to_datetime(panel["date"].dropna().unique()))


def session_offset(
    dates: list[pd.Timestamp], date: pd.Timestamp, offset: int
) -> pd.Timestamp | pd.NaT:
    positions = {value: index for index, value in enumerate(dates)}
    index = positions.get(pd.Timestamp(date))
    if index is None or index + offset >= len(dates):
        return pd.NaT
    return pd.Timestamp(dates[index + offset])


def resolve_fill(
    evidence: pd.DataFrame,
    dates: list[pd.Timestamp],
    c_name: str,
    intended_date: pd.Timestamp,
    proxy: str,
    max_delay: int,
) -> dict:
    """Resolve a future fill; close proxy is explicit and never called verified."""
    by_date = evidence[evidence["c_name"].eq(c_name)].set_index("date")
    intended_index = {date: index for index, date in enumerate(dates)}.get(
        pd.Timestamp(intended_date)
    )
    if intended_index is None:
        return {"executed": False, "failure_reason": "intended_date_unavailable"}
    for delay in range(max_delay + 1):
        index = intended_index + delay
        if index >= len(dates):
            break
        date = pd.Timestamp(dates[index])
        if date not in by_date.index:
            continue
        row = by_date.loc[date]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        allowed = proxy == "NEXT_CANONICAL_CLOSE" or bool(row["verified_trade"])
        if allowed and pd.notna(row["pa"]) and row["pa"] > 0:
            return {
                "executed": True,
                "execution_date": date,
                "execution_price": float(row["pa"]),
                "execution_delay": delay,
                "trade_evidence_status": row["trade_evidence_status"],
                "fill_is_verified": bool(row["verified_trade"]),
                "failure_reason": "",
            }
    return {
        "executed": False,
        "execution_date": pd.NaT,
        "execution_price": np.nan,
        "execution_delay": np.nan,
        "trade_evidence_status": "NO_VERIFIED_FILL",
        "fill_is_verified": False,
        "failure_reason": f"no_{proxy.lower()}_within_{max_delay}_sessions",
    }


def execution_timing_rows(
    selections: pd.DataFrame,
    evidence: pd.DataFrame,
    proxy: str,
    max_delay: int,
    holding_sessions: int = 5,
) -> pd.DataFrame:
    dates = session_calendar(evidence)
    positions = {date: index for index, date in enumerate(dates)}
    lookup = {
        (pd.Timestamp(row.date), row.c_name): row
        for row in evidence.itertuples(index=False)
    }

    def fast_fill(c_name: str, intended_date: pd.Timestamp) -> dict:
        intended_index = positions.get(pd.Timestamp(intended_date))
        if intended_index is None:
            return {"executed": False, "failure_reason": "intended_date_unavailable"}
        for delay in range(max_delay + 1):
            index = intended_index + delay
            if index >= len(dates):
                break
            date = pd.Timestamp(dates[index])
            value = lookup.get((date, c_name))
            allowed = value is not None and (
                proxy == "NEXT_CANONICAL_CLOSE" or bool(value.verified_trade)
            )
            if allowed and pd.notna(value.pa) and value.pa > 0:
                return {
                    "executed": True, "execution_date": date,
                    "execution_price": float(value.pa), "execution_delay": delay,
                    "trade_evidence_status": value.trade_evidence_status,
                    "fill_is_verified": bool(value.verified_trade), "failure_reason": "",
                }
        return {
            "executed": False, "execution_date": pd.NaT,
            "execution_price": np.nan, "execution_delay": np.nan,
            "trade_evidence_status": "NO_VERIFIED_FILL", "fill_is_verified": False,
            "failure_reason": f"no_{proxy.lower()}_within_{max_delay}_sessions",
        }

    rows = []
    for record in selections.itertuples(index=False):
        signal_date = pd.Timestamp(record.date)
        intended_entry = session_offset(dates, signal_date, 1)
        theoretical_end = session_offset(dates, signal_date, 5)
        entry = fast_fill(record.c_name, intended_entry) if pd.notna(intended_entry) else {"executed": False, "failure_reason": "no_next_session"}
        row = {
            "fold": record.fold,
            "signal_date": signal_date,
            "c_name": record.c_name,
            "symbol": record.symbol,
            "signal_prediction": record.prediction,
            "theoretical_label_return": record.actual,
            "theoretical_label_end": theoretical_end,
            "execution_proxy": proxy,
            "max_delay": max_delay,
            "intended_entry_date": intended_entry,
            **entry,
        }
        if entry.get("executed"):
            intended_exit = session_offset(
                dates, pd.Timestamp(entry["execution_date"]), holding_sessions
            )
            exit_fill = fast_fill(record.c_name, intended_exit) if pd.notna(intended_exit) else {"executed": False, "failure_reason": "no_exit_session"}
            row.update(
                {
                    "intended_exit_date": intended_exit,
                    "exit_executed": exit_fill.get("executed", False),
                    "exit_date": exit_fill.get("execution_date", pd.NaT),
                    "exit_price": exit_fill.get("execution_price", np.nan),
                    "exit_delay": exit_fill.get("execution_delay", np.nan),
                    "actual_holding_sessions": (
                        positions[pd.Timestamp(exit_fill["execution_date"])]
                        - positions[pd.Timestamp(entry["execution_date"])]
                        if exit_fill.get("executed") else np.nan
                    ),
                    "execution_aware_return": (
                        exit_fill["execution_price"] / entry["execution_price"] - 1
                        if exit_fill.get("executed") else np.nan
                    ),
                    "exit_failure_reason": exit_fill.get("failure_reason", ""),
                }
            )
        else:
            row.update(
                {
                    "intended_exit_date": pd.NaT, "exit_executed": False,
                    "exit_date": pd.NaT, "exit_price": np.nan,
                    "exit_delay": np.nan, "actual_holding_sessions": np.nan,
                    "execution_aware_return": np.nan, "exit_failure_reason": "entry_failed",
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)
