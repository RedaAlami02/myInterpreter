"""Fresh source acquisition and truthful comparison for administrator refresh jobs.

No database mutation. Source recipes remain private. A changed API value is a
candidate, never financial approval. Original response timestamps are preserved.
"""
import hashlib
import json
import re

import financial_evidence
import fundamental_collect
import fundamental_feed
import worker

BIOGRAPHICAL = {'ext_name', 'sector', 'description', 'shareholders'}
MAX_COMPANIES = 5


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _same(left, right):
    # Text fields are not coerced; numeric database strings may match JSON numbers.
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(right, (int, float)):
        from decimal import Decimal, InvalidOperation
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return False
    if isinstance(left, str) and isinstance(right, str):
        try:
            a, b = json.loads(left), json.loads(right)
            if isinstance(a, list) and isinstance(b, list):
                return a == b
        except ValueError:
            pass
    return left == right


def compare(document, evidence, baseline, *, primary_reviewed=False):
    """Explain gaps/changes without mistaking capture freshness for fiscal recency."""
    if not isinstance(baseline, dict) or baseline.get('name') != document['c_name']:
        raise ValueError('REFRESH_BASELINE_IDENTITY_DIFFERS')
    if type(primary_reviewed) is not bool:
        raise ValueError('INVALID_REVIEW_FLAG')
    changes = []
    for key, value in document['fields'].items():
        if value is None or value == '' or _same(baseline.get(key), value):
            continue
        financial = key not in BIOGRAPHICAL
        changes.append({'field': key, 'before': baseline.get(key), 'candidate': value,
                        'change': 'MISSING' if baseline.get(key) in (None, '') else 'CHANGED',
                        'decision': ('PRIMARY_REVIEW_PROTECTED' if primary_reviewed else 'FINANCIAL_REVIEW_REQUIRED')
                        if financial else 'BIOGRAPHY_REVIEW_REQUIRED'})
    source_year, stored_year = document['fields'].get('fiscal_year'), baseline.get('fiscal_year')
    period = 'UNKNOWN'
    if type(source_year) is int and type(stored_year) is int:
        period = 'OLDER' if source_year < stored_year else 'NEWER' if source_year > stored_year else 'SAME'
    elif type(source_year) is int:
        period = 'SOURCE_YEAR_AVAILABLE'
    latest_years = {}
    for fact in evidence['reported_facts']:
        metric, year = fact['metric'], fact['source_year']
        latest_years[metric] = max(year, latest_years.get(metric, year))
    return {'contract': 'profile-refresh-comparison/v1', 'symbol': document['symbol'],
            'c_name': document['c_name'], 'captured_at': evidence['captured_at'],
            'source_published_at': None, 'source_year': source_year, 'stored_year': stored_year,
            'period_comparison': period, 'changes': changes,
            'latest_reported_years': latest_years,
            'missing_fields': sorted(key for key, value in document['fields'].items() if value is None),
            'financial_coverage': 'REPORTED_SOURCE_VALUES' if evidence['reported_facts'] else 'UNAVAILABLE',
            'reported_facts': len(evidence['reported_facts']),
            'estimated_facts': len(evidence['estimated_facts']),
            'issues': evidence['issues'], 'primary_reviewed': primary_reviewed,
            'publication_eligible': False, 'production_writes': 0}


def capture(config, index, symbol, baseline, *, fetcher=worker.fetch, primary_reviewed=False, seconds=120):
    names = fundamental_feed.validate_index(index, config['provider_namespace'])
    if symbol not in names or baseline.get('name') != names[symbol]:
        raise ValueError('REFRESH_BASELINE_IDENTITY_DIFFERS')
    source_errors = []

    def request(recipe, deadline, maximum):
        try:
            return fetcher(recipe, deadline, maximum)
        except worker.AcquisitionError as error:
            code = str(error)
            source_errors.append({'kind': recipe['kind'],
                'code': code if re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code) else 'SOURCE_REQUEST_FAILED',
                'http_status': error.http_status if type(error.http_status) is int and 100 <= error.http_status <= 599 else None})
            raise

    archive = fundamental_collect.acquire(config, symbol, fetcher=request,
                                          seconds=seconds, subject_scoped=True)
    digest, blob = worker.packed(archive)
    try:
        evidence = financial_evidence.build(blob, digest, config, index)
        candidate = fundamental_feed.build(blob, digest, config, index)
    except Exception:
        return {'archive': blob, 'report': {
            'symbol': symbol, 'status': 'CANDIDATE_VALIDATION_FAILED',
            'code': 'CAPTURE_RETAINED_FOR_INSPECTION', 'archive_sha256': digest,
            'responses': len(archive['captures']), 'source_errors': source_errors,
            'publication_eligible': False, 'production_writes': 0}}
    report = compare(candidate, evidence, baseline, primary_reviewed=primary_reviewed)
    report.update(status='CAPTURED_FOR_REVIEW' if candidate['completeness'] == 'COMPLETE' else 'PARTIAL_CAPTURE',
                  responses=len(archive['captures']), transport_errors=len(archive['errors']),
                  source_errors=source_errors,
                  archive_sha256=digest)
    return {'report': report, 'archive': blob, 'candidate': candidate, 'evidence': evidence}


def capture_batch(config, index, baselines, *, fetcher=worker.fetch, primary_reviewed=(), on_result=None):
    """Bounded independent companies; share only the registry within this invocation.

    Callers persist each on_result before continuing. A new invocation always
    fetches the registry again; annual/biographical responses are never cached.
    """
    if not isinstance(baselines, dict) or not 1 <= len(baselines) <= MAX_COMPANIES:
        raise ValueError('INVALID_REFRESH_BATCH')
    names = fundamental_feed.validate_index(index, config['provider_namespace'])
    if any(not isinstance(symbol, str) or not fundamental_collect.SYMBOL.fullmatch(symbol)
           or symbol not in names or not isinstance(row, dict) or row.get('name') != names[symbol]
           for symbol, row in baselines.items()):
        raise ValueError('REFRESH_BASELINE_IDENTITY_DIFFERS')
    registry = {}
    network, reused = 0, 0

    def request(recipe, deadline, maximum):
        nonlocal network, reused
        key = hashlib.sha256(_canonical(recipe).encode()).hexdigest()
        if recipe['kind'] == 'symlinks' and key in registry:
            reused += 1
            return registry[key]
        network += 1
        result = fetcher(recipe, deadline, maximum)
        if recipe['kind'] == 'symlinks':
            registry[key] = result
        return result

    reports = []
    for symbol, baseline in baselines.items():
        try:
            result = capture(config, index, symbol, baseline, fetcher=request,
                             primary_reviewed=symbol in primary_reviewed)
        except Exception:
            # Provider URLs, response bodies and exception details never enter UI/logs.
            result = {'report': {'symbol': symbol, 'status': 'CAPTURE_FAILED',
                                'code': 'SOURCE_CAPTURE_OR_VALIDATION_FAILED', 'production_writes': 0}}
        if on_result is not None:
            on_result(symbol, result)  # Persistence failure aborts, rather than losing evidence.
        reports.append(result['report'])
    return {'contract': 'profile-refresh-batch/v1', 'reports': reports,
            'network_requests': network, 'registry_reuses': reused,
            'production_writes': 0, 'publication_eligible': False}
