"""Concurrent SQL013 publication on fresh synthetic /tmp-only data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading
import unittest

import psycopg

import test_projection_sql as fixtures
from test_projection_sql import dividend_document, dividend_row


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'), 'Isolated database not configured')
class ProjectionConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProjectionSQLTests.setUpClass()
        cls.db = fixtures.ProjectionSQLTests.db
        cls.options = psycopg.conninfo.conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        cls.new_digest = '9' * 64
        cls.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at)"
                       " SELECT %s,provider,kind,slot+interval '30 minutes',completed_at+interval '30 minutes',completeness,compressed_bytes,"
                       " 'sha256/99/'||%s||'.json.gz',state,verified_at FROM app_archive.objects WHERE digest=%s",
                       (cls.new_digest, cls.new_digest, '1' * 64))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        fixtures.ProjectionSQLTests.tearDownClass()

    def setUp(self):
        self.db.execute('TRUNCATE public.dividends,app_projection.accepted_rows')
        self.db.commit()

    def parallel(self, first, second):
        first_written, second_started, release = threading.Event(), threading.Event(), threading.Event()
        def publish(document, is_first):
            with psycopg.connect(**self.options) as db:
                db.execute('SET LOCAL ROLE service_role')
                text = json.dumps(document)
                if not is_first:
                    second_started.set()
                try:
                    value = db.execute('SELECT public.publish_dividend_projection(%s,%s)',
                                       (text, hashlib.sha256(text.encode()).hexdigest())).fetchone()[0]
                    if is_first:
                        first_written.set()
                        if not release.wait(5):
                            raise RuntimeError('Test release timeout')
                    return value
                except psycopg.Error as error:
                    return {'sqlstate': error.sqlstate}
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(publish, first, True)
            try:
                self.assertTrue(first_written.wait(5))
                b = pool.submit(publish, second, False)
                self.assertTrue(second_started.wait(5))
            finally:
                release.set()
            return a.result(timeout=10), b.result(timeout=10)

    def test_concurrent_exact_retry_has_one_public_row_and_acceptance_head(self):
        first, second = self.parallel(dividend_document(), dividend_document())
        self.assertEqual(first['created'] + second['created'], 1)
        self.assertEqual(first['updated'] + second['updated'], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM public.dividends').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_projection.accepted_rows').fetchone()[0], 1)

    def test_older_publication_waiting_on_newer_cannot_regress_committed_values(self):
        newer = dividend_document([dividend_row(amount=180.0)], archive_sha256=self.new_digest)
        first, second = self.parallel(newer, dividend_document())
        self.assertEqual(first['status'], 'PUBLISHED')
        self.assertEqual(second['sqlstate'], '22023')
        self.assertEqual(float(self.db.execute('SELECT amount FROM public.dividends').fetchone()[0]), 180.0)
        self.assertEqual(self.db.execute('SELECT archive_digest FROM app_projection.accepted_rows').fetchone()[0], self.new_digest)


if __name__ == '__main__':
    unittest.main()
