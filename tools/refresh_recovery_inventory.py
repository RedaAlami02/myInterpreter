#!/usr/bin/env python3
"""Refresh the existing field ledger from verified captures and recovery reports.

No network/backend writes. Original Appwrite field mappings remain the audited
baseline; refreshed source fields, date-only bars and client quality projections
are explicitly separate evidence.
"""
from datetime import datetime, timezone
import json

from restore_nonpersonal_data import read_capture
from stage_supabase import ROOT


def run():
    root = ROOT/'backup_live_nonpersonal_20261024'
    path = root/'completeness_inventory.json'
    inventory = json.loads(path.read_text())
    if inventory['scope'] != 'every_recoverable_nonpersonal_dataset_and_field':
        raise ValueError('Unexpected original ledger scope')
    _, profiles, _, _ = read_capture(root)
    values = [row['profile'] for row in profiles]
    inventory['company_profile_coverage'] = {
        **{key: sum(bool(row.get(key)) for row in values)
           for key in ('sector', 'description', 'shareholders')},
        'annual_charts': sum(any(row.get('charts', {}).values()) for row in values),
        'quarterly_tables': sum(bool(row.get('trim')) for row in values),
        'interim_tables': sum(bool(row.get('sem') or row.get('interim')) for row in values),
        'official_issuer_records': sum(bool(row.get('issuer_disclosures')) for row in values),
    }
    inventory['official_disclosures'] = [{
        'symbol': row['symbol'], 'characteristic_fields': sorted(row['issuer_disclosures']['characteristics']),
        'structured_table_labels': sorted(row['issuer_disclosures']['structured_tables']),
        'shareholder_dates': row['issuer_disclosures']['shareholder_dates'],
        'current_ownership_independently_verified': False,
    } for row in values if row.get('issuer_disclosures')]
    daily = json.loads((root/'daily_reference_restore.json').read_text())
    inventory['daily_price_reference'] = {key: daily[key] for key in (
        'rows', 'symbols', 'first_day', 'last_day', 'quality_issue_counts',
        'comparisons', 'missing_day_candidates', 'source_sha256')}
    dividends = json.loads((root/'dividend_quality.json').read_text())
    inventory['dividend_client_quality_projection'] = {
        key: dividends[key] for key in ('checked_rows', 'issues', 'by_year', 'raw_rows_changed')}
    inventory.pop('personal_data_imported', None)
    inventory['personal_data_included_in_public_restore'] = False
    private_path = root/'personal_staging_verification.json'
    if private_path.exists():
        private = json.loads(private_path.read_text())
        inventory['separate_private_restore'] = {
            'records': private['records'], 'original_owners': private['saved_owners'],
            'all_original_payloads_match': private['target']['all_original_payloads_match'],
            'application_roles_have_access': private['target']['application_roles_have_private_staging_access'],
            'new_logins_assigned': private['auth_accounts_created_or_assigned'],
            'application_portfolio_tables_modified': private['application_tables_modified'],
        }
    earlier_path = root/'earlier_database_archive/restoration_report.json'
    if earlier_path.exists():
        earlier = json.loads(earlier_path.read_text())
        inventory['earlier_public_backup_archive'] = {
            key: earlier[key] for key in ('archive_files', 'archive_bytes',
                'additional_original_market_ids_preserved', 'legacy_mapping_field_preserved',
                'canonical_market_tables_changed')}
    inventory['remaining_scope_limits'] = [
        'Latest Appwrite database/schema/bucket inventory remains inaccessible.',
        'Five upstream-unmatched symbols now have official general/shareholder disclosures; financial statement gaps remain.',
        'Post-October-21 history still needs verified catch-up; 364 independent price differences remain unresolved.',
        'Daily references are separately queryable with quality flags; 724 of 725 missing company-days have no positive trade activity evidence.',
        '45 mismatched dividend periods are preserved in raw data and withheld from client financial claims; correct periods/amounts still need source review.',
    ]
    inventory['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
    return {'inventory_updated': True, 'profile_coverage': inventory['company_profile_coverage'],
            'backend_writes': False, 'personal_data_imported_by_this_tool': False}


if __name__ == '__main__':
    try:
        print(json.dumps(run()), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__}), flush=True)
        raise SystemExit(1)
