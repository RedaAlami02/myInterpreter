#!/usr/bin/env python3
"""Preserve newly found public backup evidence in the protected cloud archive.

Mixed SQL/JSON originals stay local. Only explicit public sections are extracted;
account/password/trade/holding sections and ownership permissions are excluded.
No canonical prices, company rows, latest quotes or personal records are changed.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import re
import subprocess

from legacy_sql_reader import public_tables
from restore_nonpersonal_data import apply as apply_archive, artifact, reject_personal_or_secrets
from stage_supabase import ROOT, local_config, sha256


OUTPUT = ROOT/'backup_live_nonpersonal_20261024/earlier_database_archive'
SEARCH = ROOT/'backup_live_nonpersonal_20261024/earlier_database_search'
PUBLIC = ('company', 'data', 'format', 'latest_prices')


def public_sections(payload):
    selected = {}
    for table in PUBLIC:
        if table in payload:
            selected[table] = [{key: value for key, value in row.items() if key != '$permissions'}
                               for row in payload[table]]
    reject_personal_or_secrets(selected)
    return selected


def save(name, payload, files):
    reject_personal_or_secrets(payload)
    content = (json.dumps(payload, default=str, sort_keys=True,
                          ensure_ascii=False, indent=2)+'\n').encode()
    path = OUTPUT/name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Content hashes retain revisions; no mixed original gets uploaded.
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)
    entry = {'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    files.append(artifact(OUTPUT, entry, 'earlier_database_public_evidence'))


def prepare():
    OUTPUT.mkdir(exist_ok=True)
    comparison = json.loads((SEARCH/'legacy_sql_comparison.json').read_text())
    files = []
    sql_counts = []
    for source in comparison['sources']:
        if 'identical_to' in source:
            continue
        label = source['source']
        if label == 'stock.sql':
            content = (ROOT/'stock.sql').read_bytes()
        else:
            match = re.fullmatch(r'git:([a-f0-9]{10,40}):stock\.sql', label)
            if match is None:
                raise ValueError('Unsupported historical source')
            result = subprocess.run(['git', 'show', match[1]+':stock.sql'], cwd=ROOT, capture_output=True)
            if result.returncode:
                raise ValueError('Historical SQL source unavailable')
            content = result.stdout
        digest = hashlib.sha256(content).hexdigest()
        if digest != source['sha256'] or len(content) != source['bytes']:
            raise ValueError('Original SQL changed since investigation')
        tables = public_tables(content.decode('utf-8'))
        save('sql_'+digest+'.json', {'source': label, 'original_source_sha256': digest,
            'numeric_representation': 'exact_decimal_strings', 'personal_data_included': False,
            'tables': tables}, files)
        sql_counts.append({'source': label, 'rows': {name: len(rows) for name, rows in tables.items()}})
    # Select explicit public collections before serializing the mixed JSON.
    rename_path = ROOT/'backup_rename_MANAGER_20260806_161501.json'
    previous_rename = json.loads((SEARCH/'rename_public_tables.json').read_text())
    if sha256(rename_path) != previous_rename['source_evidence']['original_sha256']:
        raise ValueError('Original rename backup changed since investigation')
    rename = public_sections(json.loads(rename_path.read_text()))
    save('rename_public.json', {'original_source_sha256': sha256(rename_path),
         'ownership_permissions_omitted': True, 'personal_data_included': False,
         'tables': rename}, files)
    company_path = ROOT/'backup_company_20260806_223153.json'
    company = public_sections({'company': json.loads(company_path.read_text())})
    save('company_august_public.json', {'original_source_sha256': sha256(company_path),
         'personal_data_included': False, 'tables': company}, files)
    cleanup_path = ROOT/'backup_delete_rows.json'
    cleanup = public_sections(json.loads(cleanup_path.read_text()))
    save('cleanup_public.json', {'original_source_sha256': sha256(cleanup_path),
         'personal_data_included': False, 'classification': 'deliberate_cleanup_evidence_do_not_resurrect',
         'tables': cleanup}, files)
    recovery = ROOT/'backup_live_recovery_20261022'
    manifest = json.loads((recovery/'manifest.json').read_text())
    evidence = next(row for row in manifest['files'] if row['path'] == 'recovered_market.jsonl.gz')
    source = recovery/'recovered_market.jsonl.gz'
    if sha256(source) != evidence['sha256'] or source.stat().st_size != evidence['bytes']:
        raise ValueError('Original market recovery changed')
    with gzip.open(source, 'rt') as stream:
        current = {row['$id']: row for row in map(json.loads, stream)}
    # Establish old→new names through shared original IDs, never fuzzy matching.
    aliases = defaultdict(set)
    for row in rename['data']:
        if row['$id'] in current:
            aliases[row['c_name']].add(current[row['$id']]['c_name'])
    extra = []
    for row in rename['data']:
        if row['$id'] in current:
            continue
        targets = aliases.get(row['c_name'], set())
        if len(targets) != 1:
            raise ValueError('Historical name requires identity review')
        extra.append({'original_row': row, 'verified_current_name': next(iter(targets)),
                      'classification': 'saved_intraday_record_absent_from_selected_recovery',
                      'canonical_price_correction': False})
    save('additional_market_observations.json', {'original_source_sha256': sha256(rename_path),
         'personal_data_included': False, 'observations': extra,
         'canonical_market_tables_changed': False}, files)
    report = {'archive_files': len(files), 'archive_bytes': sum(file['source_bytes'] for file in files),
              'additional_original_market_ids_preserved': len(extra),
              'sql_public_snapshots': sql_counts, 'legacy_mapping_field_preserved': True,
              'personal_data_included': False, 'canonical_market_tables_changed': False,
              'latest_quotes_replaced': False, 'cleanup_markers_resurrected': False}
    return files, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        files, report = prepare()
        if args.apply:
            report['target'] = apply_archive(local_config(ROOT/'.supabase-migration.env'), files, {})
        report['mode'] = 'applied' if args.apply else 'local_validation'
        report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
        name = 'restoration_report.json' if args.apply else 'validation_report.json'
        (OUTPUT/name).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__}), flush=True)
        raise SystemExit(1)
