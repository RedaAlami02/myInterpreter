#!/usr/bin/env python3
"""Bounded, read-only hosting diagnosis. Never prints credentials or response bodies.

Uses the site's normal browser-verification cookie and SELECT-only SQL sessions.
SQL timing is diagnostic, not a substitute for an authenticated browser trace.
"""
import argparse
import json
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://myinterpreter.infinityfree.me'


def summary(samples):
    values = sorted(samples)
    return {'n': len(values), 'min_ms': round(min(values), 1),
            'median_ms': round(statistics.median(values), 1),
            'max_ms': round(max(values), 1)} if values else {'n': 0}


def request_site(session, path):
    start = time.perf_counter()
    response = session.get(SITE + path, timeout=35)
    challenge = 'slowAES.decrypt' in response.text
    if challenge:
        fields = re.findall(r'(?:var\s+)?([abc])=toNumbers\("([0-9a-f]+)"\)', response.text)
        values = dict(fields)
        if set(values) != {'a', 'b', 'c'}:
            raise ValueError('Unrecognized browser-verification format')
        decryptor = Cipher(algorithms.AES(bytes.fromhex(values['a'])), modes.CBC(bytes.fromhex(values['b']))).decryptor()
        cookie = (decryptor.update(bytes.fromhex(values['c'])) + decryptor.finalize()).hex()
        session.cookies.set('__test', cookie, domain='myinterpreter.infinityfree.me', path='/')
        response = session.get(SITE + path, timeout=35)
    elapsed = (time.perf_counter() - start) * 1000
    text = response.text
    return {'total_ms': elapsed, 'status': response.status_code, 'bytes': len(response.content),
            'challenge_encountered': challenge, 'challenge_remaining': 'slowAES.decrypt' in text,
            'company_rendered': 'company-header' in text and 'ADDOHA' in text,
            'signin_required': 'Please sign in' in text or 'Veuillez vous connecter' in text,
            'latest_price_panel': 'companyMarketTitle' in text}


def curl_metrics(url, headers=()):
    # Keep credentials out of process arguments and diagnostic output.
    config = ['url = ' + json.dumps(url), 'silent', 'output = "/dev/null"', 'max-time = 20']
    config += ['header = ' + json.dumps(h) for h in headers]
    fmt = {'status': '%{http_code}', 'dns_ms': '%{time_namelookup}', 'connect_ms': '%{time_connect}',
           'tls_ms': '%{time_appconnect}', 'ttfb_ms': '%{time_starttransfer}', 'total_ms': '%{time_total}'}
    result = subprocess.run(['curl', '--config', '-', '--write-out', json.dumps(fmt)],
                            input='\n'.join(config), capture_output=True, text=True, timeout=25)
    if result.returncode:
        return {'error': 'connection_failed'}
    value = json.loads(result.stdout)
    return {k: int(v) if k == 'status' else round(float(v)*1000, 1) for k, v in value.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=5, choices=range(1, 11))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'vantage': 'local execution machine; geography not independently verified',
              'site': {}, 'sql': {}, 'network': {}}
    session = requests.Session()
    for label, path in [('company', '/infoAction.php?name=ADDOHA'), ('static', '/assets/css/infoAction.css'), ('home', '/')]:
        values = []
        for _ in range(args.samples):
            try:
                values.append(request_site(session, path))
            except Exception as error:
                values.append({'error': type(error).__name__})
        report['site'][label] = {'samples': values, 'summary': summary([v['total_ms'] for v in values if 'total_ms' in v])}
        print(label, json.dumps(report['site'][label]['summary']), flush=True)
    report['network']['site_cold'] = [curl_metrics(SITE + '/assets/css/infoAction.css') for _ in range(3)]
    try:
        import psycopg
        from stage_supabase import connection_options, local_config
        config = local_config(ROOT / '.supabase-migration.env')
        options = connection_options(config)
        region = re.search(r'aws-\d+-([a-z]+-[a-z]+-\d+)', options['host'])
        report['database_region'] = region.group(1) if region else 'unverified'
        report['network']['database_rest_cold'] = [curl_metrics(config['SUPABASE_PROJECT_URL'] + '/rest/v1/company?select=id&limit=1',
             ['apikey: ' + config['SUPABASE_PUBLISHABLE_KEY']]) for _ in range(3)]
        start = time.perf_counter()
        with psycopg.connect(**options) as db:
            report['sql_connect_ms'] = round((time.perf_counter()-start)*1000, 1)
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL statement_timeout='15s'")
            db.execute('SET LOCAL ROLE authenticated')
            queries = {
                'roundtrip': ('SELECT 1', ()),
                'company_directory': ('SELECT * FROM public.company ORDER BY name,id DESC LIMIT 500', ()),
                'symbol_directory': ('SELECT * FROM public.format ORDER BY id DESC LIMIT 500', ()),
                'company_history_first_page': ('SELECT * FROM public.data WHERE c_name=%s ORDER BY date DESC,id DESC LIMIT 500', ('ADDOHA',)),
                'company_history_count': ('SELECT count(*) FROM public.data WHERE c_name=%s', ('ADDOHA',)),
                'company_latest_price': ('SELECT * FROM public.latest_prices WHERE c_name=%s ORDER BY date DESC,id DESC LIMIT 1', ('ADDOHA',)),
                'company_book': ('SELECT * FROM public.market_orderbooks WHERE symbol=%s ORDER BY captured_at DESC,id DESC LIMIT 1', ('ADH',)),
                'company_dividends': ('SELECT * FROM public.dividends WHERE c_name=%s ORDER BY year DESC,id DESC LIMIT 50', ('ADDOHA',)),
                'company_profile': ('SELECT * FROM public.company_profiles WHERE id=%s LIMIT 1', ('ADH',)),
            }
            for label, (query, params) in queries.items():
                values = []; count = None
                for _ in range(args.samples):
                    start = time.perf_counter(); rows = db.execute(query, params).fetchall()
                    values.append((time.perf_counter()-start)*1000)
                    count = rows[0][0] if label.endswith('_count') else len(rows)
                entry = {'roundtrip': summary(values), 'rows': count}
                plan = db.execute('EXPLAIN (ANALYZE, FORMAT JSON) '+query, params).fetchone()[0][0]
                entry['server_execution_ms'] = plan['Execution Time']
                entry['server_planning_ms'] = plan['Planning Time']
                report['sql'][label] = entry
                print(label, json.dumps(entry), flush=True)
    except Exception as error:
        report['database_error'] = type(error).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('Sanitized report saved.', flush=True)


if __name__ == '__main__':
    main()
