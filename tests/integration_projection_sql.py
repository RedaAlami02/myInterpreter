#!/usr/bin/env python3
"""Python -> Deno -> injected loopback REST adapter -> real isolated SQL013.

Not hosted PostgREST/Storage acceptance. All payloads are synthetic. Requires an
explicit /tmp PostgreSQL socket and a fresh database; never uses project credentials.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading

import psycopg
from psycopg.conninfo import conninfo_to_dict
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
sys.path.insert(0, str(ROOT / 'tests'))
import projection_store
import worker
from test_projection_sql import (ProjectionSQLTests, PROVIDER, dividend_document,
                                 fundamental_document, fundamental_fields)


def run():
    options = conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
    if not options.get('host', '').startswith('/tmp/'):
        raise RuntimeError('Only an isolated /tmp socket is permitted')
    ProjectionSQLTests.setUpClass()
    database = ProjectionSQLTests.db
    archives, receipts = {}, []
    now = datetime.now(timezone.utc)
    docs = {}
    for kind in ('dividends', 'fundamentals'):
        raw = json.dumps({'fixture': kind}).encode()
        raw_sha = hashlib.sha256(raw).hexdigest()
        captured = now.isoformat()
        capture_id = hashlib.sha256(json.dumps([PROVIDER, raw_sha, captured], separators=(',', ':')).encode()).hexdigest()
        envelope = {'contract': 'private-acquisition/v2', 'provider_namespace': PROVIDER,
                    'kind': kind, 'execution': 'CURRENT_ACQUISITION', 'authority': 'UNPROMOTED',
                    'prediction_eligible': False, 'completeness': 'COMPLETE',
                    'symbol': 'AAA' if kind == 'fundamentals' else None,
                    'slot': now.replace(minute=0, second=0, microsecond=0).isoformat(),
                    'completed_at': captured,
                    'captures': [{'capture_id': capture_id, 'sha256': raw_sha,
                                  'received_at': captured, 'raw_hex': raw.hex()}]}
        digest, blob = worker.packed(envelope)
        archives[digest] = blob
        database.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at)"
                         " VALUES(%s,%s,%s,%s,%s,'COMPLETE',%s,%s,'STORED',now())",
                         (digest, PROVIDER, kind, now.replace(minute=0, second=0, microsecond=0), now,
                          len(blob), 'sha256/' + digest[:2] + '/' + digest + '.json.gz'))
        docs[kind] = (dividend_document(archive_sha256=digest) if kind == 'dividends' else
                      fundamental_document(fundamental_fields(fiscal_year=2024, bpa=99.5), archive_sha256=digest))
    database.commit()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, value, content_type='application/json'):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            digest = self.path.rsplit('/', 1)[-1].removesuffix('.json.gz')
            blob = archives.get(digest)
            self.reply(200, blob, 'application/octet-stream') if blob else self.reply(404, {'code': 'NoSuchKey'})

        def do_POST(self):
            name = self.path.removeprefix('/rest/v1/rpc/')
            if name not in ('publish_dividend_projection', 'publish_fundamental_projection'):
                self.reply(404, {'code': 'UNKNOWN_FIXTURE_RPC'})
                return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4 * 1024 * 1024:
                self.reply(413, {'code': 'BODY_LIMIT'})
                return
            try:
                value = json.loads(self.rfile.read(size))
                with psycopg.connect(**options) as db:
                    db.execute('SET LOCAL ROLE service_role')
                    receipt = db.execute('SELECT public.' + name + '(%s,%s)',
                                         (value['p_document'], value['p_payload_sha256'])).fetchone()[0]
                receipts.append(receipt)
                self.reply(200, receipt)
            except Exception:
                self.reply(400, {'code': 'FIXTURE_SQL_REJECTED'})

    bridge = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    thread.start()
    server = None
    try:
        server = subprocess.Popen(['deno', 'run', '--no-config', '--no-remote', '--no-npm',
                                   '--allow-net=127.0.0.1', str(ROOT / 'tests/projection_sql_fixture.ts'),
                                   str(bridge.server_port)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if not select.select([server.stdout], [], [], 15)[0]:
            raise RuntimeError('LOCAL_FIXTURE_NOT_READY')
        port = json.loads(server.stdout.readline())['port']

        class Transport:
            def post(self, _validated_url, **kwargs):
                return requests.post('http://127.0.0.1:' + str(port), **kwargs)

        publisher = projection_store.ProjectionPublisher(
            'https://' + 'a' * 20 + '.supabase.co/functions/v1/private-projection-publisher',
            'proj_publish_' + 'a' * 64, 'a' * 20, session=Transport())
        for kind, document in docs.items():
            text = json.dumps(document, separators=(',', ':'))
            first, retry = publisher.publish(text), publisher.publish(text)
            assert first == retry and first['status'] == 'PUBLISHED' and first['kind'] == kind
            assert receipts[-1]['status'] == ('UPDATED' if kind == 'fundamentals' else 'PUBLISHED')
        assert float(database.execute("SELECT bpa FROM public.company WHERE name='Alpha'").fetchone()[0]) == 99.5
        assert float(database.execute('SELECT amount FROM public.dividends').fetchone()[0]) == 175.0
        rejected = 0
        for doc in [fundamental_document(c_name='Unknown', archive_sha256=docs['fundamentals']['archive_sha256']),
                    {**docs['fundamentals'], 'fields': {**docs['fundamentals']['fields'], 'bpa': 90}}]:
            try:
                publisher.publish(json.dumps(doc))
                raise AssertionError('Invalid publication acknowledged')
            except worker.AcquisitionError:
                rejected += 1
        database.rollback()
        assert float(database.execute("SELECT bpa FROM public.company WHERE name='Alpha'").fetchone()[0]) == 99.5
        return {'ok': True, 'scope': 'SYNTHETIC_LOOPBACK_ADAPTER_REAL_LOCAL_SQL',
                'both_kinds_acknowledged': True, 'exact_retries_acknowledged': True,
                'actual_fundamental_sql_status': 'UPDATED', 'missing_and_conflict_rejections': rejected,
                'live_services_accessed': False, 'genuine_data_or_ledgers_used': False}
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            if server.stdout:
                server.stdout.close()
        bridge.shutdown()
        bridge.server_close()
        thread.join(timeout=5)
        ProjectionSQLTests.tearDownClass()


if __name__ == '__main__':
    try:
        result = run()
    except Exception as error:
        result = {'ok': False, 'error_category': type(error).__name__, 'live_services_accessed': False}
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)
