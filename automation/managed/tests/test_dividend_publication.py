"""Raw archival, exact projection retry and durable completion without source IO."""
from datetime import timedelta
import hashlib,json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dividend_collect as jobs
import worker
from test_dividend_collect import config,RECEIVED


def index():
    return {'contract':'private-dividend-index/v1','provider_namespace':'feed_0123456789abcdef','index':{'ALPHA':'Alpha'}}


def page(cells):
    headers=['Émetteur','Montant (MAD)','Dividende %','Détachement','Paiement','Type','Fréquence']
    return '<table><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr><tr>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr></table>'


class Publisher:
    def __init__(self,failures=0):self.documents=[];self.failures=failures
    def publish(self,document):
        self.documents.append(document)
        if self.failures:self.failures-=1;raise RuntimeError('Synthetic interruption')
        return {'status':'PUBLISHED','kind':'dividends','records':len(json.loads(document)['rows']),
                'sha256':hashlib.sha256(document.encode()).hexdigest()}


class DividendPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cfg=config(jobs={'dividends':[{'year':2026,'url':'https://example.invalid/calendar'}]})
        self.store=worker.SQLiteStore(self.root/'isolated.sqlite');self.addCleanup(self.store.db.close)
        self.queue=jobs.DividendPublications(self.cfg,index(),self.root/'dividends')
        self.raw=page(['ALPHA','2.5','-','01/04/2026','15/04/2026','Ordinaire','Annuel']).encode()
        self.fetch=Mock(return_value=(self.raw,RECEIVED))
        self.now=RECEIVED+timedelta(seconds=1)

    def value(self):return jobs.acquire(self.cfg,fetcher=self.fetch,now=self.now)

    def test_success_stores_raw_and_projection_and_repeated_run_fetches_nothing(self):
        publisher=Publisher()
        result=jobs.publish_run(self.cfg,index(),self.store,publisher,self.root/'dividends',clock=lambda:self.now,fetcher=self.fetch)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(len(publisher.documents),1)
        self.assertEqual(len(json.loads(publisher.documents[0])['rows']),1)
        self.fetch.reset_mock()
        result=jobs.publish_run(self.cfg,index(),self.store,publisher,self.root/'dividends',clock=lambda:self.now,fetcher=self.fetch)
        self.assertEqual(result['status'],'ALREADY_COMPLETE');self.fetch.assert_not_called()

    def test_publication_failure_and_restart_retries_original_document_before_new_capture(self):
        publisher=Publisher(failures=1)
        self.queue.enqueue(self.value(),self.now)
        with self.assertRaises(RuntimeError):self.queue.flush(self.store,publisher)
        self.assertEqual(len(self.queue.pending.entries()),1)
        restored=jobs.DividendPublications(self.cfg,index(),self.root/'dividends')
        restored.flush(self.store,publisher)
        self.assertEqual(publisher.documents[0],publisher.documents[1]);self.assertEqual(restored.pending.entries(),[])

    def test_interrupted_ack_uses_durable_exact_receipt_without_republishing(self):
        publisher=Publisher();self.queue.enqueue(self.value(),self.now)
        with patch.object(self.queue.pending,'acknowledge',side_effect=RuntimeError('Interrupted')):
            with self.assertRaises(RuntimeError):self.queue.flush(self.store,publisher)
        self.queue.flush(self.store,publisher)
        self.assertEqual(len(publisher.documents),1);self.assertEqual(self.queue.pending.entries(),[])

    def test_preparation_failure_preserves_raw_and_does_not_publish(self):
        import dividend_feed
        with patch.object(dividend_feed,'build',side_effect=ValueError('Invalid source shape')):
            self.queue.enqueue(self.value(),self.now)
        publisher=Publisher()
        with self.assertRaisesRegex(worker.AcquisitionError,'PREPARATION_FAILED'):self.queue.flush(self.store,publisher)
        self.assertEqual(publisher.documents,[]);self.assertEqual(len(self.queue.pending.entries()),1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0],1)

    def test_complete_raw_without_a_publication_receipt_does_not_claim_success(self):
        self.store.save(self.value())
        self.fetch.reset_mock()
        with self.assertRaisesRegex(worker.AcquisitionError,'WITHOUT_PUBLICATION_RECEIPT'):
            jobs.publish_run(self.cfg,index(),self.store,Publisher(),self.root/'dividends',clock=lambda:self.now,fetcher=self.fetch)
        self.fetch.assert_not_called()

    def test_capacity_failure_stops_before_fetch_and_retains_original_state(self):
        with patch.object(worker,'require_checkpoint_acquisition_headroom',side_effect=worker.AcquisitionError('CHECKPOINT_BYTE_HEADROOM')):
            with self.assertRaisesRegex(worker.AcquisitionError,'BYTE_HEADROOM'):
                jobs.publish_run(self.cfg,index(),self.store,Publisher(),self.root/'dividends',clock=lambda:self.now,fetcher=self.fetch)
        self.fetch.assert_not_called();self.assertEqual(self.queue.pending.entries(),[])
