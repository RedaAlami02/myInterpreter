"""Exact source facts for review. Archive integrity never confers financial authority.

No database writes, no unit inference, and no forecast-to-reported promotion.
"""
from decimal import Decimal, InvalidOperation
import json
import re

import fundamental_feed

METRICS = {
    'ca': 'revenue', 'rnpg': 'net_profit', 'fp': 'equity', 'ebe': 'ebitda',
    'ebit': 'ebit', 'dn': 'net_debt', 'tn': 'net_cash', 'fcf': 'fcf',
    'actif': 'total_assets', 'nmt': 'shares', 'dpa': 'dividend_per_share',
}
FINANCIAL_SECTIONS = {
    'chiffreAffaires': 'revenue', 'beneficeParAction': 'reported_eps',
    'dividendeParAction': 'dividend_per_share', 'ebit': 'ebit',
    'fondsPropres': 'equity', 'freeCashFlow': 'fcf', 'margeNette': 'profit_margin',
}
YEAR = re.compile(r'^([0-9]{4})(p?)$')


def exact_number(value):
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (Decimal, int, str)):
        return None
    if isinstance(value, str) and not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value):
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or abs(number) > Decimal('1e15'):
        return None
    return format(number, 'f')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_FINANCIAL_JSON_KEY')
        result[key] = value
    return result


def build(blob, digest, config, index):
    archive, _ = fundamental_feed.verified_archive(blob, digest, config)
    names = fundamental_feed.validate_index(index, config['provider_namespace'])
    name = names.get(archive['symbol'])
    if not name:
        raise ValueError('UNMAPPED_FINANCIAL_IDENTITY')
    captures = {entry['request_index']: entry for entry in archive['captures']}
    facts, issues = [], []
    for target in archive['targets']:
        kind = target['kind']
        if kind not in METRICS and kind != 'financial':
            continue
        capture = captures[target['request_index']]
        try:
            page = json.loads(bytes.fromhex(capture['raw_hex']), parse_float=Decimal,
                              parse_int=Decimal, object_pairs_hook=unique_object)
        except (ValueError, UnicodeDecodeError):
            issues.append({'kind': kind, 'code': 'INVALID_OR_DUPLICATE_FINANCIAL_JSON'})
            continue
        series = []
        if kind == 'financial':
            sections = page.get('financialData') if isinstance(page, dict) else None
            if isinstance(sections, dict):
                series = [(metric, sections.get(section), ['financialData', section])
                          for section, metric in FINANCIAL_SECTIONS.items()]
            else:
                issues.append({'kind': kind, 'code': 'ANNUAL_SERIES_UNAVAILABLE'})
        else:
            series = [(METRICS[kind], page.get('data') if isinstance(page, dict) else None, ['data'])]
        for metric, values, path in series:
            if not isinstance(values, dict):
                issues.append({'kind': kind, 'metric': metric, 'code': 'ANNUAL_SERIES_UNAVAILABLE'})
                continue
            for label, raw in sorted(values.items()):
                match = YEAR.fullmatch(label)
                if not match or not 2000 <= int(match[1]) <= 2100:
                    continue
                number = exact_number(raw)
                if number is None:
                    issues.append({'kind': kind, 'metric': metric, 'year_label': label, 'code': 'VALUE_UNAVAILABLE'})
                    continue
                facts.append({
                    'metric': metric, 'value_decimal': number,
                    'source_year': int(match[1]), 'period_basis': 'SOURCE_YEAR_LABEL',
                    'is_estimate': bool(match[2]), 'unit': None, 'scope': None,
                    'published_at': None, 'received_at': capture['received_at'],
                    'archive_sha256': digest, 'raw_sha256': capture['sha256'],
                    'capture_id': capture['capture_id'], 'value_path': path + [label],
                    'authority': 'UNVERIFIED_CANDIDATE', 'publication_eligible': False,
                })
    return {
        'contract': 'financial-review-candidate/v1', 'symbol': archive['symbol'],
        'c_name': name, 'captured_at': archive['completed_at'],
        'archive_sha256': digest, 'archive_integrity_verified': True,
        'financial_authority_verified': False, 'publication_eligible': False,
        'reported_facts': [fact for fact in facts if not fact['is_estimate']],
        'estimated_facts': [fact for fact in facts if fact['is_estimate']],
        'issues': issues,
        'review_required': ['PRIMARY_DOCUMENT', 'PERIOD', 'UNITS', 'ACCOUNTING_SCOPE', 'PUBLICATION_DATE'],
    }
