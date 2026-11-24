"""Compact, leakage-safe market, MASI, liquidity, and trailing-dividend features."""

from __future__ import annotations

import numpy as np
import pandas as pd


BASE_FEATURES = [
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "relative_return_5d",
    "relative_return_20d",
    "relative_return_60d",
    "volatility_20d",
    "downside_volatility_20d",
    "drawdown_60d",
    "distance_high_60d",
    "ma_ratio_5_20",
    "price_acceleration",
    "beta_60d",
    "correlation_masi_60d",
    "relative_volatility_20d",
    "cross_sectional_momentum_rank",
]

LIQUIDITY_FEATURES = [
    "log_volume",
    "log_turnover",
    "trading_frequency_20d",
    "stale_fraction_20d",
    "stale_run",
    "days_since_genuine_trade",
    "volume_known",
    "history_days",
    "liquidity_missing",
]

DIVIDEND_FEATURES = [
    "trailing_dividend_252d",
    "trailing_dividend_yield",
    "days_since_dividend",
]


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.sort_values(["c_name", "date"]).copy()
    group = frame.groupby("c_name", group_keys=False)

    for window in [1, 5, 10, 20, 60]:
        frame[f"return_{window}d"] = group["pa"].pct_change(window, fill_method=None)
        frame[f"masi_return_lag_{window}d"] = group["masi_close"].pct_change(
            window, fill_method=None
        )
        if window in [5, 20, 60]:
            frame[f"relative_return_{window}d"] = (
                frame[f"return_{window}d"] - frame[f"masi_return_lag_{window}d"]
            )

    frame["volatility_20d"] = group["total_return_1d"].transform(
        lambda s: s.rolling(20, min_periods=15).std()
    )
    negative_return = frame["total_return_1d"].where(frame["total_return_1d"].lt(0), 0.0)
    frame["downside_volatility_20d"] = negative_return.groupby(frame["c_name"]).transform(
        lambda s: s.rolling(20, min_periods=15).std()
    )
    rolling_high = group["pa"].transform(lambda s: s.rolling(60, min_periods=30).max())
    rolling_low = group["pa"].transform(lambda s: s.rolling(60, min_periods=30).min())
    frame["drawdown_60d"] = frame["pa"] / rolling_high - 1
    frame["distance_high_60d"] = (frame["pa"] - rolling_low) / (rolling_high - rolling_low)
    ma5 = group["pa"].transform(lambda s: s.rolling(5, min_periods=5).mean())
    ma20 = group["pa"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    frame["ma_ratio_5_20"] = ma5 / ma20 - 1
    frame["price_acceleration"] = frame["return_5d"] - frame["return_20d"] / 4

    stock_ret = frame["total_return_1d"]
    masi_ret = frame["masi_return_1d"]
    rolling_cov = stock_ret.groupby(frame["c_name"]).transform(
        lambda s: s.rolling(60, min_periods=40).cov(masi_ret.loc[s.index])
    )
    rolling_market_var = masi_ret.groupby(frame["c_name"]).transform(
        lambda s: s.rolling(60, min_periods=40).var()
    )
    frame["beta_60d"] = rolling_cov / rolling_market_var
    frame["correlation_masi_60d"] = stock_ret.groupby(frame["c_name"]).transform(
        lambda s: s.rolling(60, min_periods=40).corr(masi_ret.loc[s.index])
    )
    masi_vol = masi_ret.groupby(frame["c_name"]).transform(
        lambda s: s.rolling(20, min_periods=15).std()
    )
    frame["relative_volatility_20d"] = frame["volatility_20d"] / masi_vol
    frame["cross_sectional_momentum_rank"] = frame.groupby("date")["relative_return_20d"].rank(
        pct=True
    )

    frame["log_volume"] = np.log1p(frame["volume"].where(frame["volume"].ge(0)))
    frame["log_turnover"] = np.log1p(
        (frame["volume"] * frame["pa"]).where(frame["volume"].ge(0))
    )
    frame["trading_frequency_20d"] = frame["genuine_trade"].astype(float).groupby(
        frame["c_name"]
    ).transform(lambda s: s.rolling(20, min_periods=10).mean())
    frame.loc[~frame["volume_known"], "trading_frequency_20d"] = np.nan
    frame["stale_fraction_20d"] = frame["stale_price_flag"].astype(float).groupby(
        frame["c_name"]
    ).transform(lambda s: s.rolling(20, min_periods=10).mean())
    frame["liquidity_missing"] = (~frame["volume_known"]).astype(int)

    trailing_cash = frame["dividend_cash"].groupby(frame["c_name"]).transform(
        lambda s: s.rolling(252, min_periods=1).sum()
    )
    frame["trailing_dividend_252d"] = trailing_cash
    frame["trailing_dividend_yield"] = trailing_cash / frame["pa"]
    last_dividend_date = frame["date"].where(frame["dividend_cash"].gt(0)).groupby(
        frame["c_name"]
    ).ffill()
    frame["days_since_dividend"] = (frame["date"] - last_dividend_date).dt.days
    return frame


def mark_eligibility(
    frame: pd.DataFrame,
    minimum_history: int,
    maximum_stale: int,
    maximum_unknown_volume_stale_fraction: float,
    minimum_known_volume_trading_frequency: float,
) -> pd.DataFrame:
    output = frame.copy()
    recent_action = output["suspected_corporate_action"].astype(int).groupby(
        output["c_name"]
    ).transform(lambda s: s.rolling(60, min_periods=1).max())
    reasons = pd.Series("", index=output.index, dtype="string")
    reasons = reasons.mask(output["history_days"].lt(minimum_history), "insufficient_history")
    reasons = reasons.mask(output["stale_run"].gt(maximum_stale), "stale_price_run")
    reasons = reasons.mask(
        ~output["volume_known"]
        & output["stale_fraction_20d"].gt(maximum_unknown_volume_stale_fraction),
        "mostly_stale_with_unknown_volume",
    )
    reasons = reasons.mask(
        output["volume_known"]
        & output["trading_frequency_20d"].lt(minimum_known_volume_trading_frequency),
        "low_observed_trading_frequency",
    )
    reasons = reasons.mask(recent_action.gt(0), "recent_suspected_corporate_action")
    reasons = reasons.mask(output["pa"].le(0) | output["pa"].isna(), "invalid_price")
    output["eligibility_reason"] = reasons
    output["eligible"] = reasons.eq("")
    return output
