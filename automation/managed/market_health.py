"""Pure market-data freshness audit.

Inputs are already-fetched rows from the public Supabase tables. No network, no
writes. The caller supplies the as-of moment so tests and cloud runs are
reproducible.
"""

import json
from datetime import datetime, timezone

CONTRACT = "market-health/v1"


def _moment(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _shareholders(value):
    if value in (None, "", "[]"):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def audit(latest_prices, companies, dividends, formats, as_of=None, max_age_days=7):
    moment = as_of or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    symbols = {row.get("name"): row.get("symbol") for row in formats or []}
    prices = {row.get("c_name"): row for row in latest_prices or []}
    dividend_years = {}
    for row in dividends or []:
        name = row.get("c_name")
        year = row.get("year")
        if not isinstance(year, int):
            continue
        current = dividend_years.get(name)
        if current is None or year > current[0]:
            dividend_years[name] = (year, bool(row.get("confirmed")))
    rows = []
    summary = {
        "companies": 0, "price_ok": 0, "price_stale": 0, "price_missing": 0,
        "price_zero": 0, "fiscal_ok": 0, "fiscal_stale": 0, "fiscal_missing": 0,
        "shares_missing": 0, "dividend_recent": 0, "dividend_stale": 0,
        "dividend_missing": 0, "shareholders_missing": 0, "needs_attention": 0,
        "fiscal_current": 0,
    }
    for company in companies or []:
        name = company.get("name")
        if not isinstance(name, str) or not name:
            continue
        summary["companies"] += 1
        price = prices.get(name) or {}
        price_value = _number(price.get("pa"))
        price_date = _moment(price.get("date"))
        age = (moment - price_date).days if price_date else None
        flags = []
        if price_value is None:
            price_status = "MISSING"
            summary["price_missing"] += 1
            flags.append("PRICE_MISSING")
        elif price_value <= 0:
            price_status = "ZERO"
            summary["price_zero"] += 1
            flags.append("PRICE_ZERO")
        elif age is not None and age > max_age_days:
            price_status = "STALE"
            summary["price_stale"] += 1
            flags.append("PRICE_STALE_%dD" % age)
        else:
            price_status = "OK"
            summary["price_ok"] += 1
        fiscal = company.get("fiscal_year")
        if not isinstance(fiscal, int):
            fiscal_status = "MISSING"
            summary["fiscal_missing"] += 1
            flags.append("FISCAL_YEAR_MISSING")
        elif fiscal < moment.year - 1:
            fiscal_status = "STALE"
            summary["fiscal_stale"] += 1
            flags.append("FISCAL_YEAR_STALE_%d" % fiscal)
        elif fiscal >= moment.year:
            fiscal_status = "CURRENT"
            summary["fiscal_current"] += 1
            flags.append("FISCAL_YEAR_NOT_COMPLETED_%d" % fiscal)
        else:
            fiscal_status = "OK"
            summary["fiscal_ok"] += 1
        shares = _number(company.get("na"))
        if shares is None or shares <= 0:
            summary["shares_missing"] += 1
            flags.append("SHARES_MISSING")
        dividend = dividend_years.get(name)
        if dividend is None:
            dividend_status = "MISSING"
            summary["dividend_missing"] += 1
        elif dividend[0] >= moment.year - 1:
            dividend_status = "CONFIRMED" if dividend[1] else "UNCONFIRMED"
            summary["dividend_recent"] += 1
            if not dividend[1]:
                flags.append("DIVIDEND_UNCONFIRMED")
        else:
            dividend_status = "STALE"
            summary["dividend_stale"] += 1
            flags.append("DIVIDEND_STALE_%d" % dividend[0])
        holders = _shareholders(company.get("shareholders"))
        if not holders:
            summary["shareholders_missing"] += 1
            flags.append("SHAREHOLDERS_MISSING")
        if any(flag.startswith(("PRICE_MISSING", "PRICE_ZERO", "PRICE_STALE",
                                "FISCAL_YEAR_MISSING", "FISCAL_YEAR_STALE",
                                "FISCAL_YEAR_NOT_COMPLETED", "SHARES_MISSING")) for flag in flags):
            summary["needs_attention"] += 1
        rows.append({
            "symbol": symbols.get(name), "name": name,
            "price": price_value, "price_date": price.get("date"),
            "price_age_days": age, "price_status": price_status,
            "fiscal_year": fiscal, "fiscal_status": fiscal_status,
            "shares": shares, "dividend_year": dividend[0] if dividend else None,
            "dividend_confirmed": dividend[1] if dividend else None,
            "dividend_status": dividend_status,
            "shareholders": len(holders), "flags": flags,
        })
    rows.sort(key=lambda row: (-len(row["flags"]), row["name"] or ""))
    return {"contract": CONTRACT, "as_of": moment.isoformat(),
            "max_age_days": max_age_days, "summary": summary, "companies": rows}


def to_csv_rows(report):
    return [{key: row.get(key) for key in (
        "symbol", "name", "price", "price_date", "price_age_days", "price_status",
        "fiscal_year", "fiscal_status", "shares", "dividend_year",
        "dividend_confirmed", "dividend_status", "shareholders")}
        | {"flags": "; ".join(row.get("flags") or [])}
        for row in report.get("companies") or []]


def to_markdown(report):
    summary = report.get("summary") or {}
    lines = ["# Market data health", "", f"As of: {report.get('as_of')}", "",
             "| Metric | Count |", "|---|---:|"]
    for key in ("companies", "price_ok", "price_stale", "price_missing", "price_zero",
                "fiscal_ok", "fiscal_stale", "fiscal_missing", "fiscal_current",
                "shares_missing", "dividend_recent", "dividend_stale", "dividend_missing",
                "shareholders_missing", "needs_attention"):
        lines.append(f"| {key.replace('_', ' ')} | {summary.get(key, 0)} |")
    lines += ["", "## Needs attention", "",
              "| Symbol | Company | Price | Fiscal | Flags |", "|---|---|---|---|---|"]
    for row in report.get("companies") or []:
        if not row.get("flags"):
            continue
        lines.append(f"| {row.get('symbol') or ''} | {row.get('name')} | "
                     f"{row.get('price_status')} {row.get('price_age_days')}d | "
                     f"{row.get('fiscal_status')} {row.get('fiscal_year')} | "
                     f"{'; '.join(row.get('flags') or [])} |")
    return "\n".join(lines) + "\n"
