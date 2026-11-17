#!/usr/bin/env python3
"""Preserve both saved portfolios in isolated staging before new-login mapping.

Default: verify local sources and emit aggregate counts only. --apply imports all
four private collections atomically and fully reads them back. --verify performs
read-only verification. No Auth account or application table is changed, and
legacy owners, permissions, dates, quantities, cost snapshots and P&L stay intact.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json

import psycopg

from stage_supabase import (ROOT, PRIVATE_COLLECTIONS, connection_options, datasets,
                            import_dataset, local_config, records, verify)
from verify_supabase_staging import compare_payloads


MAX_BYTES = 350_000_000


def summarize(grouped):
    owners = defaultdict(lambda: {name: [] for name in PRIVATE_COLLECTIONS})
    numeric = {'achats': ('number', 'prix_achat'), 'ventes': ('number', 'prix_vente'),
               'portefeuille': ('quantity', 'total_cost'), 'benefits': ('value',)}
    for table, rows in grouped.items():
        for row in rows:
            owner = row.get('user_id')
            if not isinstance(owner, str) or not owner.strip():
                raise ValueError('Private row missing legacy owner')
            for field in numeric[table]:
                value = row.get(field)
                if (isinstance(value, bool) or not isinstance(value, (int, float, Decimal))
                        or not Decimal(str(value)).is_finite()
                        or (table != 'benefits' and value <= 0)):
                    raise ValueError('Invalid source portfolio number')
            if table in ('achats', 'ventes', 'benefits'):
                stamp = datetime.fromisoformat(row['date'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('Original portfolio timestamp requires timezone')
            owners[owner][table].append(row)
    report = []
    for index, owner in enumerate(sorted(owners), 1):
        tables = owners[owner]
        net = defaultdict(Decimal)
        holdings = {}
        for table, sign in (('achats', 1), ('ventes', -1)):
            for row in tables[table]:
                net[row['c_name']] += sign * Decimal(str(row['number']))
        for row in tables['portefeuille']:
            name = row['c_name']
            if name in holdings:
                raise ValueError('Duplicate saved owner holding')
            holdings[name] = Decimal(str(row['quantity']))
        pnl_days = [row['date'][:10] for row in tables['benefits']]
        if len(set(pnl_days)) != len(pnl_days):
            raise ValueError('Duplicate saved owner P&L day requires review')
        names = set(net) | set(holdings)
        report.append({'saved_owner': 'saved_owner_'+str(index),
            'rows': {table: len(rows) for table, rows in tables.items()},
            'holding_quantity_disagreements': sum(net.get(name, 0) != holdings.get(name, 0)
                                                  for name in names),
            'holdings_without_saved_trade_history': sum(name not in net for name in holdings),
            'raw_ownership_preserved': True, 'new_login_assigned': False})
    return {'saved_owners': len(owners), 'owners': report,
            'records': sum(len(rows) for rows in grouped.values()),
            'source': 'verified_September_19_backup',
            'private_staging_only': True, 'application_tables_modified': False,
            'auth_accounts_created_or_assigned': False,
            'financial_values_or_owner_ids_printed': False}


def prepare(recovery):
    selected = [dataset for dataset in datasets(recovery, None, include_private=True)
                if dataset.collection in PRIVATE_COLLECTIONS]
    if {dataset.collection for dataset in selected} != set(PRIVATE_COLLECTIONS):
        raise ValueError('Incomplete private source selection')
    counts = [verify(dataset) for dataset in selected]
    grouped = {dataset.collection: list(records(dataset)) for dataset in selected}
    return selected, counts, summarize(grouped)


def verify_isolation(connection):
    for role in ('anon', 'authenticated', 'service_role'):
        access = connection.execute("""SELECT
            has_schema_privilege(%s,'migration_stage','USAGE'),
            has_table_privilege(%s,'migration_stage.datasets','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
            has_table_privilege(%s,'migration_stage.documents','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')""",
            (role, role, role)).fetchone()
        if any(access):
            raise ValueError('Private staging must be inaccessible to application roles')
    security = connection.execute("""SELECT c.relname,c.relrowsecurity,
        (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='migration_stage' AND c.relkind='r'""").fetchall()
    if ({row[0] for row in security} != {'datasets', 'documents'}
            or any(not row[1] or row[2] != 0 for row in security)):
        raise ValueError('Unexpected private staging boundary')


def restore(config, selected, counts, apply=False):
    with psycopg.connect(**connection_options(config)) as connection:
        if not apply:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        if not connection.pgconn.ssl_in_use:
            raise ValueError('TLS required')
        connection.execute("SET LOCAL statement_timeout='60s'")
        if apply:
            connection.execute('SELECT pg_advisory_xact_lock(182736451,1)')
        verify_isolation(connection)
        before = connection.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        if apply and before > MAX_BYTES:
            raise ValueError('Database exceeds recovery target')
        result = []
        for index, (dataset, count) in enumerate(zip(selected, counts)):
            state = import_dataset(connection, dataset, count, MAX_BYTES) if apply else 'read_only_verification'
            metadata = connection.execute('SELECT source_sha256,source_bytes,row_count '
                'FROM migration_stage.datasets WHERE dataset_id=%s', (dataset.identifier,)).fetchone()
            if metadata != (dataset.expected_hash, dataset.expected_bytes, count):
                raise ValueError('Private source metadata differs')
            with connection.cursor(name='private_restore_'+str(index)) as cursor:
                cursor.itersize = 100
                cursor.execute('SELECT document_id,payload FROM migration_stage.documents WHERE dataset_id=%s',
                               (dataset.identifier,))
                if compare_payloads(dataset, cursor) != count:
                    raise ValueError('Private payload read-back incomplete')
            result.append({'collection': dataset.collection, 'records': count,
                           'status': state, 'all_original_payloads_match': True})
        # Verify the local sources again before committing any selected owner.
        for dataset in selected:
            verify(dataset)
        verify_isolation(connection)
        after = connection.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        if apply and after > MAX_BYTES:
            raise ValueError('Private restore exceeds recovery target')
    return {'collections': result, 'all_original_payloads_match': True,
            'application_roles_have_private_staging_access': False,
            'database_bytes_before': before, 'database_bytes_after': after}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        selected, counts, report = prepare(ROOT/'backup_live_recovery_20261022')
        report['mode'] = 'applied' if args.apply else 'read_only_verification' if args.verify else 'local_validation'
        if args.apply or args.verify:
            report['target'] = restore(local_config(ROOT/'.supabase-migration.env'), selected, counts, args.apply)
        report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
        name = 'personal_staging_verification.json' if args.verify else 'personal_staging_restore.json' if args.apply else 'personal_staging_preparation.json'
        (ROOT/'backup_live_nonpersonal_20261024'/name).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__}), flush=True)
        raise SystemExit(1)
