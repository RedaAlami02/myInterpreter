from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
import contextlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app_feed
import app_publish
import market_collect
import price_publication
import enrichment_jobs
import worker
from test_app_publish import profile
from test_market_collect import config
from test_market_frame import body,CAPTURED
from fixture_price import companies


class Publisher:
    def __init__(self,failures=0): self.failures,self.candidates=failures,[]
    def publish(self,candidate,mapping,*,application_rows=None):
        self.candidates.append(candidate)
        if self.failures:
            self.failures-=1
            raise RuntimeError('private')
        return {'status':'PUBLISHED','sha256':app_feed.fingerprint(candidate),'captured_at':candidate['captured_at'],
                **({'application_rows_sha256':app_feed.fingerprint(application_rows)} if application_rows is not None else {})}


class PricePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=worker.SQLiteStore(self.root/'isolated.sqlite');self.addCleanup(self.store.db.close)
        self.config=config()
        self.profile=profile()
        self.queue=price_publication.Publications(self.config,self.profile,self.root/'pending')
        self.value=market_collect.envelope(self.config,json.dumps(body()).encode(),CAPTURED,
            CAPTURED.replace(minute=0,second=0,microsecond=0).isoformat(),execution='CURRENT_ACQUISITION')
        self.value['completed_at']=CAPTURED.isoformat()

    def test_archive_success_publication_failure_restart_retries_exact_candidate(self):
        publisher=Publisher(failures=1)
        digest,blob=self.queue.enqueue(self.value,now=CAPTURED+timedelta(seconds=1))
        with self.assertRaises(RuntimeError): self.queue.flush(self.store,publisher=publisher)
        self.assertTrue(self.store.complete(self.config['provider_namespace'],'quotes',self.value['slot']))
        self.assertFalse(self.queue.complete(self.value['slot']))
        restored=price_publication.Publications(self.config,self.profile,self.root/'pending')
        restored.flush(self.store,publisher=publisher)
        self.assertEqual(publisher.candidates[0],publisher.candidates[1])
        self.assertTrue(restored.complete(self.value['slot']))
        self.assertEqual(restored.pending.entries(),[])
        self.assertEqual(self.store.db.execute('SELECT raw FROM attempts WHERE digest=?',(digest,)).fetchone()[0],blob)

    def test_full_price_job_uses_only_its_own_context_and_retry_keeps_that_exact_snapshot(self):
        cfg=self.root/'config.json';cfg.write_text(json.dumps(self.config))
        selected={**self.profile,'application_fields_sha256':app_feed.fingerprint({})}
        pins=self.root/'profile.json';pins.write_text(json.dumps(selected))
        fields=self.root/'fields.json';fields.write_text('{}')
        original=companies()
        context={'contract':'private-price-company-context/v1','price_companies':original}
        publisher=Publisher(failures=1)
        publisher.read_context=unittest.mock.Mock(return_value=context)
        store=SimpleNamespace(save_blob=self.store.save_blob,complete=self.store.complete,admit=self.store.admit)
        args=['--config',str(cfg),'--publish-profile',str(pins),'--application-bindings',str(fields),
              '--publication-spool',str(self.root/'own-context')]
        with patch.object(worker,'open_store',return_value=store),patch.object(worker,'scheduled_slot',return_value=self.value['slot']), \
             patch.object(app_publish,'open_publisher',return_value=publisher),patch('projection_store.ProjectionPublisher') as other_provider, \
             patch.object(price_publication,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(seconds=1))), \
             patch.object(market_collect,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(seconds=1))):
            with patch.object(worker,'fetch',return_value=(json.dumps(body()).encode(),CAPTURED)) as fetched,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(market_collect.main(args),1)
                fetched.assert_called_once()
            publisher.read_context.side_effect=AssertionError('Retry must not fetch newer fundamentals')
            with patch.object(worker,'fetch') as fetched,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(market_collect.main(args),0)
                fetched.assert_not_called()
            publisher.read_context.assert_called_once_with(self.config,selected)
            other_provider.assert_not_called()
        self.assertEqual(publisher.candidates[0],publisher.candidates[1])
        self.assertEqual(len(publisher.candidates[0]['rows']),3)
        self.assertEqual(len(self.store.db.execute('SELECT digest FROM attempts').fetchall()),1)

    def test_price_context_rejection_stops_before_source_or_archive_write(self):
        cfg=self.root/'config.json';cfg.write_text(json.dumps(self.config))
        selected={**self.profile,'application_fields_sha256':app_feed.fingerprint({})}
        pins=self.root/'profile.json';pins.write_text(json.dumps(selected))
        fields=self.root/'fields.json';fields.write_text('{}')
        publisher=Publisher();publisher.read_context=unittest.mock.Mock(side_effect=worker.AcquisitionError('PRICE_CONTEXT_DISABLED'))
        store=SimpleNamespace(save_blob=self.store.save_blob,complete=self.store.complete,admit=self.store.admit)
        with patch.object(worker,'open_store',return_value=store),patch.object(worker,'scheduled_slot',return_value=self.value['slot']), \
             patch.object(app_publish,'open_publisher',return_value=publisher),patch.object(worker,'fetch') as fetched,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(market_collect.main(['--config',str(cfg),'--publish-profile',str(pins),
                '--application-bindings',str(fields),'--publication-spool',str(self.root/'denied')]),1)
        fetched.assert_not_called()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)

    def test_full_application_rows_and_original_company_inputs_survive_retry(self):
        full_profile={**self.profile,'application_fields_sha256':app_feed.fingerprint({})}
        queue=price_publication.Publications(self.config,full_profile,self.root/'full')
        queue.enqueue(self.value,now=CAPTURED,companies=companies(),field_bindings={})
        saved=worker.unpacked(queue.pending.entries()[0].name[:64],queue.pending.read(queue.pending.entries()[0]),max_batch=queue.pending.entry_limit)
        self.assertEqual(len(saved['prepared']['application_rows']['rows']),3)
        self.assertEqual(saved['companies'],companies())
        publisher=Publisher(failures=1)
        with self.assertRaises(RuntimeError): queue.flush(self.store,publisher=publisher)
        queue.flush(self.store,publisher=publisher)
        self.assertEqual(publisher.candidates[0],publisher.candidates[1])

    def test_older_quote_only_job_cannot_downgrade_a_full_row_profile(self):
        self.queue.enqueue(self.value,now=CAPTURED)
        path=self.queue.pending.entries()[0]
        job=worker.unpacked(path.name[:64],self.queue.pending.read(path),max_batch=price_publication.MAX_JOB)
        full_profile={**self.profile,'application_fields_sha256':app_feed.fingerprint({})}
        queue=price_publication.Publications(self.config,full_profile,self.root/'downgrade')
        job['profile_sha256']=app_feed.fingerprint(full_profile)
        key,blob=worker.packed(job,max_batch=price_publication.MAX_JOB);queue.pending.put(key,blob)
        with self.assertRaisesRegex(worker.AcquisitionError,'COMPLETE_APPLICATION_INPUTS_REQUIRED'):
            queue.flush(self.store,publisher=Publisher())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)
        self.assertEqual(len(queue.pending.entries()),1)

    def test_changed_profile_cannot_publish_pending_document(self):
        self.queue.enqueue(self.value,now=CAPTURED)
        changed={**self.profile,'display_fallbacks':True}
        other=price_publication.Publications(self.config,changed,self.root/'pending')
        with self.assertRaisesRegex(worker.AcquisitionError,'PUBLICATION_CONTEXT_CHANGED'):
            other.flush(self.store,publisher=Publisher())
        self.assertEqual(len(other.pending.entries()),1)

    def test_preparation_failure_preserves_raw_and_never_claims_publication(self):
        with patch.object(app_publish,'prepare',side_effect=RuntimeError('private')):
            self.queue.enqueue(self.value)
        with self.assertRaisesRegex(worker.AcquisitionError,'PRICE_PREPARATION_FAILED'):
            self.queue.flush(self.store,publisher=Publisher())
        self.assertEqual(len(self.queue.pending.entries()),1)
        self.assertFalse(self.queue.complete(self.value['slot']))

    def test_all_publication_archive_and_enrichment_spools_are_disjoint(self):
        from outbox import Outbox
        for collision in [self.queue.pending.directory,self.queue.accepted.directory,
                          self.queue.pending.directory/'child',self.queue.accepted.directory/'child']:
            store=SimpleNamespace(save_blob=self.store.save_blob,outbox=Outbox(collision))
            with self.assertRaisesRegex(worker.AcquisitionError,'WORKER_SPOOLS_MUST_BE_SEPARATE'):
                self.queue.available(store)
            store=SimpleNamespace(save_blob=self.store.save_blob,outbox=Outbox(self.root/'raw'))
            with self.assertRaisesRegex(worker.AcquisitionError,'WORKER_SPOOLS_MUST_BE_SEPARATE'):
                self.queue.available(store,other_spools=[collision])

    def test_interrupted_ack_keeps_commit_and_retries_without_new_candidate(self):
        publisher=Publisher()
        self.queue.enqueue(self.value,now=CAPTURED)
        with patch.object(self.queue.pending,'acknowledge',side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError): self.queue.flush(self.store,publisher=publisher)
        self.assertTrue(self.queue.complete(self.value['slot']))
        self.queue.flush(self.store,publisher=publisher)
        self.assertEqual(len(publisher.candidates),1)
        self.assertEqual(len(self.queue.accepted.entries()),1)
        self.assertEqual(self.queue.pending.entries(),[])

    def test_actual_collector_restart_retries_publication_before_enrichment(self):
        cfg=self.root/'config.json';cfg.write_text(json.dumps(self.config))
        pins=self.root/'profile.json';pins.write_text(json.dumps(self.profile))
        # Explicit synthetic transport facade; no remote or project credentials.
        store=SimpleNamespace(save_blob=self.store.save_blob,complete=self.store.complete,admit=self.store.admit)
        publisher=Publisher(failures=1)
        args=['--config',str(cfg),'--publish-profile',str(pins),'--publication-spool',str(self.root/'cycle'),
              '--enrichment-config','unused','--enrichment-index','unused','--enrichment-spool',str(self.root/'enrichment')]
        with patch.object(worker,'open_store',return_value=store), \
                patch.object(worker,'scheduled_slot',return_value=self.value['slot']), \
                patch.object(app_publish,'open_publisher',return_value=publisher), \
                patch.object(price_publication,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(seconds=1))), \
                patch.object(market_collect,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(seconds=1))), \
                patch.object(enrichment_jobs,'execute',return_value={'status':'COMPLETE'}) as enrich:
            with patch.object(worker,'fetch',return_value=(json.dumps(body()).encode(),CAPTURED)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(market_collect.main(args),1)
            enrich.assert_not_called()
            output=io.StringIO()
            with patch.object(worker,'fetch') as fetch, contextlib.redirect_stdout(output):
                self.assertEqual(market_collect.main(args),0)
            fetch.assert_not_called()
            enrich.assert_called_once()
            self.assertEqual(json.loads(output.getvalue())['status'],'ALREADY_COMPLETE')
        self.assertEqual(publisher.candidates[0],publisher.candidates[1])

    def test_completed_archive_without_publication_receipt_is_explicitly_unverified(self):
        cfg=self.root/'config.json';cfg.write_text(json.dumps(self.config))
        pins=self.root/'profile.json';pins.write_text(json.dumps(self.profile))
        store=SimpleNamespace(save_blob=self.store.save_blob,complete=lambda *args:True)
        output=io.StringIO()
        with patch.object(worker,'open_store',return_value=store), \
                patch.object(worker,'scheduled_slot',return_value=self.value['slot']), \
                patch.object(worker,'fetch') as fetch, contextlib.redirect_stdout(output):
            self.assertEqual(market_collect.main(['--config',str(cfg),'--publish-profile',str(pins),
                '--publication-spool',str(self.root/'unknown')]),2)
        fetch.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'],'PUBLICATION_UNVERIFIED')

    def test_recurring_expired_intent_is_preserved_without_blocking_future_jobs(self):
        import os
        from datetime import datetime,timezone
        digest,blob=self.queue.enqueue(self.value,now=CAPTURED+timedelta(seconds=1))
        pending=self.queue.pending.entries()[0];original=self.queue.pending.read(pending)
        publisher=Publisher()
        with patch.dict(os.environ,{'APP_SCHEDULE_CONTRACT':'recurring-casablanca/v1'}),patch.object(price_publication,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(days=1))):
            result=self.queue.flush(self.store,publisher=publisher)
        self.assertEqual(result['status'],'EXPIRED_OR_REJECTED_PRESERVED')
        self.assertEqual(publisher.candidates,[])
        self.assertEqual(self.queue.pending.entries(),[])
        saved=self.queue.quarantine.entries()
        self.assertEqual(len(saved),1)
        self.assertEqual(self.queue.quarantine.read(saved[0]),original)
        self.assertEqual(self.store.db.execute('SELECT raw FROM attempts WHERE digest=?',(digest,)).fetchone()[0],blob)

    def test_full_quarantine_blocks_before_send_and_keeps_pending_intent(self):
        import os,hashlib
        import runner_checkpoint as checkpoint
        from unittest.mock import Mock
        state=self.root/'state';state.mkdir(mode=0o700)
        queue=price_publication.Publications(self.config,self.profile,state/'quotes')
        queue.enqueue(self.value,now=CAPTURED+timedelta(seconds=1))
        for i in range(64):
            raw=str(i).encode();queue.quarantine.put(hashlib.sha256(raw).hexdigest(),raw)
        store=SimpleNamespace(outbox=checkpoint.queue(state,'archive'),save_blob=Mock())
        with patch.dict(os.environ,{'APP_SCHEDULE_CONTRACT':'recurring-casablanca/v1','APP_CHECKPOINT_ROOT':str(state)}),patch.object(price_publication,'datetime',SimpleNamespace(now=lambda zone:CAPTURED+timedelta(days=1))):
            with self.assertRaisesRegex(worker.AcquisitionError,'CHECKPOINT_ENTRY_HEADROOM'):
                queue.flush(store,publisher=Publisher())
        store.save_blob.assert_not_called()
        self.assertEqual(len(queue.pending.entries()),1)
        self.assertEqual(len(queue.quarantine.entries()),64)
