"""Genuine forward shadow inference against the live Supabase market tables.

Rebuilds the frozen V3 panel from the production tables, runs the four
hash-pinned V3 models on the newest closed session, and appends to an
era-specific ledger. It is shadow-only: nothing here reaches candidate
selection, execution, or any application surface.

The Appwrite-era ledger is left untouched. Its last three cohorts never
matured because the source changed, and mixing the two eras in one file would
make "genuine" ambiguous.

    python -m research.prediction_model.src.run_supabase_forward --check
    python -m research.prediction_model.src.run_supabase_forward --dry-run
    python -m research.prediction_model.src.run_supabase_forward
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .common import PROJECT_ROOT, load_json, sha256
from .daily_panel import build_daily_panel
from .features_market import BASE_FEATURES, build_features, mark_eligibility
from .labels import add_forward_labels
from .paper_trading import append_rows, initialize_ledger
from .supabase_source import SourceError, latest_date, snapshot, tables
from .tradability import attach_tradability
from .v2_models import predict_bundle
from .v3_5_execution import attach_trade_evidence

AUTOMATION = PROJECT_ROOT / "data" / "automation"
PREDICTIONS = AUTOMATION / "supabase_forward_predictions.csv"
OUTCOMES = AUTOMATION / "supabase_forward_outcomes.csv"
RUN_MODES = AUTOMATION / "supabase_forward_run_modes.csv"

MODEL_PATHS = {
    "whole_5d": PROJECT_ROOT / "models/v3/xgboost__percentile__rolling_252__5d.joblib",
    "topk_5d": PROJECT_ROOT / "models/v3/xgboost__dedicated_rank__expanding__5d.joblib",
    "secondary_5d": PROJECT_ROOT / "models/v3/catboost__raw__expanding__5d.joblib",
    "whole_20d": PROJECT_ROOT / "models/v3/xgboost__percentile__rolling_252__20d.joblib",
}
FROZEN = {
    "whole_5d": "a719c12fb018553070ede5641fd30b7829e38281e5c20ffbb12899039aa44fd1",
    "topk_5d": "9c84d8fe82348684a966eb5701b74a390988898e2b01faabeeb392a2d7b7b434",
    "secondary_5d": "2d654c907077afbc00d1018bf3719973f28399e1e897b7e23117b77c9bb37b1c",
    "whole_20d": "87be4cd6c61604f97dc23c09fb937a1781f9f8f9c31acd54550abff0d734b1c9",
}

PREDICTION_FIELDS = [
    "record_id", "prediction_market_date", "prediction_generated_at",
    "data_available_through", "model_hash", "model_hashes", "data_hash",
    "symbol", "company", "score_5d", "signal_rank_5d", "topk_rank_5d",
    "actionable_rank_5d", "score_20d", "signal_rank_20d",
    "model_agreement_5d", "tradability_class", "trade_evidence_status",
    "execution_policy", "intended_order", "confidence", "source",
]
OUTCOME_FIELDS = [
    "outcome_id", "prediction_record_id", "prediction_market_date", "symbol",
    "outcome_appended_at", "label_end_date", "realized_5d_excess",
    "realized_stock_total_return", "realized_masi_return", "status", "data_hash",
]
RUN_MODE_FIELDS = [
    "market_date", "rows", "run_mode", "source", "generation_time",
    "data_hash", "note",
]

MAX_LAG_DAYS = 4
# The daily publication can rewrite a session's close after the first post-close
# write. Scoring before it settles would make the "genuine" row depend on which
# minute the job happened to run.
MIN_SETTLE_MINUTES = 60


class ForwardError(RuntimeError):
    """The run would have produced a hindsight or otherwise invalid prediction."""


def _records(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    import csv

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _rank(values: pd.Series) -> pd.Series:
    return values.rank(method="first", ascending=False).astype(int)


def _record_id(market_date, symbol: str, model_hashes: str) -> str:
    value = f"supabase|{market_date}|{symbol}|{model_hashes}".encode()
    return hashlib.sha256(value).hexdigest()


def build_panel(tables_: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Mirror `daily_automation.build_forward_panel` without the CDG merge."""
    market = tables_["market"]
    export_date = market["date"].max()
    config = load_json(PROJECT_ROOT / "config.json")
    panel, _, _ = build_daily_panel(
        market,
        tables_["mapping"],
        tables_["companies"],
        tables_["dividends"],
        export_date,
        config["corporate_action_return_threshold"],
    )
    featured = build_features(panel)
    eligible = mark_eligibility(
        featured,
        config["minimum_history_days"],
        config["maximum_stale_run"],
        config["maximum_unknown_volume_stale_fraction_20d"],
        config["minimum_known_volume_trading_frequency_20d"],
    )
    v3 = load_json(PROJECT_ROOT / "config_v3.json")
    eligible = attach_tradability(eligible, v3["tradability"])
    eligible = attach_trade_evidence(eligible)
    return add_forward_labels(eligible, [5, 20])


def load_models() -> tuple[dict, str]:
    models = {}
    hashes = {}
    for name, path in MODEL_PATHS.items():
        raw = path.read_bytes()
        digest = sha256(path)
        if digest != FROZEN[name]:
            raise ForwardError(f"frozen model hash mismatch: {name}")
        models[name] = joblib.load(path)
        hashes[name] = digest
    return models, json.dumps(hashes, sort_keys=True)


def predict_latest(panel: pd.DataFrame, market_date: pd.Timestamp, models: dict,
                   model_hashes: str, data_hash: str, now: str) -> list[dict]:
    group = panel[panel["date"].eq(market_date) & panel["eligible"]].copy()
    if group.empty:
        raise ForwardError("no eligible securities for the target session")
    outputs = {}
    for name, bundle in models.items():
        missing = sorted(set(bundle.features) - set(group.columns))
        if missing:
            raise ForwardError(f"panel missing frozen features: {missing}")
        outputs[name] = predict_bundle(bundle, group)
    group["score_5d"] = outputs["whole_5d"]
    group["score_topk_5d"] = outputs["topk_5d"]
    group["score_secondary_5d"] = outputs["secondary_5d"]
    group["score_20d"] = outputs["whole_20d"]
    group["signal_rank_5d"] = _rank(group["score_5d"])
    group["signal_rank_20d"] = _rank(group["score_20d"])
    group["topk_rank_5d"] = _rank(group["score_topk_5d"])
    group["secondary_rank_5d"] = _rank(group["score_secondary_5d"])
    actionable = group["actionable"].fillna(False)
    group["actionable_rank_5d"] = np.nan
    group.loc[actionable, "actionable_rank_5d"] = _rank(
        group.loc[actionable, "score_topk_5d"]
    )
    group["model_agreement_5d"] = (
        group["signal_rank_5d"].le(5).astype(int)
        + group["topk_rank_5d"].le(5).astype(int)
        + group["secondary_rank_5d"].le(5).astype(int)
    )
    rows = []
    for value in group.itertuples(index=False):
        symbol = str(value.symbol)
        rows.append({
            "record_id": _record_id(market_date.date(), symbol, model_hashes),
            "prediction_market_date": str(market_date.date()),
            "prediction_generated_at": now,
            "data_available_through": str(market_date.date()),
            "model_hash": sha256(PROJECT_ROOT / "models/v3/xgboost__percentile__rolling_252__5d.joblib"),
            "model_hashes": model_hashes,
            "data_hash": data_hash,
            "symbol": symbol,
            "company": value.c_name,
            "score_5d": value.score_5d,
            "signal_rank_5d": value.signal_rank_5d,
            "topk_rank_5d": value.topk_rank_5d,
            "actionable_rank_5d": value.actionable_rank_5d,
            "score_20d": value.score_20d,
            "signal_rank_20d": value.signal_rank_20d,
            "model_agreement_5d": value.model_agreement_5d,
            "tradability_class": value.tradability_class,
            "trade_evidence_status": value.trade_evidence_status,
            "execution_policy": "STAGGERED_5_DAY_COHORTS",
            "intended_order": "BUY" if value.actionable_rank_5d <= 5 else "NONE",
            "confidence": "INSUFFICIENT_EVIDENCE",
            "source": "SUPABASE_LIVE",
        })
    return rows


def mature_outcomes(panel: pd.DataFrame, today: date) -> list[dict]:
    existing = {row["prediction_record_id"] for row in _records(OUTCOMES)}
    indexed = panel.set_index(
        [panel["date"].dt.strftime("%Y-%m-%d"), panel["symbol"].astype(str)]
    )
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for prediction in _records(PREDICTIONS):
        if prediction["record_id"] in existing:
            continue
        key = (prediction["prediction_market_date"], prediction["symbol"])
        if key not in indexed.index:
            continue
        value = indexed.loc[key]
        if isinstance(value, pd.DataFrame):
            value = value.iloc[-1]
        label_end = value.get("label_end_date_5d", pd.NaT)
        if pd.isna(label_end) or pd.Timestamp(label_end).date() > today:
            continue
        excess = value.get("excess_return_5d", np.nan)
        stock = value.get("stock_total_return_5d", np.nan)
        masi = value.get("masi_return_5d", np.nan)
        if pd.isna(excess) or pd.isna(stock):
            continue
        rows.append({
            "outcome_id": hashlib.sha256(
                f"{prediction['record_id']}|{pd.Timestamp(label_end).date()}".encode()
            ).hexdigest(),
            "prediction_record_id": prediction["record_id"],
            "prediction_market_date": prediction["prediction_market_date"],
            "symbol": prediction["symbol"],
            "outcome_appended_at": now,
            "label_end_date": str(pd.Timestamp(label_end).date()),
            "realized_5d_excess": excess,
            "realized_stock_total_return": stock,
            "realized_masi_return": masi,
            "status": "MATURED",
            "data_hash": prediction["data_hash"],
        })
    return rows


def run(apply: bool, snapshot_dir: Path | None, env_file: Path | None,
        settle_minutes: int = MIN_SETTLE_MINUTES) -> dict:
    temporary = None
    if snapshot_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="supabase-market-")
        snapshot_dir = Path(temporary.name)
    try:
        manifest = snapshot(snapshot_dir, env_file)
        tables_ = tables(snapshot_dir)
        panel = build_panel(tables_)
        latest = pd.Timestamp(panel["date"].max())
        today = datetime.now(timezone.utc).date()
        data_hash = manifest["tables"]["data"]["sha256"]

        existing_dates = {row["prediction_market_date"] for row in _records(PREDICTIONS)}
        pending = str(latest.date()) not in existing_dates
        if pending and (today - latest.date()).days > MAX_LAG_DAYS:
            raise ForwardError(
                f"source is { (today - latest.date()).days } days behind {latest.date()}; "
                "refusing to label a stale row as a genuinely new prediction"
            )
        observed = panel.loc[panel["date"].eq(latest), "observation_ts"].max()
        now = pd.Timestamp(datetime.now(timezone.utc))
        settled = pd.isna(observed) or (now - observed).total_seconds() >= settle_minutes * 60

        new_rows = []
        waiting = pending and not settled
        if pending and not waiting:
            models, model_hashes = load_models()
            new_rows = predict_latest(
                panel, latest, models, model_hashes, data_hash,
                datetime.now(timezone.utc).isoformat(),
            )
        matured = mature_outcomes(panel, today)

        result = {
            "status": "WAITING_FOR_SETTLED_CLOSE" if waiting else "OK",
            "source": "supabase",
            "data_latest": str(latest.date()),
            "observed_at": str(observed),
            "settle_minutes": settle_minutes,
            "eligible": int(panel[panel["date"].eq(latest)]["eligible"].sum()),
            "prediction_pending": pending and not waiting,
            "prediction_rows": len(new_rows),
            "matured_rows": len(matured),
            "applied": apply and bool(new_rows or matured),
        }
        if not apply:
            return result

        initialize_ledger(PREDICTIONS, PREDICTION_FIELDS)
        initialize_ledger(OUTCOMES, OUTCOME_FIELDS)
        initialize_ledger(RUN_MODES, RUN_MODE_FIELDS)
        if new_rows:
            append_rows(PREDICTIONS, new_rows, PREDICTION_FIELDS, "record_id")
            append_rows(RUN_MODES, [{
                "market_date": str(latest.date()),
                "rows": len(new_rows),
                "run_mode": "AUTOMATED_SUPABASE_FORWARD",
                "source": "SUPABASE_LIVE",
                "generation_time": datetime.now(timezone.utc).isoformat(),
                "data_hash": data_hash,
                "note": "scheduled shadow inference on the production market tables",
            }], RUN_MODE_FIELDS, "market_date")
        if matured:
            append_rows(OUTCOMES, matured, OUTCOME_FIELDS, "outcome_id")
        return result
    finally:
        if temporary is not None:
            temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="append to the ledgers")
    parser.add_argument("--dry-run", action="store_true", help="fetch and score, write nothing")
    parser.add_argument("--check", action="store_true", help="report the latest source date only")
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--settle-minutes", type=int, default=MIN_SETTLE_MINUTES)
    args = parser.parse_args()
    if args.check:
        try:
            print(latest_date(args.env_file) or "")
        except SourceError as error:
            print(json.dumps({"status": "FAILED", "error": str(error)}, sort_keys=True))
            return 1
        return 0
    try:
        result = run(apply=args.apply and not args.dry_run, snapshot_dir=args.snapshot_dir,
                     env_file=args.env_file, settle_minutes=args.settle_minutes)
    except (SourceError, ForwardError) as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
