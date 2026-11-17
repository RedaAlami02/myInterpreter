#!/usr/bin/env python3
"""Restore every verified daily reference row with explicit source/quality flags.

Date-only source bars stay separate from original Appwrite ticks. Original OHLC
values, including inconsistent ranges, are retained and flagged rather than fixed
by guessing adjustments or inventing a trade timestamp. Default: local validation.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from audit_supabase_recovery import compare_rows
from migrate_supabase_market import prepare as prepare_baseline
from stage_supabase import ROOT, connection_options, local_config, sha256


TABLE = 'daily_price_reference'
FIELDS = ('id', 'c_name', 'symbol', 'period_day', 'close', 'bar', 'quality', 'source_sha256')
MARKER = 'myInterpreter daily reference v1'
MAX_BYTES = 350_000_000
NUMERIC_FIELDS = ('open', 'high', 'low', 'close', 'quantity_traded', 'volume_mad',
                  'transactions', 'status')


def build_rows(reference, formats, observations, source_hash):
    names = {row['symbol']: row['name'] for row in formats}
    if len(names) != len(formats) or len(set(names.values())) != len(formats):
        raise ValueError('Ambiguous company/symbol mapping')
    symbols = {name: symbol for symbol, name in names.items()}
    latest = {}
    for row in observations:
        symbol = symbols.get(row['c_name'])
        if symbol is None:
            continue
        key = (symbol, row['date'].date())
        previous = latest.get(key)
        if previous is None or (row['date'], row['id']) > (previous['date'], previous['id']):
            latest[key] = row
    seen = set()
    rows = []
    issues = Counter()
    comparisons = Counter()
    gaps = Counter()
    for original in reference:
        symbol = original['symbol']
        moment = original['date']
        if (not isinstance(moment, datetime) or moment.time().isoformat() != '00:00:00'
                or symbol not in names):
            raise ValueError('Unexpected daily period or unknown symbol')
        day = moment.date()
        if (symbol, day) in seen:
            raise ValueError('Duplicate daily identity')
        seen.add((symbol, day))
        bar = {key: original[key] for key in NUMERIC_FIELDS}
        for value in bar.values():
            if value is not None and (isinstance(value, bool)
                    or not isinstance(value, (int, float, Decimal))
                    or not Decimal(str(value)).is_finite()):
                raise ValueError('Invalid numeric daily reference')
        close = Decimal(str(bar['close']))
        if close <= 0:
            raise ValueError('Daily close must be positive')
        flags = []
        if any(bar[key] is None for key in ('open', 'high', 'low')):
            flags.append('incomplete_ohlc')
        elif (bar['low'] > bar['high'] or any(
                not bar['low'] <= bar[key] <= bar['high'] for key in ('open', 'close'))):
            flags.append('inconsistent_ohlc_range')
        if any(bar[key] is not None and bar[key] < 0
               for key in ('quantity_traded', 'volume_mad', 'transactions')):
            flags.append('negative_activity')
        if any(bar[key] is not None and bar[key] != int(bar[key])
               for key in ('quantity_traded', 'transactions')):
            flags.append('fractional_activity_count')
        if bar['volume_mad'] == 0:
            flags.append('zero_reported_volume')
        previous = latest.get((symbol, day))
        comparison = ('no_recovered_company_day' if previous is None
                      else 'matches_latest_recovered_price' if previous['pa'] == close
                      else 'different_from_latest_recovered_price')
        quality = {'issues': flags, 'comparison': comparison,
                   'observation_kind': 'daily_reference',
                   'price_adjustment_basis': 'unknown',
                   'independently_verified_close': False,
                   'has_trade_activity_evidence': any(
                       bar[k] is not None and bar[k] > 0
                       for k in ('quantity_traded', 'volume_mad', 'transactions')),
                   'usable_ohlc_range': not any(flag in flags for flag in (
                       'inconsistent_ohlc_range', 'incomplete_ohlc', 'negative_activity'))}
        if previous is not None:
            quality['recovered_id'] = previous['id']
            quality['recovered_timestamp_utc'] = previous['date'].isoformat()
            quality['recovered_price'] = str(previous['pa'])
        else:
            gaps['rows'] += 1
            gaps['with_trade_activity_evidence'] += quality['has_trade_activity_evidence']
            gaps['with_usable_ohlc_range'] += quality['usable_ohlc_range']
        issues.update(flags)
        comparisons[comparison] += 1
        identity = hashlib.sha256((source_hash+'\0'+symbol+'\0'+day.isoformat()).encode()).hexdigest()
        rows.append(dict(zip(FIELDS, (identity, names[symbol], symbol, day, close,
                                      bar, quality, source_hash))))
    report = {'rows': len(rows), 'symbols': len({row['symbol'] for row in rows}),
              'first_day': min(row['period_day'] for row in rows).isoformat(),
              'last_day': max(row['period_day'] for row in rows).isoformat(),
              'quality_issue_counts': dict(issues), 'comparisons': dict(comparisons),
              'missing_day_candidates': dict(gaps), 'original_values_preserved': True,
              'original_application_tables_modified': False, 'personal_data_included': False,
              'trade_timestamps_invented': False}
    return rows, report


def prepare(recovery):
    reference = recovery/'independent_daily_history.parquet'
    manifest = json.loads((recovery/'manifest.json').read_text())
    evidence = next(row for row in manifest['files'] if row['path'] == reference.name)
    digest = sha256(reference)
    if evidence['bytes'] != reference.stat().st_size or evidence['sha256'] != digest:
        raise ValueError('Daily reference artifact differs from verified manifest')
    _, _, baseline, _ = prepare_baseline(recovery)
    import pyarrow.parquet as parquet
    original = parquet.read_table(reference).to_pylist()
    rows, report = build_rows(original, baseline['format'], baseline['data'], digest)
    report['source_sha256'] = digest
    return rows, report


def saved_rows(connection):
    with connection.cursor(name='daily_reference_verify') as cursor:
        cursor.itersize = 1000
        cursor.execute(sql.SQL('SELECT {} FROM public.daily_price_reference').format(
            sql.SQL(',').join(map(sql.Identifier, FIELDS))))
        for row in cursor:
            yield dict(zip(FIELDS, row))


def apply(config, rows):
    with psycopg.connect(**connection_options(config)) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ValueError('TLS required')
        connection.execute("SET LOCAL statement_timeout='300s'")
        connection.execute("SET LOCAL lock_timeout='10s'")
        connection.execute('SELECT pg_advisory_xact_lock(182736451,4)')
        before = connection.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        if before > MAX_BYTES:
            raise ValueError('Database exceeds recovery target')
        existing = connection.execute("SELECT to_regclass(%s),obj_description(to_regclass(%s),'pg_class')",
                                      ('public.'+TABLE, 'public.'+TABLE)).fetchone()
        if existing[0] is not None and existing[1] != MARKER:
            raise ValueError('Refusing unrelated daily-reference table')
        connection.execute((ROOT/'migrations/supabase/005_daily_reference.sql').read_text(), prepare=False)
        count = connection.execute('SELECT count(*) FROM public.daily_price_reference').fetchone()[0]
        if count == 0:
            with connection.cursor() as cursor:
                with cursor.copy(sql.SQL('COPY public.daily_price_reference ({}) FROM STDIN').format(
                        sql.SQL(',').join(map(sql.Identifier, FIELDS)))) as copy:
                    for row in rows:
                        copy.write_row([Jsonb(row[key]) if key in ('bar', 'quality') else row[key]
                                        for key in FIELDS])
        comparison = compare_rows(rows, saved_rows(connection))
        if not comparison['all_typed_values_match']:
            raise ValueError('Daily reference read-back differs from source')
        for role in ('anon', 'authenticated', 'service_role'):
            permissions = connection.execute("SELECT has_table_privilege(%s,%s,'SELECT'),"
                "has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
                (role, 'public.'+TABLE, role, 'public.'+TABLE)).fetchone()
            if permissions != (True, False):
                raise ValueError('Unexpected daily reference permissions')
        security = connection.execute("SELECT relrowsecurity,(SELECT count(*) FROM pg_policy WHERE polrelid=c.oid) "
                                      "FROM pg_class c WHERE c.oid='public.daily_price_reference'::regclass").fetchone()
        if security != (True, 1):
            raise ValueError('Unexpected daily reference row policies')
        after = connection.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        if after > MAX_BYTES:
            raise ValueError('Daily restoration exceeds recovery target')
        connection.execute("NOTIFY pgrst,'reload schema'")
    return {'rows_added': len(rows) if count == 0 else 0, 'all_typed_values_match': True,
            'read_only_public_access_verified': True, 'database_bytes_before': before,
            'database_bytes_after': after}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        rows, report = prepare(ROOT/'backup_live_recovery_20261022')
        if args.apply:
            report['target'] = apply(local_config(ROOT/'.supabase-migration.env'), rows)
        report['mode'] = 'applied' if args.apply else 'local_validation'
        report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
        name = 'daily_reference_restore.json' if args.apply else 'daily_reference_validation.json'
        (ROOT/'backup_live_nonpersonal_20261024'/name).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__}), flush=True)
        raise SystemExit(1)
