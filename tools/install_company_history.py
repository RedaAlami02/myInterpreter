#!/usr/bin/env python3
"""Validate the additive history RPC in a rollback-only transaction; --apply commits it."""
import argparse
import hashlib
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from stage_supabase import connection_options, local_config

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'migrations/supabase/20261118_company_daily_history.sql'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    sql_text = MIGRATION.read_text()
    result = {'applied': False, 'market_data_modified': False,
              'migration_sha256': hashlib.sha256(sql_text.encode()).hexdigest(),
              'as_of_utc': datetime.now(timezone.utc).isoformat()}
    with psycopg.connect(**connection_options(local_config(ROOT / '.supabase-migration.env'))) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        db.execute("SET LOCAL statement_timeout='15s'")
        db.execute("SET LOCAL lock_timeout='2s'")
        if db.execute("SELECT to_regprocedure('public.read_company_daily_history_v1(text)')").fetchone()[0]:
            raise ValueError('Function already exists; inspect before changing it')
        db.execute(sql_text)
        grants = db.execute("""SELECT
            has_function_privilege('anon','public.read_company_daily_history_v1(text)','EXECUTE'),
            has_function_privilege('authenticated','public.read_company_daily_history_v1(text)','EXECUTE'),
            p.prosecdef FROM pg_proc p WHERE p.oid='public.read_company_daily_history_v1(text)'::regprocedure""").fetchone()
        if grants != (False, True, False):
            raise ValueError('Unexpected history privileges')
        db.execute('SET LOCAL ROLE authenticated')
        db.execute("SELECT set_config('request.jwt.claims','{}',true)")
        db.execute('SAVEPOINT guest_probe')
        try:
            db.execute("SELECT public.read_company_daily_history_v1('ADDOHA')")
        except psycopg.errors.InsufficientPrivilege:
            db.execute('ROLLBACK TO SAVEPOINT guest_probe')
        else:
            raise ValueError('Missing identity was accepted')
        claims = {'role': 'authenticated', 'sub': '00000000-0000-0000-0000-000000000001'}
        db.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps(claims),))
        names = ['ADDOHA'] + [row[0] for row in db.execute(
            "SELECT name FROM public.company WHERE name<>'ADDOHA' ORDER BY name LIMIT 2"
        ).fetchall()]
        for name in names:
            # Only verify canonical identities actually present in this project.
            if not db.execute('SELECT 1 FROM public.company WHERE name=%s', (name,)).fetchone():
                continue
            expected = db.execute("""SELECT day::text,pa::text FROM (
                SELECT DISTINCT ON ((date AT TIME ZONE 'UTC')::date)
                    (date AT TIME ZONE 'UTC')::date AS day,pa
                FROM public.data WHERE c_name=%s
                ORDER BY (date AT TIME ZONE 'UTC')::date DESC,date DESC,id DESC
            ) rows ORDER BY day""", (name,)).fetchall()
            elapsed = []
            for _ in range(5):
                start = time.perf_counter()
                document = db.execute('SELECT public.read_company_daily_history_v1(%s)', (name,)).fetchone()[0]
                elapsed.append((time.perf_counter() - start) * 1000)
            if document['contract'] != 'company-daily-history/v1' or document['company'] != name:
                raise ValueError('Invalid history identity')
            if document['rows'] != [{'day': day, 'price': price} for day, price in expected]:
                raise ValueError('Daily observation equivalence failed')
            result[name] = {'rows': len(expected), 'equivalence': True,
                            'n': 5, 'median_rpc_roundtrip_ms': round(statistics.median(elapsed), 1)}
        db.execute('SAVEPOINT invalid_probe')
        try:
            db.execute('SELECT public.read_company_daily_history_v1(%s)', ('not-a-listed-company',))
        except psycopg.errors.InvalidParameterValue:
            db.execute('ROLLBACK TO SAVEPOINT invalid_probe')
        else:
            raise ValueError('Unknown identity accepted')
        result['auth_and_privileges_passed'] = True
        if args.apply:
            db.execute("NOTIFY pgrst, 'reload schema'")
            db.commit()
            result['applied'] = True
        else:
            db.rollback()
    folder = ROOT / 'docs/performance'
    folder.mkdir(exist_ok=True)
    suffix = 'applied' if args.apply else 'preview'
    (folder / f'company_history_install_{suffix}_20261118.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('History RPC installation failed: ' + type(error).__name__)
        raise SystemExit(1)
