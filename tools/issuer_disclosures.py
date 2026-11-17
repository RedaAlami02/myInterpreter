"""Parse saved official issuer records without confusing their publication dates.

Source URLs and complete HTML remain in ignored evidence. The public projection
contains corporate disclosures and their dates, never a claim of current ownership.
"""
from datetime import datetime
from decimal import Decimal
import re
import unicodedata

from bs4 import BeautifulSoup


def issuer_key(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    value = re.sub(r"\bS\.?A\.?\b", "", value)
    return re.sub(r"[^A-Z0-9]", "", value)


def iso_disclosure_date(value):
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def parse_issuer(content, expected_name):
    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table", class_="cols-1")
    if table is None:
        raise ValueError("Issuer characteristics table missing")
    fields = {}
    nested = {}
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            raise ValueError("Issuer characteristics layout changed")
        label = cells[0].get_text(" ", strip=True)
        if label in fields:
            raise ValueError("Duplicate issuer characteristic")
        fields[label] = cells[1].get_text(" ", strip=True)
        inner = cells[1].find("table")
        if inner:
            nested[label] = [[cell.get_text(" ", strip=True)
                              for cell in tr.find_all(["td", "th"], recursive=False)]
                             for tr in inner.find_all("tr")]
    if issuer_key(fields.get("Dénomination", "")) != issuer_key(expected_name):
        raise ValueError("Official issuer identity does not match saved company")
    shareholders = []
    rows = nested.get("Principaux actionnaires", [])
    if rows and rows[0] != ["Dénomination", "Date", "Pourcentage détenu"]:
        raise ValueError("Shareholder table header changed")
    for row in rows[1:]:
        if len(row) != 3:
            raise ValueError("Shareholder row layout changed")
        name, day, percentage = row
        number = Decimal(percentage.replace("%", "").replace(" ", "").replace(",", "."))
        if not number.is_finite() or not 0 <= number <= 100:
            raise ValueError("Invalid shareholder percentage")
        shareholders.append({"name": name, "pct": float(number),
                             "as_of": iso_disclosure_date(day)})
    # Retain all characteristics and nested governance rows, not only UI fields.
    return {"issuer_name": fields["Dénomination"],
            "sector_label": fields.get("Secteur d'activité") or None,
            "shareholders": shareholders, "characteristics": fields,
            "structured_tables": nested,
            "shareholder_dates": sorted({row["as_of"] for row in shareholders}),
            "current_ownership_independently_verified": False}


def merge_issuer(profile, disclosure, captured_at, evidence_hash):
    if issuer_key(disclosure["issuer_name"]) != issuer_key(profile["c_name"]):
        raise ValueError("Issuer identity mismatch")
    profile["issuer_disclosures"] = {**disclosure, "captured_at": captured_at,
                                     "evidence_sha256": evidence_hash}
    # Existing sector values also select corporate/banking financial formulas.
    # Keep the exchange/regulator classification distinct from that selector.
    if not profile.get("sector") and disclosure.get("sector_label"):
        profile["sector"] = disclosure["sector_label"]
        profile["field_origins"]["sector"] = "official_issuer_record"
    if not profile.get("shareholders") and disclosure["shareholders"]:
        profile["shareholders"] = disclosure["shareholders"]
        profile["field_origins"]["shareholders"] = "official_issuer_record_dated_disclosure"
    profile.setdefault("financials_captured_at", profile["captured_at"])
    if datetime.fromisoformat(captured_at) > datetime.fromisoformat(profile["captured_at"]):
        profile["captured_at"] = captured_at
    return profile
