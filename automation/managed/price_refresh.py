"""Existing price-row calculations on a verified saved archive, without writes.

Application fields are extracted from the exact bound raw observation. Native
paths stay in private configuration. This shadow derivation is deliberately not
a public.data/latest_prices writer: references must not become fresh valuations.
"""

from decimal import Decimal

import app_feed
import fundamental_frame
import market_frame
import price_jobs
import worker

NUMERIC_FIELDS = {
    'variation', 'variation_v', 'cours_ref', 'open_price', 'high', 'low',
    'volume', 'qty_traded', 'market_cap',
}
MAX_CHART_CHARS = 65536


def _bindings(value):
    if not isinstance(value, dict) or set(value) - {'quotes', 'indices', 'instruments', 'calculation_rules'}:
        raise ValueError('Invalid application field bindings')
    if value.get('calculation_rules') not in (None, 'legacy_getprice/v1'):
        raise ValueError('Unknown application field calculations')
    for view, fields in value.items():
        if view == 'calculation_rules':
            continue
        if not isinstance(fields, dict) or set(fields) - (NUMERIC_FIELDS | {'data_chart'}):
            raise ValueError('Invalid application fields')
        for field, binding in fields.items():
            if (not isinstance(binding, dict)
                    or set(binding) - {'path', 'type', 'locale', 'optional', 'blank_is_null'}
                    or not market_frame.valid_path(binding.get('path'))
                    or binding.get('type') != ('text' if field == 'data_chart' else 'decimal')
                    or binding.get('locale', 'plain') not in {'plain', 'comma', 'comma_dot_grouping'}
                    or type(binding.get('optional', False)) is not bool
                    or type(binding.get('blank_is_null', False)) is not bool):
                raise ValueError('Invalid application field binding')


def _fields(raw_row, document, bindings):
    values = {}
    for field, binding in bindings.items():
        if field == 'data_chart':
            try:
                value = market_frame.get(raw_row, binding['path'])
            except market_frame.FrameError:
                if not binding.get('optional'):
                    raise
                value = None
            if value is None or (value == '' and binding.get('blank_is_null')):
                if not binding.get('optional'):
                    raise ValueError('Missing required price chart')
                value = None
            elif not isinstance(value, str) or len(value) > MAX_CHART_CHARS:
                raise ValueError('Invalid or oversized price chart')
        else:
            value = market_frame.extract(binding, raw_row, document)
        if value is None or field == 'data_chart':
            values[field] = value
        elif field == 'qty_traded':
            number = Decimal(value)
            if number != number.to_integral_value() or not 0 <= number <= 2**63 - 1:
                raise ValueError('Invalid traded quantity')
            values[field] = int(number)
        else:
            values[field] = float(value)
    return values


def build(blob, digest, config, mapping, companies, *, as_of, field_bindings=None, last_known=()):
    """Full stock/index row shapes + original enrichment choices, shadow only.

    ``companies`` contains existing application rows, keyed by original company
    ID. The result keeps provenance outside the legacy row, so its date is never
    confused with a trade timestamp. Saved prices retain their old record date;
    unknown market fields remain absent. Invalid field extraction fails explicitly.
    """
    bindings = {} if field_bindings is None else field_bindings
    _bindings(bindings)
    saved = tuple(last_known)
    display = app_feed.build_display_prices(blob, digest, config, mapping,
                                           as_of=as_of, last_known=saved)
    envelope, frame, _, _ = app_feed.verified_archive(blob, digest, config)
    document = market_frame.read_json(bytes.fromhex(envelope['captures'][0]['raw_hex']))
    identities = {item['asset_key']: item for kind in ('stocks', 'indices') for item in mapping[kind]}
    rows, excluded = [], []
    for resolved in display['rows']:
        if resolved['price_decimal'] is None:
            reason = (resolved['quote_status'] if resolved['price_basis'] == 'UNAVAILABLE'
                      else resolved['price_basis'])
            excluded.append({'asset_key': resolved['asset_key'], 'reason': reason})
            continue
        identity = identities[resolved['asset_key']]
        company = None
        basis = resolved['price_basis']
        recorded_at = (resolved['original_recorded_at'] if basis == 'RECOVERED_LAST_KNOWN'
                       else resolved['captured_at'])
        fundamental_at = None
        if resolved['instrument_type'] == 'STOCK':
            company = companies.get(identity['company_id'])
            if company is None or company.get('name') != identity['c_name']:
                excluded.append({'asset_key': resolved['asset_key'], 'reason': 'COMPANY_IDENTITY_UNAVAILABLE'})
                continue
            dates = [worker.utc(company[field]) for field in ('date', '$updatedAt', 'available_at') if company.get(field)]
            if not dates:
                excluded.append({'asset_key': resolved['asset_key'], 'reason': 'UNKNOWN_FUNDAMENTAL_AVAILABILITY'})
                continue
            fundamental_at = max(dates)
            if fundamental_at > min(as_of, worker.utc(recorded_at)):
                excluded.append({'asset_key': resolved['asset_key'], 'reason': 'FUTURE_FUNDAMENTALS'})
                continue
        market = {'symbol': identity['symbol']}
        if basis == 'RECOVERED_LAST_KNOWN':
            # Reusing a saved price must not manufacture a new observation date
            # or attach today's market cap, volume and chart to the old price.
            recorded_at = resolved['original_recorded_at']
        else:
            recorded_at = resolved['captured_at']
            view = ('indices' if resolved['instrument_type'] == 'INDEX' else
                    'quotes' if basis == 'OBSERVED_QUOTE' else 'instruments')
            used_ids = {row['observation_id'] for row in resolved['observations']}
            observations = [row for row in frame['views'][view]
                            if row['source_identity'] == identity['source_identity']
                            and row['observation_id'] in used_ids]
            raw_rows = market_frame.get(document, config['recipe']['views'][view]['rows_path'])
            candidates = [_fields(raw_rows[observation['raw_row_index']], document,
                                  bindings.get(view, {})) for observation in observations]
            if not candidates or any(item != candidates[0] for item in candidates[1:]):
                excluded.append({'asset_key': resolved['asset_key'], 'reason': 'CONFLICTING_MARKET_FIELDS'})
                continue
            market.update(candidates[0])
        price = float(resolved['price_decimal'])
        if basis != 'RECOVERED_LAST_KNOWN' and bindings.get('calculation_rules') == 'legacy_getprice/v1':
            market = fundamental_frame.legacy_price_fields(price, market, view)
        if company is None:
            value = fundamental_frame.index_document(identity['c_name'], price, market, recorded_at)
        else:
            value = fundamental_frame.price_document(identity['c_name'], price, company, market, recorded_at)
        provenance = {**resolved, 'fundamentals_available_at': fundamental_at.isoformat() if fundamental_at else None}
        rows.append({'asset_key': resolved['asset_key'], 'row': value, 'provenance': provenance})
    stock_ids = {identity['company_id']: identity for identity in mapping['stocks']}
    # Keep the original company read order, including fiscal-year tie ordering.
    current_companies = {
        company['name']: company for identifier, company in companies.items()
        if identifier in stock_ids and company.get('name') == stock_ids[identifier]['c_name']
        and all(worker.utc(company[field]) <= as_of for field in ('date', '$updatedAt', 'available_at') if company.get(field))
    }
    return {
        'mode': 'SHADOW_ONLY', 'evaluation': 'SAVED_ARCHIVE_DERIVATION',
        'source_execution': envelope['execution'], 'archive_sha256': digest,
        'application_fields_sha256': app_feed.fingerprint(bindings),
        'captured_at': display['captured_at'], 'as_of': display['as_of'],
        'rows': rows, 'excluded': excluded,
        'enrichment_jobs': price_jobs.enrichment_jobs(current_companies,
            {identity['symbol']: identity['c_name'] for identity in mapping['stocks']}, as_of),
        'acquisition_completeness': display['acquisition_completeness'],
        'prediction_eligible': False, 'portfolio_valuation_eligible': False,
    }


def publication(blob, digest, config, mapping, companies, quote_candidate, *, as_of, field_bindings):
    """Current shadow publication, bound to the exact separately published quote head.

    Stale and saved-price rows stay display-only local references. Publication
    never changes historical market tables or valuation prices.
    """
    builder = (app_feed.build_with_references if quote_candidate.get('contract') == 'app-market-candidate/v2'
               else app_feed.build)
    expected = builder(blob, digest, config, mapping, as_of=as_of)
    if expected != quote_candidate or expected['source_execution'] != 'CURRENT_ACQUISITION':
        raise ValueError('Exact current quote candidate required')
    result = build(blob, digest, config, mapping, companies, as_of=as_of, field_bindings=field_bindings)
    result.pop('enrichment_jobs')
    eligible = {row['asset_key'] for row in expected['rows']
                if row['status'] in {'REPORTED_DATE_ONLY', 'REPORTED_EVENT_VERIFIED'}
                or row.get('reference_price') is not None}
    result['excluded'].extend({'asset_key': item['asset_key'], 'reason': 'NO_CURRENT_DISPLAY_EVIDENCE'}
                              for item in result['rows'] if item['asset_key'] not in eligible)
    result['rows'] = [item for item in result['rows'] if item['asset_key'] in eligible]
    result.update(contract='app-price-rows/v1', provider_namespace=config['provider_namespace'],
                  quote_payload_sha256=app_feed.fingerprint(expected))
    return result
