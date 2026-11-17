from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import enrichment_jobs as jobs
import fundamental_collect
import fundamental_feed
from outbox import Outbox
import worker
from test_fundamental_collect import config, fetcher, values, RECEIVED, PROVIDER


NOW = RECEIVED + timedelta(seconds=10)
ACQUIRE = fundamental_collect.acquire


class Publisher:
    def __init__(self, failures=0):
        self.failures, self.documents = failures, []

    def publish(self, document):
        self.documents.append(document)
        if self.failures:
            self.failures -= 1
            raise RuntimeError('private upstream detail')
        return {'status': 'PUBLISHED', 'sha256': hashlib.sha256(document.encode()).hexdigest()}


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = worker.SQLiteStore(self.root / 'isolated.sqlite')
        self.addCleanup(self.store.db.close)
        self.outbox = Outbox(self.root / 'pending')
        self.index = {'contract': 'private-fundamental-index/v1', 'provider_namespace': PROVIDER,
                      'symbols': {'AAA': 'Alpha', 'BBB': 'Beta'}}
        self.companies = {'Alpha': {}, 'Beta': {}}

    def value(self, symbol='AAA', failures=()):
        data = values()
        data['symlinks'] = [{'symbol': symbol, 'name': 'Alpha SA', 'type': 'Banks'}]
        fetch, _ = fetcher(data, failures=failures)
        return ACQUIRE(config(), symbol, fetcher=fetch,
            now=NOW, subject_scoped=True)

    def execute(self, publisher=None, **kwargs):
        def acquire(cfg, symbol, **options):
            self.assertTrue(options['subject_scoped'])
            return self.value(symbol)
        with patch.object(fundamental_collect, 'acquire', side_effect=acquire) as source:
            result = jobs.run(config(), self.index, self.companies, self.store,
                publisher or Publisher(), self.outbox, clock=lambda: NOW, **kwargs)
        return result, source

    def test_two_companies_same_hour_collect_and_publish_without_legacy_completion(self):
        result, source = self.execute()
        self.assertEqual(result['complete'], 2)
        self.assertEqual(source.call_count, 2)
        self.assertEqual(result['pending'], 0)
        self.assertFalse(self.store.complete(PROVIDER, 'fundamentals', RECEIVED.replace(minute=0).isoformat()))
        again, source = self.execute()
        self.assertEqual(again['skipped'], 2)
        source.assert_not_called()

    def test_failed_projection_survives_restart_and_reuses_exact_document_and_archive(self):
        self.companies = {'Alpha': {}}
        publisher = Publisher(failures=1)
        result, _ = self.execute(publisher)
        self.assertEqual(result['pending'], 1)
        first = publisher.documents[0]
        before = self.store.db.execute('SELECT digest,raw FROM attempts').fetchall()
        result, source = self.execute(publisher)
        self.assertEqual(result['resumed'], 1)
        self.assertEqual(result['complete'], 1)
        source.assert_not_called()
        self.assertEqual(publisher.documents, [first, first])
        self.assertEqual(self.store.db.execute('SELECT digest,raw FROM attempts').fetchall(), before)

    def test_failed_archive_prevents_publication_and_retry_uses_saved_response(self):
        self.companies = {'Alpha': {}}
        publisher = Publisher()
        with patch.object(self.store, 'save_blob', side_effect=RuntimeError('private')):
            result, _ = self.execute(publisher)
        self.assertEqual(result['pending'], 1)
        self.assertEqual(publisher.documents, [])
        result, source = self.execute(publisher)
        self.assertEqual(result['complete'], 1)
        source.assert_not_called()

    def test_incomplete_raw_evidence_is_archived_without_company_merge(self):
        self.companies = {'Alpha': {}}
        publisher = Publisher()
        with patch.object(fundamental_collect, 'acquire', return_value=self.value(failures={'fp'})):
            result = jobs.run(config(), self.index, self.companies, self.store,
                publisher, self.outbox, clock=lambda: NOW)
        self.assertEqual(result['incomplete'], 1)
        self.assertEqual(result['pending'], 0)
        self.assertEqual(publisher.documents, [])
        self.assertEqual(self.store.db.execute('SELECT complete FROM attempts').fetchone()[0], 0)

    def test_budget_retains_original_plan_and_reports_deferred_work(self):
        result, source = self.execute(max_jobs=1)
        self.assertEqual(result['planned'], 2)
        self.assertEqual(result['attempted'], 1)
        self.assertEqual(result['deferred'], 1)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(source.call_count, 1)

    def test_explicit_target_refreshes_only_requested_company_outside_planner_window(self):
        later = NOW.replace(minute=45)
        with patch.object(jobs.price_jobs, 'enrichment_jobs') as planner:
            with patch.object(fundamental_collect, 'acquire', return_value=self.value()) as source:
                result = jobs.run(config(), self.index, self.companies, self.store,
                    Publisher(), self.outbox, clock=lambda: later, max_jobs=1, target_symbol='AAA')
        planner.assert_not_called()
        self.assertEqual(result['complete'], 1)
        self.assertEqual(result['planned'], 1)
        self.assertEqual(source.call_args.args[1], 'AAA')

    def test_explicit_target_rejects_ambiguous_company_before_source_request(self):
        self.index['symbols']['CCC'] = 'Alpha'
        with patch.object(fundamental_collect, 'acquire') as source:
            with self.assertRaisesRegex(worker.AcquisitionError, 'INVALID_REQUESTED_ENRICHMENT_TARGET'):
                jobs.run(config(), self.index, self.companies, self.store,
                    Publisher(), self.outbox, max_jobs=1, target_symbol='AAA')
        source.assert_not_called()

    def test_explicit_target_preserves_unrelated_pending_job_without_delivery_or_refetch(self):
        self.companies = {'Alpha': {}}
        self.execute(Publisher(failures=1))
        before = {p.name: self.outbox.read(p) for p in self.outbox.entries()}
        with patch.object(jobs, 'deliver') as delivery, patch.object(fundamental_collect, 'acquire') as source:
            result = jobs.run(config(), self.index, {'Alpha': {}, 'Beta': {}}, self.store,
                Publisher(), self.outbox, clock=lambda: NOW, max_jobs=1, target_symbol='BBB')
        delivery.assert_not_called()
        source.assert_not_called()
        self.assertEqual(result['pending'], 1)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual({p.name: self.outbox.read(p) for p in self.outbox.entries()}, before)

    def test_pending_context_change_blocks_refetch_and_keeps_evidence(self):
        self.execute(Publisher(failures=2))
        before = {p.name: self.outbox.read(p) for p in self.outbox.entries()}
        self.index['symbols']['AAA'] = 'Renamed'
        result, source = self.execute()
        source.assert_not_called()
        self.assertGreater(result['failed'], 0)
        self.assertEqual({p.name: self.outbox.read(p) for p in self.outbox.entries()}, before)

    def test_preparation_failure_keeps_raw_evidence_for_review(self):
        self.companies = {'Alpha': {}}
        with patch.object(fundamental_feed, 'build', side_effect=ValueError('private')):
            result, _ = self.execute()
        self.assertEqual(result['pending'], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)
        result, source = self.execute()
        self.assertEqual(result['pending'], 1)
        source.assert_not_called()

    def test_tampered_prepared_projection_is_refused_before_archive_write(self):
        job = jobs.prepare(self.value(), config(), self.index, NOW)
        doc = json.loads(job['document'])
        doc['fields']['bpa'] = 999
        job['document'] = fundamental_feed.canonical(doc)
        with self.assertRaisesRegex(worker.AcquisitionError, 'INVALID_ENRICHMENT_JOB'):
            jobs.deliver(job, config(), self.index, self.store, Publisher())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_overlapping_runner_cannot_collect_or_publish(self):
        with jobs.run_lock(self.outbox):
            with self.assertRaisesRegex(worker.AcquisitionError, 'ENRICHMENT_ALREADY_RUNNING'):
                self.execute()

    def test_legacy_archive_never_satisfies_company_scoped_completion(self):
        value = self.value()
        value.pop('subject_key')
        value['contract'] = 'private-acquisition/v2'
        self.store.save(value)
        result, source = self.execute()
        self.assertEqual(result['complete'], 2)
        self.assertEqual(source.call_count, 2)

    def test_legacy_only_store_rejected_before_fetch(self):
        with patch.object(fundamental_collect, 'acquire') as fetch:
            with self.assertRaisesRegex(worker.AcquisitionError, 'INVALID_ENRICHMENT_EXECUTOR'):
                jobs.run(config(), self.index, self.companies, object(), Publisher(), self.outbox)
        fetch.assert_not_called()

    def test_cli_failure_never_prints_exception_details(self):
        with patch('builtins.print') as printed:
            self.assertEqual(jobs.main(['--config', '/absent/private.json', '--index', '/absent',
                '--context', '/absent', '--spool', str(self.root / 'pending')]), 1)
        self.assertEqual(json.loads(printed.call_args.args[0]),
                         {'status': 'FAILED', 'code': 'ENRICHMENT_EXECUTION_FAILED'})

    def test_denied_positive_admission_prevents_any_source_request(self):
        with patch.object(self.store, 'admit_subject', return_value=False):
            result, source = self.execute()
        source.assert_not_called()
        self.assertEqual(result['failed'], 2)
        self.assertEqual(result['pending'], 0)

    def test_insufficient_pending_capacity_prevents_capture(self):
        self.outbox.limit = 10
        result, source = self.execute()
        source.assert_not_called()
        self.assertEqual(result['failed'], 2)

    def test_archive_and_job_spools_cannot_overlap(self):
        self.store.outbox = self.outbox
        with self.assertRaisesRegex(worker.AcquisitionError, 'ENRICHMENT_SPOOLS_MUST_BE_SEPARATE'):
            self.execute()

    def test_isolated_publisher_writes_only_local_sqlite(self):
        publisher = jobs.IsolatedPublisher(self.store)
        with patch('requests.post', side_effect=AssertionError('Network forbidden')):
            result, _ = self.execute(publisher)
        self.assertEqual(result['complete'], 2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM enrichment_projections').fetchone()[0], 2)

    def test_isolated_storage_refuses_remote_publisher_before_fetch(self):
        publisher = jobs.ProjectionPublisher('https://' + 'a'*20 + '.supabase.co/functions/v1/private-projection-publisher',
            'proj_publish_' + 'a'*64, 'a'*20)
        with patch.object(fundamental_collect, 'acquire') as source:
            with self.assertRaisesRegex(worker.AcquisitionError, 'ISOLATED_PUBLISHER_REQUIRED'):
                jobs.run(config(), self.index, self.companies, self.store, publisher, self.outbox)
        source.assert_not_called()

    def test_maximum_archive_wrapper_fits_separate_explicit_queue_bound(self):
        job = {'archive_hex': os.urandom(worker.MAX_BATCH).hex(), 'document': 'x' * (2 * 1024 * 1024)}
        digest, blob = worker.packed(job, max_batch=jobs.MAX_JOB)
        self.assertGreater(len(blob), worker.MAX_BATCH)
        spool = Outbox(self.root / 'large', entry_limit=jobs.MAX_JOB)
        spool.put(digest, blob)
        restored = worker.unpacked(digest, spool.read(spool.entries()[0]), max_batch=jobs.MAX_JOB)
        self.assertEqual(restored, job)
        with self.assertRaises(worker.AcquisitionError):
            Outbox(self.root / 'ordinary').put(digest, blob)
