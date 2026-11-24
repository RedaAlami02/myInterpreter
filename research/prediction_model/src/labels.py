"""Dividend-aware forward total-return and MASI-excess labels."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_forward_labels(panel: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    frame = panel.sort_values(["c_name", "date"]).copy()
    grouped = frame.groupby("c_name", group_keys=False)
    for horizon in horizons:
        future_price = grouped["pa"].shift(-horizon)
        future_date = grouped["date"].shift(-horizon)
        future_masi = grouped["masi_close"].shift(-horizon)
        # Sum cash with ex-date after the decision close and through the future close.
        future_cash = grouped["dividend_cash"].transform(
            lambda values: values.shift(-1).rolling(horizon, min_periods=horizon).sum().shift(-(horizon - 1))
        )
        future_action = grouped["suspected_corporate_action"].transform(
            lambda values: values.shift(-1)
            .rolling(horizon, min_periods=horizon)
            .max()
            .shift(-(horizon - 1))
        )
        frame[f"label_end_date_{horizon}d"] = future_date
        frame[f"stock_total_return_{horizon}d"] = (future_price + future_cash) / frame["pa"] - 1
        frame[f"masi_return_{horizon}d"] = future_masi / frame["masi_close"] - 1
        frame[f"excess_return_{horizon}d"] = (
            frame[f"stock_total_return_{horizon}d"] - frame[f"masi_return_{horizon}d"]
        )
        frame[f"label_crosses_corporate_action_{horizon}d"] = future_action.fillna(1).astype(bool)
        invalid = frame[f"label_crosses_corporate_action_{horizon}d"]
        frame.loc[invalid, f"stock_total_return_{horizon}d"] = np.nan
        frame.loc[invalid, f"excess_return_{horizon}d"] = np.nan
    return frame

