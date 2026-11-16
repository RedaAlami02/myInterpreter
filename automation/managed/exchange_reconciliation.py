"""Strict reconciliation of exchange instrument data against application fields.

Pure functions only: no network, no database, no writes. The caller supplies a
snapshot of exchange instrument records (see tools/reconcile_exchange.py) and,
optionally, the application's saved company rows.

The exchange is authoritative for identity, current shares, price and corporate
actions. Its annual-row ``nombreTitres`` is *not* trusted: several issuers store a
10x, 5x or 2x wrong count there. Current shares are accepted only when at least
two independent checks agree. Annual figures are proposed for review; the tool
never publishes them.
"""

from datetime import datetime, timezone
import hashlib
import json
import math

CONTRACT = "exchange-reconciliation/v1"
TOLERANCE = 0.01
ANOMALY_RATIOS = (10.0, 5.0, 2.0, 0.5, 0.2, 0.1)
ANOMALY_TOLERANCE = 0.02
BANK_WORDS = ("banque", "bank")
INSURER_WORDS = ("assurance", "assurances", "insurance")


def number(value):
    """Finite float or None; booleans and strings are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _latest(rows, key="exercice"):
    usable = [row for row in rows or [] if isinstance(row, dict) and number(row.get(key)) is not None]
    return max(usable, key=lambda row: number(row[key])) if usable else None


def _latest_capital_action(record):
    actions = [a for a in record.get("capital_actions") or [] if isinstance(a, dict)]
    dated = [a for a in actions if text(a.get("date")) and number(a.get("capital")) is not None]
    if not dated:
        return None
    # Several operations can share a date. The last total is the largest capital,
    # not the first row. Nominal-changing operations carry their own nominal.
    return max(dated, key=lambda a: (text(a["date"]), number(a.get("capital")) or 0))


def _ratio(value, reference):
    if value is None or reference is None or reference <= 0:
        return None
    return value / reference


def _anomaly(ratio):
    if ratio is None:
        return None
    for candidate in ANOMALY_RATIOS:
        if abs(ratio / candidate - 1) <= ANOMALY_TOLERANCE:
            return candidate
    return None


def validate_current_shares(record):
    """Triangulate the current share count.

    Checks: the exchange ``shares_count`` against capitalization/price and
    against the latest post-action capital divided by the instrument nominal.
    """
    shares = number(record.get("shares"))
    nominal = number(record.get("nominal"))
    price = number(record.get("price"))
    cap = number(record.get("cap"))
    action = _latest_capital_action(record)
    capital = number(action.get("capital")) if action else None
    annual = _latest(record.get("annual_rows"))
    if capital is None and annual:
        capital = number(annual.get("capitalSocial"))
    checks = []
    if shares and price and cap:
        implied = cap / price
        checks.append({"name": "capitalization_price", "implied": implied,
                       "deviation": abs(implied / shares - 1)})
    if shares and nominal and capital:
        # Capital is a current total; nominal is the current instrument nominal.
        # A split is already reflected in both, so this stays a current check.
        implied = capital / nominal
        checks.append({"name": "capital_nominal", "implied": implied,
                       "deviation": abs(implied / shares - 1)})
    good = [c for c in checks if c["deviation"] <= TOLERANCE]
    if not shares or shares <= 0:
        status = "INSUFFICIENT"
    elif len(good) >= 2:
        status = "VERIFIED"
    elif len(good) == 1 and len(checks) == 1:
        status = "VERIFIED_SINGLE_CHECK"
    elif checks:
        status = "CONFLICT"
    else:
        status = "INSUFFICIENT"
    anomalies = []
    for check in checks:
        factor = _anomaly(check["implied"] / shares if shares else None)
        if factor:
            anomalies.append({"check": check["name"], "factor": factor})
    return {
        "shares": shares,
        "nominal": nominal,
        "latest_capital": capital,
        "latest_capital_date": text(action.get("date")) if action else None,
        "checks": checks,
        "status": status,
        "anomalies": anomalies,
        "confidence": "HIGH" if status == "VERIFIED" else "MEDIUM" if status == "VERIFIED_SINGLE_CHECK" else "NONE",
    }


def validate_annual(record, current=None):
    """Validate the latest annual row and its dated share count.

    A row count can legitimately be pre-split. The row's implied nominal
    (capital / shares) is compared with the current nominal; the adjusted count
    must then match current shares, or the divergence must follow a later
    capital action. Otherwise it is quarantined.
    """
    annual = _latest(record.get("annual_rows"))
    if not annual:
        return {"status": "MISSING", "year": None, "reasons": ["NO_ANNUAL_ROW"], "notes": []}
    year = int(number(annual.get("exercice")))
    row_shares = number(annual.get("nombreTitres"))
    capital = number(annual.get("capitalSocial"))
    nominal = number(record.get("nominal"))
    current_shares = (current or {}).get("shares") or number(record.get("shares"))
    implied_nominal = capital / row_shares if capital and row_shares and row_shares > 0 else None
    split_factor = implied_nominal / nominal if implied_nominal and nominal else None
    adjusted_row = row_shares * split_factor if row_shares and split_factor else row_shares
    row_vs_current = _ratio(adjusted_row, current_shares)
    reasons, notes = [], []
    status = "OK"
    if number(annual.get("resultatNet")) is None or number(annual.get("capitalPropre")) is None:
        status = "INCOMPLETE"
        reasons.append("MISSING_CORE_FIGURE")
    if year < 2025:
        status = "STALE"
        reasons.append("FISCAL_YEAR_BEFORE_2025")
    if split_factor and abs(split_factor - 1) > TOLERANCE:
        notes.append("ANNUAL_ROW_COUNT_PRE_SPLIT_%gX" % round(split_factor, 2))
    if status == "OK" and row_vs_current is not None and abs(row_vs_current - 1) > TOLERANCE:
        action = _latest_capital_action(record)
        after = bool(action and text(action.get("date", ""))[:4].isdigit()
                     and int(action["date"][:4]) > year)
        if after:
            reasons.append("DATED_BEFORE_LATER_CAPITAL_ACTION")
        else:
            status = "SHARE_ROW_ANOMALY"
            reasons.append("UNEXPLAINED_SHARE_DIFFERENCE")
    return {
        "status": status, "year": year,
        "row_shares": row_shares, "implied_nominal": implied_nominal,
        "split_factor": split_factor, "adjusted_row_shares": adjusted_row,
        "row_vs_current": row_vs_current,
        "compte_consolide": annual.get("compteConsolide"),
        "resultat_net_mad": number(annual.get("resultatNet")),
        "capital_propre_mad": number(annual.get("capitalPropre")),
        "chiffre_affaire_mad": number(annual.get("chiffreAffaire")),
        "resultat_exploitation_mad": number(annual.get("resultatExploitation")),
        "reasons": reasons, "notes": notes,
    }


def propose(record, current=None):
    """Build a review proposal for application company fields.

    Units follow the application contract: ``cp`` is MAD; ``net_profit`` and
    ``revenue`` are millions MAD; ``bpa`` is MAD per share.
    """
    shares = validate_current_shares(record)
    annual = validate_annual(record, shares)
    sector = text(record.get("sector")) or ""
    lower = sector.lower()
    is_bank = any(word in lower for word in BANK_WORDS)
    is_insurer = any(word in lower for word in INSURER_WORDS)
    fields = {}
    warnings = list(annual.get("reasons") or [])
    notes = list(annual.get("notes") or [])
    status = "QUARANTINE"
    if shares["status"] in ("VERIFIED", "VERIFIED_SINGLE_CHECK") and annual["status"] in ("OK", "STALE", "SHARE_ROW_ANOMALY", "INCOMPLETE"):
        net = annual.get("resultat_net_mad")
        equity = annual.get("capital_propre_mad")
        revenue = annual.get("chiffre_affaire_mad")
        current_shares = shares["shares"]
        fields = {
            "na": current_shares,
            "fiscal_year": annual.get("year"),
            "fy_est": None,
            "rnpg_est": None,
            "ext_name": text(record.get("company")),
            "sector": sector or None,
            "cp": equity,
            "net_profit": round(net / 1e6, 3) if net is not None else None,
            "revenue": round(revenue / 1e6, 3) if revenue is not None else None,
            "bpa": round(net / current_shares, 4) if net is not None and current_shares else None,
            "roe": round(net / equity * 100, 2) if net is not None and equity else None,
            "profit_margin": (round(net / revenue * 100, 2)
                              if not is_bank and not is_insurer and net is not None and revenue else None),
        }
        if is_bank:
            warnings.append("BANK_PROFIT_GROUP_OVER_TOTAL_EQUITY")
        elif is_insurer:
            warnings.append("INSURER_SCOPE_REVIEW")
        if annual.get("compte_consolide") is False:
            warnings.append("STANDALONE_ACCOUNTS")
        if annual["status"] == "STALE":
            status = "STALE"
        elif annual["status"] == "SHARE_ROW_ANOMALY":
            status = "ANNUAL_REVIEW"
        else:
            status = "ANNUAL_REVIEW"
    elif shares["status"] == "CONFLICT":
        warnings.append("CURRENT_SHARE_COUNT_CONFLICT")
    else:
        warnings.append("CURRENT_SHARE_COUNT_INSUFFICIENT")
    if shares["status"] == "CONFLICT" or annual.get("status") == "SHARE_ROW_ANOMALY":
        review_class = "CONFLICT"
    elif annual.get("status") == "STALE":
        review_class = "STALE_REVIEW"
    elif is_bank:
        review_class = "BANK_REVIEW"
    elif is_insurer:
        review_class = "INSURER_REVIEW"
    elif annual.get("compte_consolide") is False:
        review_class = "STANDALONE_REVIEW"
    elif annual.get("compte_consolide") is not True:
        review_class = "ANNUAL_REVIEW"
    elif annual.get("status") == "OK" and annual.get("year") == 2025:
        review_class = "AUTO_ANNUAL_CANDIDATE"
    else:
        review_class = "ANNUAL_REVIEW"
    return {
        "status": status,
        "review_class": review_class,
        "fields": fields,
        "warnings": sorted(set(warnings)),
        "notes": sorted(set(notes)),
        "shares": shares,
        "annual": annual,
    }


def reconcile(records, companies=None, pages_dir=None, generated_at=None, saved_by_symbol=None):
    """Reconcile a snapshot; optionally compare with saved application rows."""
    by_name = {}
    for company in companies or []:
        name = text(company.get("name"))
        if name:
            by_name[name.upper()] = company
    saved_by_symbol = saved_by_symbol or {}
    out = []
    totals = {"companies": 0, "shares_verified": 0, "shares_conflict": 0,
              "shares_insufficient": 0, "annual_ok": 0, "annual_stale": 0,
              "annual_row_anomaly": 0, "review": 0, "quarantine": 0,
              "share_updates": 0, "annual_updates": 0,
              "auto_annual_candidate": 0, "bank_review": 0, "insurer_review": 0,
              "standalone_review": 0, "stale_review": 0, "conflict_review": 0}
    for record in records or []:
        if record.get("error"):
            continue
        symbol = text(record.get("symbol"))
        company = text(record.get("company")) or ""
        saved = saved_by_symbol.get(symbol) or by_name.get(company.upper())
        result = propose(record, saved)
        shares = result["shares"]
        annual = result["annual"]
        totals["companies"] += 1
        totals["shares_verified"] += shares["status"] in ("VERIFIED", "VERIFIED_SINGLE_CHECK")
        totals["shares_conflict"] += shares["status"] == "CONFLICT"
        totals["shares_insufficient"] += shares["status"] == "INSUFFICIENT"
        totals["annual_ok"] += annual["status"] == "OK"
        totals["annual_stale"] += annual["status"] == "STALE"
        totals["annual_row_anomaly"] += annual["status"] == "SHARE_ROW_ANOMALY"
        totals["review"] += result["status"] == "ANNUAL_REVIEW"
        totals["quarantine"] += result["status"] == "QUARANTINE"
        review_class = result["review_class"]
        if review_class == "AUTO_ANNUAL_CANDIDATE":
            totals["auto_annual_candidate"] += 1
        elif review_class == "BANK_REVIEW":
            totals["bank_review"] += 1
        elif review_class == "INSURER_REVIEW":
            totals["insurer_review"] += 1
        elif review_class == "STANDALONE_REVIEW":
            totals["standalone_review"] += 1
        elif review_class == "STALE_REVIEW":
            totals["stale_review"] += 1
        elif review_class == "CONFLICT":
            totals["conflict_review"] += 1
        evidence = {"url": f"https://www.casablanca-bourse.com/live-market/actions/cours?symbol={symbol}&ce={record.get('ce','')}"}
        if pages_dir:
            path = f"{pages_dir}/{symbol}.html"
            try:
                blob = open(path, "rb").read()
                evidence["page_sha256"] = hashlib.sha256(blob).hexdigest()
                evidence["page_bytes"] = len(blob)
            except OSError:
                pass
        prior = None
        if saved is not None:
            prior = {key: saved.get(key) for key in (
                "name", "na", "fiscal_year", "bpa", "cp", "net_profit", "revenue", "roe", "date")}
            proposed_shares = (result["fields"] or {}).get("na")
            if proposed_shares and prior.get("na"):
                if abs(proposed_shares / prior["na"] - 1) > TOLERANCE:
                    totals["share_updates"] += 1
            proposed_year = (result["fields"] or {}).get("fiscal_year")
            if proposed_year and (prior.get("fiscal_year") is None or proposed_year > prior["fiscal_year"]):
                totals["annual_updates"] += 1
        out.append({
            "symbol": symbol, "company": company,
            "isin": text(record.get("isin")), "sector": text(record.get("sector")),
            "status": result["status"], "review_class": result["review_class"],
            "warnings": result["warnings"],
            "notes": result["notes"],
            "current_shares": shares, "annual": annual,
            "proposed_fields": result["fields"], "saved": prior,
            "evidence": evidence,
        })
    summary = dict(totals)
    summary["generated_at"] = (generated_at or datetime.now(timezone.utc)).isoformat()
    return {"contract": CONTRACT, "summary": summary, "companies": out}


def to_csv_rows(report):
    rows = []
    for company in report.get("companies") or []:
        shares = company.get("current_shares") or {}
        annual = company.get("annual") or {}
        prior = company.get("saved") or {}
        fields = company.get("proposed_fields") or {}
        rows.append({
            "symbol": company.get("symbol"),
            "company": company.get("company"),
            "isin": company.get("isin"),
            "sector": company.get("sector"),
            "status": company.get("status"),
            "review_class": company.get("review_class"),
            "shares_status": shares.get("status"),
            "current_shares": shares.get("shares"),
            "saved_shares": prior.get("na"),
            "shares_delta": (round(shares.get("shares") / prior.get("na"), 4)
                             if shares.get("shares") and prior.get("na") else None),
            "annual_year": annual.get("year"),
            "saved_fiscal_year": prior.get("fiscal_year"),
            "annual_status": annual.get("status"),
            "annual_row_shares": annual.get("row_shares"),
            "split_factor": round(annual.get("split_factor"), 4) if annual.get("split_factor") else None,
            "row_vs_current": round(annual.get("row_vs_current"), 4) if annual.get("row_vs_current") else None,
            "proposed_na": fields.get("na"),
            "proposed_fiscal_year": fields.get("fiscal_year"),
            "proposed_bpa": fields.get("bpa"),
            "proposed_roe": fields.get("roe"),
            "proposed_cp": fields.get("cp"),
            "proposed_net_profit": fields.get("net_profit"),
            "proposed_revenue": fields.get("revenue"),
            "saved_bpa": prior.get("bpa"),
            "saved_roe": prior.get("roe"),
            "saved_cp": prior.get("cp"),
            "saved_net_profit": prior.get("net_profit"),
            "saved_revenue": prior.get("revenue"),
            "warnings": "; ".join(company.get("warnings") or []),
            "notes": "; ".join(company.get("notes") or []),
        })
    return rows


def to_markdown(report):
    summary = report.get("summary") or {}
    lines = [
        "# Exchange reconciliation report", "",
        f"Generated: {summary.get('generated_at')}", "",
        "| Metric | Count |", "|---|---:|",
    ]
    for key in ("companies", "shares_verified", "shares_conflict", "shares_insufficient",
                "annual_ok", "annual_stale", "annual_row_anomaly", "review", "quarantine"):
        lines.append(f"| {key.replace('_', ' ')} | {summary.get(key, 0)} |")
    lines += ["", "## Companies needing review or quarantine", "",
              "| Symbol | Company | Status | Shares | Annual | Warnings | Notes |", "|---|---|---|---|---|---|---|"]
    for company in report.get("companies") or []:
        if company.get("status") == "ANNUAL_REVIEW" and not company.get("warnings"):
            continue
        shares = company.get("current_shares") or {}
        annual = company.get("annual") or {}
        lines.append(
            f"| {company.get('symbol')} | {company.get('company')} | {company.get('status')} | "
            f"{shares.get('status')} {shares.get('shares')} | {annual.get('status')} {annual.get('year')} | "
            f"{'; '.join(company.get('warnings') or [])} | {'; '.join(company.get('notes') or [])} |")
    return "\n".join(lines) + "\n"
