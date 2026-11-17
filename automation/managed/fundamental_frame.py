"""Fundamental derivation from already-fetched source payloads.

Managed-collection copy of the archival enrichment's pure calculations. No
network, no storage. The rules are compared with the archival module in the tests:
one fiscal year is chosen for the reported figures, projections stay separate,
share count is current, and nothing is invented when a table is absent.
"""

import json
import math
import re
from datetime import datetime

YEAR_FLOOR = 2000
MAX_LOOKBACK = 6


def price_ratios(price, company, market_cap=None):
    """Pure port of the existing price job's calculations, in its original units.

    Inputs are already normalized numbers. Net profit is in millions; prefer
    reported market cap to stale per-share figures. Source/time eligibility is
    decided by the caller, never by the presence of a computed ratio.
    """
    bpa, tc5, roe = (company.get(key) or 0 for key in ('bpa', 'tc5', 'roe'))
    shares, equity = (company.get(key) or 0 for key in ('na', 'cp'))
    capital = market_cap or (price * shares if shares else None)
    pb = capital / equity if capital is not None and equity else None
    profit = company.get('net_profit')
    per = market_cap / (profit * 1000000) if market_cap and profit else price / bpa if bpa else None
    if per is not None and abs(per) > 500:
        per = None
    peg = per / tc5 if per is not None and per > 0 and 1 <= tc5 <= 100 else None
    pr = per / roe if per is not None and per > 0 and roe >= 1 else None

    def rating(value, green, orange):
        if value is None or value <= 0:
            return None
        return 'green' if value <= green else 'orange' if value <= orange else 'red'

    return {'cb': capital, 'pb': pb, 'per': per, 'peg': peg, 'pr': pr,
        'per_rating': rating(per, 20, 25), 'peg_rating': rating(peg, 1, 2),
        'pr_rating': rating(pr, 1.5, 2), 'pb_rating': rating(pb, 2, 3)}


def _price_observation(price, observed_at):
    """Validate explicit inputs without consulting the wall clock."""
    try:
        moment = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            raise ValueError()
    except (AttributeError, ValueError):
        raise ValueError('Aware original observation time required') from None
    if (isinstance(price, bool) or not isinstance(price, (int, float))
            or not math.isfinite(price) or price <= 0):
        raise ValueError('Positive normalized price required')


def price_document(name, price, company, market, observed_at):
    """Original getprice application-row shape, with capture time supplied by caller.

    Market fields have already been normalized. Unknown OHLC/volume remain absent;
    genuine published zeros remain zero. This function performs no persistence.
    """
    _price_observation(price, observed_at)
    chart = fit_price_chart(market.get('data_chart'))
    values = {
        'date': observed_at, 'c_name': name, 'symbol': market['symbol'], 'pa': price,
        **price_ratios(price, company, market.get('market_cap')),
        **{key: market.get(key) for key in (
            'variation', 'variation_v', 'cours_ref', 'open_price', 'high', 'low',
            'volume', 'qty_traded', 'market_cap')},
        'data_chart': chart or None,
    }
    return {key: value for key, value in values.items() if value is not None}


def fit_price_chart(chart, max_len=195):
    """Legacy chart suffix in linear time, including charts longer than 500 chars."""
    if not chart or len(chart) <= max_len:
        return chart
    parts = chart.split('|')
    flag = parts[-1] if len(parts) > 1 else ''
    points = parts[0].split(';')
    remaining = len(parts[0]) + 1 + len(flag)
    first = 0
    while first < len(points) and remaining > max_len:
        remaining -= len(points[first]) + (1 if first < len(points) - 1 else 0)
        first += 1
    return ';'.join(points[first:]) + '|' + flag


def index_document(name, price, market, observed_at):
    """Original index row; never manufacture company ratios or a stock symbol."""
    _price_observation(price, observed_at)
    values = {
        'date': observed_at, 'c_name': name, 'pa': price,
        **{key: market.get(key) for key in (
            'cours_ref', 'variation', 'variation_v', 'high', 'low', 'volume',
            'qty_traded', 'market_cap')},
    }
    return {key: value for key, value in values.items() if value is not None}


def legacy_price_fields(price, market, view):
    """Original price job's two derived fields; explicit legacy-profile use only.

    Quotes supplied a reference close; instrument references supplied an absolute
    change instead. These calculations are not assumptions about other providers.
    """
    result = dict(market)
    if view == 'quotes':
        reference = result.get('cours_ref')
        result['variation_v'] = round(price - reference, 4) if price and reference else None
    elif view == 'instruments':
        change = result.get('variation_v')
        result['cours_ref'] = round(price - change, 4) if change is not None else None
    return result


def data(payload):
    return payload.get("data") if isinstance(payload, dict) else None


def to_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def reported_years(*tables):
    """Four-digit reported year columns present in these tables, newest first."""
    years = set()
    for table in tables:
        value = data(table)
        if isinstance(value, dict):
            for key in value:
                if (
                    isinstance(key, str)
                    and len(key) == 4
                    and key.isdigit()
                    and int(key) >= YEAR_FLOOR
                ):
                    years.add(key)
    return sorted(years, reverse=True)


def latest(table, allow_projected=False):
    value = data(table)
    if not isinstance(value, dict):
        return None
    for year in reported_years(table)[:MAX_LOOKBACK]:
        number = to_float(value.get(year))
        if number is not None:
            return number
    if allow_projected:
        for key in sorted(
            key for key in value if isinstance(key, str) and re.match(r"^\d{4}p$", key)
        ):
            number = to_float(value[key])
            if number is not None:
                return number
    return None


def series(table):
    value = data(table)
    output = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and re.match(r"^\d{4}p?$", key):
                number = to_float(item)
                if number is not None:
                    output[key] = number
    return dict(sorted(output.items()))


def projected_profit(profit):
    """Newest projected net profit and year, strictly separate from reported."""
    value = data(profit)
    if not isinstance(value, dict):
        return None, None
    years = sorted(
        key
        for key in value
        if isinstance(key, str)
        and len(key) == 5
        and key.endswith("p")
        and key[:4].isdigit()
        and int(key[:4]) >= YEAR_FLOOR
    )
    for key in years[:MAX_LOOKBACK]:
        number = to_float(value.get(key))
        if number is not None and number != 0:
            return int(key[:4]), number
    return None, None


def year_value(table, year):
    value = data(table)
    if not isinstance(value, dict) or year is None:
        return None
    return to_float(value.get(str(year)))


def consistent_year(profit, *tables):
    """Newest reported year where every table has a usable value."""
    for year in reported_years(profit, *tables)[:MAX_LOOKBACK]:
        amount = year_value(profit, year)
        if amount is None or amount == 0:
            continue
        if all(year_value(table, year) is not None for table in tables):
            return int(year)
    return None


def shares_now(table):
    """Current share count: the highest year present, forecasts included."""
    value = data(table)
    if not isinstance(value, dict):
        return None
    best = None
    for key, item in value.items():
        if not (isinstance(key, str) and re.match(r"^\d{4}p?$", key)):
            continue
        number = to_float(item)
        if number is None or number <= 0:
            continue
        year = int(key[:4])
        if best is None or year > best[0]:
            best = (year, number)
    return best[1] if best else None


def cagr(table, years=5):
    value = data(table)
    if not isinstance(value, dict):
        return None
    last_year = last_value = None
    for key in reported_years(table)[:MAX_LOOKBACK]:
        number = to_float(value.get(key))
        if number is not None and number > 0:
            last_year, last_value = int(key), number
            break
    if not last_year:
        return None
    first = to_float(value.get(str(last_year - years)))
    if first is None or first <= 0:
        return None
    return round((pow(last_value / first, 1 / years) - 1) * 100, 2)


def identity(symbol, stock, symlinks):
    """Registered external name and sector for a symbol, or (None, None)."""
    ext_name = sector = None
    if isinstance(symlinks, list):
        for item in symlinks:
            if isinstance(item, dict) and item.get("symbol") == symbol:
                ext_name = item.get("name")
                sector = item.get("type")
                break
    if not ext_name and isinstance(stock, dict):
        ext_name = stock.get("name")
    return ext_name, sector


def derive(symbol, stock, symlinks, financial, tables):
    financial_data = (
        financial.get("financialData") if isinstance(financial, dict) else None
    )
    if not isinstance(financial_data, dict):
        financial_data = {}

    ext_name, sector = identity(symbol, stock, symlinks)
    if not ext_name:
        raise ValueError("SYMBOL_NOT_IN_SOURCE_REGISTRY")

    table = lambda kind: tables.get(kind)  # noqa: E731
    fiscal_year = consistent_year(table("rnpg"), table("fp"), table("ca"))
    fy_est, rnpg_est = projected_profit(table("rnpg"))
    if fy_est is not None and fiscal_year is not None and fy_est <= fiscal_year:
        fy_est, rnpg_est = None, None

    rnpg = year_value(table("rnpg"), fiscal_year)
    fp = year_value(table("fp"), fiscal_year)
    ca = year_value(table("ca"), fiscal_year)
    ebe = year_value(table("ebe"), fiscal_year)
    ebit = year_value(table("ebit"), fiscal_year)
    dn = year_value(table("dn"), fiscal_year)
    tn = year_value(table("tn"), fiscal_year)
    fcf = year_value(table("fcf"), fiscal_year)
    actif = year_value(table("actif"), fiscal_year)
    dpa = year_value(table("dpa"), fiscal_year)
    nmt = shares_now(table("nmt"))

    bpa = None
    if rnpg is not None and nmt:
        bpa = round(rnpg * 1_000_000 / nmt, 2)
    if bpa is None and fiscal_year:
        per_share = (
            financial_data.get("beneficeParAction")
            if isinstance(financial_data.get("beneficeParAction"), dict)
            else {}
        )
        number = to_float(per_share.get(str(fiscal_year)))
        if number is not None:
            bpa = number
    if dpa is None and fiscal_year:
        per_share = (
            financial_data.get("dividendeParAction")
            if isinstance(financial_data.get("dividendeParAction"), dict)
            else {}
        )
        number = to_float(per_share.get(str(fiscal_year)))
        if number is not None:
            dpa = number

    roe = round(rnpg / fp * 100, 2) if (rnpg is not None and fp) else None
    cp = fp * 1_000_000 if fp is not None else None
    margin = round(rnpg / ca * 100, 2) if (rnpg is not None and ca) else None

    beta_data = data(table("beta"))
    beta_3y = to_float(beta_data.get("Béta 3 ans")) if isinstance(beta_data, dict) else None
    beta_5y = to_float(beta_data.get("Béta 5 ans")) if isinstance(beta_data, dict) else None

    description_data = data(table("desc"))
    description = None
    if isinstance(description_data, dict):
        description = (description_data.get("description") or "").strip()[:3800] or None

    holders_data = data(table("holders"))
    shareholders = None
    if isinstance(holders_data, list):
        holders = [
            {
                "name": holder.get("Shareholder", ""),
                "pct": round(to_float(holder.get("Percentage")) * 100, 2),
            }
            for holder in holders_data
            if isinstance(holder, dict) and to_float(holder.get("Percentage"))
        ]
        holders = [holder for holder in holders if holder["pct"] > 0]
        if holders:
            shareholders = json.dumps(holders, ensure_ascii=False)

    return {
        "symbol": symbol,
        "ext_name": ext_name,
        "sector": sector,
        "description": description,
        "computed": {
            "bpa": bpa,
            "dpa": dpa,
            "tc5": cagr(table("ca"), 5),
            "roe": roe,
            "na": nmt,
            "cp": cp,
            "beta_3y": beta_3y,
            "beta_5y": beta_5y,
            "revenue": ca,
            "ebitda": ebe,
            "ebit": ebit,
            "net_profit": rnpg,
            "fcf": fcf,
            "net_debt": dn,
            "net_cash": tn,
            "total_assets": actif,
            "profit_margin": margin,
            "rev_growth_5y": cagr(table("ca"), 5),
            "rnpg_growth_5y": cagr(table("rnpg"), 5),
            "shareholders": shareholders,
            "fiscal_year": fiscal_year,
            "fy_est": fy_est,
            "rnpg_est": rnpg_est,
        },
    }
