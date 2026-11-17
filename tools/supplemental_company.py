"""Parse explicitly identified supplementary company statistics for review.

Endpoints and instrument mappings belong in private configuration. Capturing a
page does not establish the publication date or financial authority of its data.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re

from bs4 import BeautifulSoup

LABELS = {
    'Société': 'company_name', 'ISIN': 'isin', 'Secteur': 'sector',
    'Capitalisation boursière': 'market_cap', "Nombre d'actions": 'shares',
    'Actions en circulation (flottant)': 'free_float',
}
DIVIDEND_HEADER = ['Année', 'Date détachement', 'Date paiement', 'Montant Brut', 'Montant Net']


def number(value):
    """Exact French-formatted decimal; no booleans, non-finite values or guessing."""
    if not isinstance(value, str):
        raise ValueError('INVALID_SOURCE_NUMBER')
    value = re.sub(r'[\s\u00a0\u202f]', '', value).replace(',', '.')
    if not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value):
        raise ValueError('INVALID_SOURCE_NUMBER')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError('INVALID_SOURCE_NUMBER') from None
    if not result.is_finite() or abs(result) > Decimal('1e15'):
        raise ValueError('INVALID_SOURCE_NUMBER')
    return format(result, 'f')


def _day(value):
    if value in ('', '-', '—'):
        return None
    try:
        return datetime.strptime(value, '%d/%m/%Y').date().isoformat()
    except ValueError:
        raise ValueError('INVALID_DIVIDEND_DATE') from None


def parse_statistics(content, expected_isin, captured_at):
    if not isinstance(content, bytes) or len(content) > 3_000_000:
        raise ValueError('INVALID_STATISTICS_BODY')
    if not isinstance(expected_isin, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', expected_isin):
        raise ValueError('INVALID_EXPECTED_ISIN')
    try:
        moment = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError('INVALID_CAPTURE_TIME') from None
    soup = BeautifulSoup(content, 'html.parser')
    identity = None
    dividends = []
    dividend_table_seen = False
    for table in soup.find_all('table'):
        rows = [[cell.get_text(' ', strip=True) for cell in row.find_all(['td', 'th'], recursive=False)]
                for row in table.find_all('tr') if row.find_parent('table') is table]
        if any(row and row[0] == 'ISIN' for row in rows):
            if identity is not None:
                raise ValueError('AMBIGUOUS_STATISTICS_IDENTITY')
            identity = {}
            for row in rows:
                if len(row) != 2 or row[0] not in LABELS:
                    raise ValueError('STATISTICS_LAYOUT_CHANGED')
                key = LABELS[row[0]]
                if key in identity:
                    raise ValueError('DUPLICATE_STATISTICS_FIELD')
                identity[key] = row[1]
        if rows and rows[0] == DIVIDEND_HEADER:
            if dividend_table_seen:
                raise ValueError('AMBIGUOUS_DIVIDEND_TABLE')
            dividend_table_seen = True
            seen = set()
            for row in rows[1:]:
                if len(row) != 5 or not re.fullmatch(r'20[0-9]{2}', row[0]):
                    raise ValueError('DIVIDEND_LAYOUT_CHANGED')
                record = {'source_year_label':int(row[0]), 'ex_date':_day(row[1]),
                          'pay_date':_day(row[2]), 'gross_decimal':number(row[3]),
                          'net_decimal':number(row[4]), 'currency':None,
                          'period_basis':'SOURCE_YEAR_LABEL', 'publication_eligible':False}
                if Decimal(record['gross_decimal']) < 0 or Decimal(record['net_decimal']) < 0:
                    raise ValueError('INVALID_DIVIDEND_AMOUNT')
                key = (row[0], record['ex_date'], record['pay_date'])
                if key in seen:
                    raise ValueError('DUPLICATE_DIVIDEND_ROW')
                seen.add(key)
                dividends.append(record)
    if not identity or identity.get('isin') != expected_isin or not identity.get('company_name'):
        raise ValueError('STATISTICS_IDENTITY_DIFFERS')
    for key in ['market_cap', 'shares', 'free_float']:
        raw = identity.get(key)
        if raw in (None, '', '-', '—'):
            identity[key] = None
            continue
        value = number(raw)
        if Decimal(value) < 0 or (key != 'market_cap' and Decimal(value) != Decimal(value).to_integral_value()):
            raise ValueError('INVALID_SHARE_OR_CAPITAL_VALUE')
        identity[key] = value
    return {'contract':'supplemental-company-review/v1', 'identity':identity,
            'dividends':dividends, 'captured_at':moment.astimezone(timezone.utc).isoformat(),
            'source_as_of':None, 'source_published_at':None, 'market_cap_currency':None,
            'evidence_sha256':hashlib.sha256(content).hexdigest(),
            'annual_financial_statements_available':False, 'publication_eligible':False,
            'review_required':['CURRENT_SHARE_COUNT','EFFECTIVE_DATE','UNITS','PRIMARY_CORROBORATION']}
