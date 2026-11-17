"""Dividend calendar parsing and payment-period rules.

This is the managed-collection copy of the archival Appwrite function's parser.
The rules are the shared contract exercised by `tests/fixtures/dividend_periods.json`
in PHP, Dart and Python; keep all three agreeing with that fixture.
"""

from datetime import date
import html
import re
import unicodedata

DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4})')
CELL_RE = re.compile(r'<t[dh].*?</t[dh]>', re.S)
ROW_RE = re.compile(r'<tr.*?</tr>', re.S)
TABLE_RE = re.compile(r'<table.*?</table>', re.S)
TOOLTIP_CUT = re.compile(
    r'\s*(Date de détachement|Cours action|Calcul\s*:|Cours au détachement)', re.I)
TICKER_SUFFIX = re.compile(r'\s*\(([A-Z0-9]{2,6})\)\s*$')


def quality_issue(row):
    """Same payment-period decisions as core/dividends.php and dividends.dart."""
    year = row.get('year', 0)
    if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 9999:
        return 'invalid_payment_year'
    dates = {}
    for field in ('ex_date', 'pay_date', 'pay_date_end'):
        value = (row.get(field) or '').strip()
        if not value:
            continue
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return 'invalid_calendar_date'
            parsed = date.fromisoformat(value)
        except ValueError:
            return 'invalid_calendar_date'
        dates[field] = parsed
        if field != 'ex_date' and parsed.year != year:
            return 'payment_year_mismatch'
    ex, pay, end = (dates.get(field) for field in ('ex_date', 'pay_date', 'pay_date_end'))
    if ex and ex.year != year and not (pay and ex.year == year - 1):
        return 'payment_year_mismatch'
    if (ex and pay and pay < ex) or (end and (not pay or end < pay)):
        return 'invalid_date_order'
    if row.get('confirmed') and not ex:
        return 'missing_confirmation_date'
    return None


def _clean(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', fragment))).strip()


def _amount(text: str):
    """French-formatted money to float. '1 279,00' -> 1279.0, '—' -> None."""
    t = text.replace('\xa0', '').replace(' ', '').replace(' ', '')
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    t = re.sub(r'[^\d.\-]', '', t)
    if not t or t in ('.', '-'):
        return None
    try:
        value = float(t)
    except ValueError:
        return None
    return value if value > 0 else None


def _iso(value: str):
    match = DATE_RE.search(value or '')
    if not match:
        return None
    day, month, year = match.group(1).split('/')
    return f"{year}-{month}-{day}"


def normalise_name(value: str) -> str:
    """Fold an issuer name to a comparison key."""
    value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode().upper()
    value = TICKER_SUFFIX.sub('', value)
    value = re.sub(r'\b(S\.?A\.?|SA|GROUP|GROUPE|ASSURANCES?|MAROC|DU MAROC|AUTOMOBILES?'
                   r'|DE|DU|DES|D)\b', '', value)
    return re.sub(r'[^A-Z0-9]', '', value)


def ticker_of(name: str):
    match = TICKER_SUFFIX.search(
        unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().upper())
    return match.group(1) if match else None


# The two issuers whose names share no normalised form with ours. Mirrors
# COMPANY_ALIASES in config/config.php — keep the two in step.
ALIASES = {
    normalise_name('MAROC TELECOM'): 'IAM',
    normalise_name('Total Energies Maroc'): 'TOTALENERGIES MAROC',
}


def parse_calendar(page: str, year: int) -> list:
    """Rows from one calendar page. Raises if the page shape is not what we expect."""
    tables = TABLE_RE.findall(page)
    if not tables:
        raise ValueError(f"no <table> in the {year} calendar — page shape changed")
    rows = ROW_RE.findall(tables[0])
    if len(rows) < 2:
        raise ValueError(f"{year} calendar table has no data rows")
    header = [_clean(cell) for cell in CELL_RE.findall(rows[0])]
    if len(header) != 7 or 'metteur' not in header[0]:
        raise ValueError(f"{year} calendar header changed: {header}")
    output = []
    for raw in rows[1:]:
        cells = [_clean(cell) for cell in CELL_RE.findall(raw)]
        if len(cells) < 7:
            continue
        name = cells[0].strip()
        if not name:
            continue
        ex_dates = DATE_RE.findall(cells[3])
        pay_dates = DATE_RE.findall(cells[4])
        parsed = {
            'issuer': name,
            'key': normalise_name(name),
            'ticker': ticker_of(name),
            'year': year,
            'amount': _amount(cells[1]),
            'yield_src': TOOLTIP_CUT.split(cells[2])[0].strip() or None,
            'ex_date': _iso(ex_dates[0]) if ex_dates else None,
            'pay_date': _iso(pay_dates[0]) if pay_dates else None,
            'pay_date_end': _iso(pay_dates[1]) if len(pay_dates) > 1 else None,
            # Only the source's own ex-date marks an AGM decision.
            'confirmed': bool(ex_dates),
            'type': cells[5] or None,
            'frequency': cells[6] or None,
        }
        issue = quality_issue(parsed)
        if issue is not None:
            parsed['verification_issue'] = issue
        output.append(parsed)
    return output


def resolve(key: str, index: dict, ticker: str = None):
    """Map a normalised issuer key to our stored company name, or None."""
    if key in ALIASES:
        return ALIASES[key]
    hit = index.get(key)
    if hit:
        return hit
    return index.get(normalise_name(ticker)) if ticker else None


def dedupe(rows: list) -> list:
    """Collapse the source's duplicate spellings; keep the most complete row."""
    best = {}
    for row in rows:
        group = (row.get('c_name') or row['key'], row['year'], row['type'])
        rank = (bool(row['confirmed']), bool(row['pay_date']), bool(row['amount']))
        if group not in best or rank > best[group][0]:
            best[group] = (rank, row)
    return [row for _, row in best.values()]


def decode_page(raw: bytes, charset: str = None) -> str:
    """Decode archived bytes without losing the original evidence."""
    if charset:
        try:
            return raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            raise ValueError("DECLARED_CHARSET_INVALID") from None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("PAGE_NOT_UTF8") from None
