"""Point-in-time Casablanca tradability classes and actionable ranks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features_market import BASE_FEATURES


ORDER = {
    "GOOD": 0,
    "CAUTION": 1,
    "AVOID": 2,
    "INSUFFICIENT_DATA": 3,
}


def attach_tradability(frame: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """Classify each row using fields available no later than its decision date."""
    output = frame.sort_values(["c_name", "date"]).copy()
    output["feature_missing_fraction"] = output[BASE_FEATURES].isna().mean(axis=1)
    output["corporate_action_recent"] = (
        output["suspected_corporate_action"]
        .astype(int)
        .groupby(output["c_name"])
        .transform(
            lambda series: series.rolling(
                settings["corporate_action_lookback_dates"], min_periods=1
            ).max()
        )
        .gt(0)
    )

    insufficient = (
        output["history_days"].lt(settings["minimum_history"])
        | output["feature_missing_fraction"].gt(
            settings["maximum_feature_missing_fraction"]
        )
    )
    avoid = (
        output["stale_run"].ge(settings["avoid_stale_run"])
        | (
            ~output["volume_known"]
            & output["stale_fraction_20d"].gt(
                settings["avoid_unknown_volume_stale_fraction_20d"]
            )
        )
        | (
            output["volume_known"]
            & output["trading_frequency_20d"].lt(
                settings["minimum_known_trading_frequency"]
            )
        )
        | output["corporate_action_recent"]
        | ~output["eligible"]
    )
    caution = (
        ~output["volume_known"]
        | output["stale_run"].ge(settings["caution_stale_run"])
        | output["stale_fraction_20d"].gt(
            settings["caution_stale_fraction_20d"]
        )
        | output["days_since_genuine_trade"].gt(
            settings["caution_days_since_trade"]
        )
        | output["feature_missing_fraction"].gt(0.10)
    )
    output["tradability_class"] = np.select(
        [insufficient, avoid, caution],
        ["INSUFFICIENT_DATA", "AVOID", "CAUTION"],
        default="GOOD",
    )

    def reasons(row: pd.Series) -> str:
        values = []
        if row["history_days"] < settings["minimum_history"]:
            values.append("short_history")
        if row["feature_missing_fraction"] > settings["maximum_feature_missing_fraction"]:
            values.append("feature_missingness")
        if not row["volume_known"]:
            values.append("volume_unknown")
        if row["stale_run"] >= settings["caution_stale_run"]:
            values.append("stale_run")
        if row["stale_fraction_20d"] > settings["caution_stale_fraction_20d"]:
            values.append("frequent_unchanged_prices")
        if pd.notna(row["days_since_genuine_trade"]) and row["days_since_genuine_trade"] > settings["caution_days_since_trade"]:
            values.append("days_since_observed_trade")
        if row["corporate_action_recent"]:
            values.append("recent_suspected_corporate_action")
        if (
            not row["eligible"]
            and pd.notna(row["eligibility_reason"])
            and str(row["eligibility_reason"])
        ):
            values.append(str(row["eligibility_reason"]))
        return ";".join(dict.fromkeys(values)) or "clean_observed_history"

    output["tradability_reason"] = output.apply(reasons, axis=1)
    output["actionable"] = output["tradability_class"].isin(["GOOD", "CAUTION"])
    output["strictly_tradable"] = output["tradability_class"].eq("GOOD")
    # This intermediate research screen does not claim that an unknown-volume
    # price update was executable. It only removes the clearest stale/data-risk
    # cases so V3 can test whether they drive the ranking result.
    output["quality_screen_pass"] = (
        output["actionable"]
        & output["stale_run"].lt(settings["caution_stale_run"])
        & output["stale_fraction_20d"].le(
            settings["caution_stale_fraction_20d"]
        )
        & output["feature_missing_fraction"].le(0.10)
        & ~output["corporate_action_recent"]
    )
    return output


def add_signal_and_actionable_ranks(
    frame: pd.DataFrame,
    score_column: str = "prediction",
) -> pd.DataFrame:
    output = frame.copy()
    output["signal_rank"] = output.groupby("date")[score_column].rank(
        ascending=False, method="first"
    )
    output["actionable_rank"] = np.nan
    actionable = output["actionable"].fillna(False)
    class_order = output["tradability_class"].map(ORDER)
    ranked = output.loc[actionable].assign(_class_order=class_order.loc[actionable])
    ranked = ranked.sort_values(
        ["date", "_class_order", score_column], ascending=[True, True, False]
    )
    ranked["actionable_rank"] = ranked.groupby("date").cumcount() + 1
    output.loc[ranked.index, "actionable_rank"] = ranked["actionable_rank"]
    return output
