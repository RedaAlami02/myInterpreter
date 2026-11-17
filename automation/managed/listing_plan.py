"""Existing listing decisions on exact archived catalog bytes; no writes or fetches."""
import hashlib
import re

import app_feed
import market_frame
import price_jobs
import worker

CONTRACT = 'reviewed-listing-update/v1'


def catalog_fingerprint_sql():
    return """SELECT encode(sha256(convert_to(jsonb_build_object(
        'companies',coalesce((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM public.company c),'[]'::jsonb),
        'mappings',coalesce((SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id) FROM public.format f),'[]'::jsonb)
        )::text,'UTF8')),'hex')"""


def build(blob, digest, config, bindings, companies, mappings, before_sha256):
    if not isinstance(bindings, dict) or set(bindings) != {'contract','symbol_path','name_path'} or bindings['contract'] != 'private-listing-bindings/v1':
        raise worker.AcquisitionError('INVALID_LISTING_BINDINGS')
    for path in (bindings['symbol_path'], bindings['name_path']):
        if not isinstance(path,list) or not path or len(path)>10 or any(not isinstance(v,str) or not app_feed.clean(v,100) for v in path):
            raise worker.AcquisitionError('INVALID_LISTING_BINDINGS')
    if not isinstance(before_sha256,str) or not re.fullmatch('[a-f0-9]{64}',before_sha256):
        raise worker.AcquisitionError('CATALOG_FINGERPRINT_REQUIRED')
    envelope, frame, _, _ = app_feed.verified_archive(blob,digest,config)
    if frame is None or any(v.get('view')=='instruments' for v in frame['issues']):
        raise worker.AcquisitionError('VERIFIED_CATALOG_REQUIRED')
    by_name = {}
    for row in companies:
        if not app_feed.clean(row.get('id')) or not app_feed.clean(row.get('name')) or row['name'] in by_name:
            raise worker.AcquisitionError('AMBIGUOUS_EXISTING_COMPANY')
        by_name[row['name']] = row['id']
    symbols = {}
    for row in mappings:
        if not app_feed.clean(row.get('symbol')) or not app_feed.clean(row.get('name')) or row['symbol'] in symbols:
            raise worker.AcquisitionError('AMBIGUOUS_EXISTING_MAPPING')
        symbols[row['symbol']] = row['name']
    raw = market_frame.read_json(bytes.fromhex(envelope['captures'][0]['raw_hex']))
    raw_rows = market_frame.get(raw,config['recipe']['views']['instruments']['rows_path'])
    instruments, evidence = [], {}
    for observation in frame['views']['instruments']:
        row = raw_rows[observation['raw_row_index']]
        symbol = market_frame.get(row,bindings['symbol_path'])
        name = market_frame.get(row,bindings['name_path'])
        if not app_feed.clean(symbol,100) or not app_feed.clean(name) or symbol!=symbol.strip() or name!=name.strip():
            raise worker.AcquisitionError('INVALID_LISTING_IDENTITY')
        instruments.append({'symbol':symbol,'name':name})
        evidence.setdefault((symbol,name),[]).append({
            'observation_id':observation['observation_id'],
            'source_identity':observation['source_identity'],
            'raw_row_index':observation['raw_row_index']})
    decisions = price_jobs.new_listings(instruments,symbols,by_name)
    additions = []
    for addition in decisions['additions']:
        symbol, name = addition['format']['symbol'], addition['format']['name']
        identity = [config['provider_namespace'], symbol, name]
        key = hashlib.sha256(b'\0'.join(v.encode('utf-8') for v in identity)).hexdigest()
        additions.append({'symbol':symbol,'name':name,'format_id':'listing-format-'+key,
                          'company_id':by_name.get(name,'listing-company-'+key),
                          'create_company':name not in by_name,'evidence':evidence[(symbol,name)]})
    if len(additions)>25:
        raise worker.AcquisitionError('LISTING_BATCH_REQUIRES_REVIEW')
    return {'contract':CONTRACT,'mode':'OWNER_REVIEW_REQUIRED',
            'provider_namespace':config['provider_namespace'],'archive_sha256':digest,
            'source_execution':envelope['execution'],'captured_at':envelope['captures'][0]['received_at'],
            'recipe_sha256':app_feed.fingerprint(config['recipe']),
            'bindings_sha256':app_feed.fingerprint(bindings),'before_sha256':before_sha256,
            'additions':additions,'conflicts':decisions['conflicts'],
            'prediction_eligible':False,'portfolio_valuation_eligible':False}
