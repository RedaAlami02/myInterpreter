"""Canonical daily panel and conservative Casablanca tradability flags."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .common import clean_name, numeric, raw_frame


MARKET_NUMERIC = [
    "pa",
    "open_price",
    "high",
    "low",
    "volume",
    "qty_traded",
    "market_cap",
    "variation",
    "variation_v",
    "per",
    "pb",
    "pr",
    "peg",
    "cb",
]


def typed_source_tables() -> dict[str, pd.DataFrame]:
    market = raw_frame("data")
    market["c_name"] = clean_name(market["c_name"])
    market["observation_ts"] = pd.to_datetime(market["date"], utc=True, errors="coerce")
    market["captured_at"] = pd.to_datetime(market["$createdAt"], utc=True, errors="coerce")
    market["date"] = market["observation_ts"].dt.tz_localize(None).dt.normalize()
    numeric(market, MARKET_NUMERIC)

    dividends = raw_frame("dividends")
    dividends["c_name"] = clean_name(dividends["c_name"])
    dividends["ex_date"] = pd.to_datetime(dividends["ex_date"], errors="coerce")
    dividends["pay_date"] = pd.to_datetime(dividends["pay_date"], errors="coerce")
    dividends["pay_date_end"] = pd.to_datetime(dividends["pay_date_end"], errors="coerce")
    dividends["updated_at"] = pd.to_datetime(dividends["updated_at"], utc=True, errors="coerce")
    numeric(dividends, ["amount", "year"])

    companies = raw_frame("company")
    companies["name"] = clean_name(companies["name"])
    formats = raw_frame("format")
    formats["name"] = clean_name(formats["name"])
    latest = raw_frame("latest_prices")
    latest["c_name"] = clean_name(latest["c_name"])
    latest["date"] = pd.to_datetime(latest["date"], utc=True, errors="coerce")
    numeric(latest, ["pa"])
    errors = raw_frame("errors")
    errors["ts"] = pd.to_datetime(errors["ts"], utc=True, errors="coerce")
    return {
        "market_observations": market,
        "dividend_events": dividends,
        "company_snapshot": companies,
        "symbol_mapping": formats,
        "latest_prices": latest,
        "ingestion_errors": errors,
    }


def valid_dividend_events(dividends: pd.DataFrame, export_date: pd.Timestamp) -> pd.DataFrame:
    frame = dividends.copy()
    plausible_year = frame["year"].notna() & frame["ex_date"].notna()
    plausible_year &= (frame["year"] - frame["ex_date"].dt.year).between(0, 1)
    frame = frame[
        frame["confirmed"].fillna(False).astype(bool)
        & frame["amount"].gt(0)
        & frame["ex_date"].le(export_date)
        & plausible_year
    ].copy()
    # Some source updates store ordinary and ordinary+exceptional versions of the
    # same cash distribution. Do not double count an identical event.
    frame = frame.sort_values(["c_name", "ex_date", "type"]).drop_duplicates(
        ["c_name", "ex_date", "amount", "pay_date"], keep="last"
    )
    return frame


def _stale_run(prices: pd.Series) -> pd.Series:
    unchanged = prices.eq(prices.shift()) & prices.notna()
    groups = (~unchanged).cumsum()
    return unchanged.groupby(groups).cumsum().astype("int32")


def build_daily_panel(
    market: pd.DataFrame,
    mapping: pd.DataFrame,
    companies: pd.DataFrame,
    dividends: pd.DataFrame,
    export_date: pd.Timestamp,
    corporate_action_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = market.sort_values(["c_name", "date", "observation_ts", "captured_at"])
    daily = ordered.drop_duplicates(["c_name", "date"], keep="last").copy()
    daily = daily[daily["pa"].gt(0) & daily["date"].notna()].copy()

    masi = daily[daily["c_name"].eq("MASI")][["date", "pa"]].rename(
        columns={"pa": "masi_close"}
    )
    masi = masi.sort_values("date").drop_duplicates("date", keep="last")
    masi["masi_return_1d"] = masi["masi_close"].pct_change(fill_method=None)

    stocks = daily[~daily["c_name"].isin(["MASI", "TEST"])].copy()
    stock_dates = set(masi["date"])
    stocks = stocks[stocks["date"].isin(stock_dates)].copy()
    stocks = stocks.merge(masi, on="date", how="left", validate="many_to_one")

    symbol_map = mapping[["name", "symbol"]].drop_duplicates("name", keep="last").rename(
        columns={"symbol": "mapped_symbol"}
    )
    stocks = stocks.merge(symbol_map, left_on="c_name", right_on="name", how="left")
    stocks["symbol"] = stocks["mapped_symbol"].fillna(stocks["symbol"])
    sector_map = companies[["name", "sector"]].drop_duplicates("name", keep="last")
    stocks = stocks.merge(
        sector_map.rename(columns={"name": "company_name"}),
        left_on="c_name",
        right_on="company_name",
        how="left",
    )
    stocks = stocks.sort_values(["c_name", "date"]).reset_index(drop=True)
    grouped = stocks.groupby("c_name", group_keys=False)
    stocks["history_days"] = grouped.cumcount() + 1
    stocks["price_return_1d"] = grouped["pa"].pct_change(fill_method=None)
    stocks["stale_run"] = grouped["pa"].apply(_stale_run).reset_index(level=0, drop=True)
    stocks["stale_price_flag"] = stocks["stale_run"].gt(0)
    stocks["volume_known"] = stocks["volume"].notna() | stocks["qty_traded"].notna()
    stocks["genuine_trade"] = stocks["volume"].gt(0) | stocks["qty_traded"].gt(0)

    valid_dividends = valid_dividend_events(dividends, export_date)
    cash_by_day = (
        valid_dividends.groupby(["c_name", "ex_date"], as_index=False)["amount"]
        .sum()
        .rename(columns={"ex_date": "date", "amount": "dividend_cash"})
    )
    stocks = stocks.merge(cash_by_day, on=["c_name", "date"], how="left")
    stocks["dividend_cash"] = stocks["dividend_cash"].fillna(0.0)
    previous_price = grouped["pa"].shift(1)
    stocks["total_return_1d"] = (stocks["pa"] + stocks["dividend_cash"]) / previous_price - 1
    unexplained = stocks["total_return_1d"].abs().gt(corporate_action_threshold)
    stocks["suspected_corporate_action"] = unexplained.fillna(False)
    stocks["suspected_suspension"] = stocks["stale_run"].ge(10)

    trade_date = stocks["date"].where(stocks["genuine_trade"])
    last_trade = trade_date.groupby(stocks["c_name"]).ffill()
    stocks["days_since_genuine_trade"] = (stocks["date"] - last_trade).dt.days
    stocks.loc[~stocks["volume_known"], "days_since_genuine_trade"] = np.nan
    return stocks, masi, valid_dividends
