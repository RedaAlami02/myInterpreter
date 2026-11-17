"""Derive one daily `data` row per company from an exchange capture.

Mirrors the retired Appwrite getprice function: market capitalisation comes from
the exchange, and PER/P-B are computed from totals so they cannot be poisoned by
a stale per-share figure. Values without a trustworthy input stay null; nothing
is defaulted to zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PER_GREEN, PER_ORANGE = 20.0, 25.0
PEG_GREEN, PEG_ORANGE = 1.0, 2.0
PR_GREEN, PR_ORANGE = 1.5, 2.0
PB_GREEN, PB_ORANGE = 2.0, 3.0
MAX_PER = 500.0
MIN_TC5, MAX_TC5 = 1.0, 100.0
MIN_ROE = 1.0

CASABLANCA = ZoneInfo("Africa/Casablanca")


def number(value):
    if value in (None, "", "-", "--"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def rate(value, green, orange):
    if value is None or value <= 0:
        return None
    if value <= green:
        return "green"
    if value <= orange:
        return "orange"
    return "red"


def trade_day(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(CASABLANCA).date().isoformat()


def utc_stamp(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ratios(price, cap, company):
    """Return (per, peg, pr, pb, ratings) using the legacy guards."""
    cp = number(company.get("cp"))
    net_profit = number(company.get("net_profit"))
    bpa = number(company.get("bpa"))
    tc5 = number(company.get("tc5"))
    roe = number(company.get("roe"))

    # Market cap over net income, not price over EPS: no share count involved.
    if cap and net_profit:
        per = cap / (net_profit * 1_000_000)
    elif price and bpa:
        per = price / bpa
    else:
        per = None
    if per is not None and abs(per) > MAX_PER:
        per = None
    pb = cap / cp if cap and cp else None
    peg = per / tc5 if per is not None and per > 0 and tc5 is not None and MIN_TC5 <= tc5 <= MAX_TC5 else None
    pr = per / roe if per is not None and per > 0 and roe is not None and roe >= MIN_ROE else None
    ratings = {
        "per_rating": rate(per, PER_GREEN, PER_ORANGE),
        "peg_rating": rate(peg, PEG_GREEN, PEG_ORANGE),
        "pr_rating": rate(pr, PR_GREEN, PR_ORANGE),
        "pb_rating": rate(pb, PB_GREEN, PB_ORANGE),
    }
    return per, peg, pr, pb, ratings


def daily_row(symbol, name, action, record, company, moment):
    """One row for public.data, or None when the session produced no price."""
    price = number((action or {}).get("dernierCours"))
    if price is None or price <= 0:
        price = number((record or {}).get("price"))
    if price is None or price <= 0:
        return None
    shares = number((record or {}).get("shares")) or number(company.get("na"))
    cap = number((action or {}).get("capitalisation")) or number((record or {}).get("cap"))
    if cap is None and shares:
        cap = price * shares
    reference = number((action or {}).get("reference"))
    per, peg, pr, pb, ratings = ratios(price, cap, company or {})
    variation = number((action or {}).get("variation"))
    row = {
        "symbol": symbol.upper(),
        "c_name": name,
        "trade_day": trade_day(moment),
        "date": utc_stamp(moment),
        "pa": price,
        "cb": cap,
        "market_cap": cap,
        "per": per,
        "peg": peg,
        "pr": pr,
        "pb": pb,
        **ratings,
        "variation": variation,
        "variation_v": round(price - reference, 4) if reference else None,
        "cours_ref": reference,
        "open_price": number((action or {}).get("ouverture")),
        "high": number((action or {}).get("plusHaut")),
        "low": number((action or {}).get("plusBas")),
        "volume": number((action or {}).get("volume")),
        "qty_traded": number((action or {}).get("quantite")),
    }
    return {key: value for key, value in row.items() if value is not None}


def build_rows(snapshot, actions, formats, companies, moment):
    """Map capture artefacts onto one row per company; skip unpriced ones."""
    by_symbol = {}
    for row in actions or []:
        symbol = str((row or {}).get("symbol") or "").upper()
        if symbol:
            by_symbol.setdefault(symbol, row)
    records = {}
    for row in snapshot or []:
        symbol = str((row or {}).get("symbol") or "").upper()
        if symbol:
            records.setdefault(symbol, row)
    rows, skipped = [], []
    for fmt in formats or []:
        symbol = str((fmt or {}).get("symbol") or "").upper()
        name = (fmt or {}).get("name")
        if not symbol or not isinstance(name, str) or not name:
            continue
        company = (companies or {}).get(name)
        row = daily_row(symbol, name, by_symbol.get(symbol), records.get(symbol),
                        company or {}, moment)
        if row is None:
            skipped.append(symbol)
            continue
        rows.append(row)
    return rows, skipped
