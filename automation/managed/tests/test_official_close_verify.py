from datetime import datetime,timezone,timedelta
import copy,hashlib,json,shutil,unittest
import official_close_collect as collect
import official_close_verify as reviewer
import worker
from fixture_official import config,pdf


@unittest.skipUnless(shutil.which('pdftotext'),'Official PDF text dependency required')
class IndependentOfficialReviewTests(unittest.TestCase):
    def setUp(self):
        self.config=config();self.raw=pdf();self.now=datetime(2026,11,3,18,5,tzinfo=timezone.utc)
        self.job=collect.build(self.config,self.raw,self.now-timedelta(minutes=1),self.now.replace(minute=0).isoformat(),200)

    def fetch(self,*args):return self.raw,self.now,200

    def test_independent_fresh_pdf_produces_bound_attestation(self):
        body=reviewer.attested_body(self.config,self.job,'c'*64,'d'*40,fetcher=self.fetch,clock=lambda:self.now)
        proof=json.loads(body['attestation_document'])
        self.assertEqual(proof['document_sha256'],hashlib.sha256(self.job['document'].encode()).hexdigest())
        self.assertEqual(proof['raw_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(len(body['attestation_hmac']),64)
        self.assertNotIn('c'*64,json.dumps(body))

    def test_real_pdf_plus_forged_parsed_prices_cannot_get_attested(self):
        forged=copy.deepcopy(self.job);envelope=worker.unpacked(forged['archive_sha256'],bytes.fromhex(forged['archive_hex']))
        envelope['official_report']['rows'][0]['price_decimal']='999.00'
        digest,blob=worker.packed(envelope);forged['archive_sha256']=digest;forged['archive_hex']=blob.hex()
        doc=json.loads(forged['document']);doc['archive_sha256']=digest;doc['rows'][0]['price_decimal']='999.00';forged['document']=collect.canonical(doc)
        with self.assertRaisesRegex(worker.AcquisitionError,'PRICE_DIFFERS'):
            reviewer.attested_body(self.config,forged,'c'*64,'d'*40,fetcher=self.fetch,clock=lambda:self.now)

    def test_changed_source_pdf_or_identity_mapping_is_not_signed(self):
        with self.assertRaisesRegex(worker.AcquisitionError,'REPORT_CHANGED'):
            reviewer.verify(self.config,self.job,fetcher=lambda *args:(pdf(price='26,00'),self.now,200),clock=lambda:self.now)
        bad=copy.deepcopy(self.config);bad['identities'][0]['symbol']='WRONG'
        with self.assertRaisesRegex(worker.AcquisitionError,'POLICY_(PIN_)?DIFFERS'):
            reviewer.verify(bad,self.job,fetcher=self.fetch,clock=lambda:self.now)

class ReviewDeploymentTests(unittest.TestCase):
    def test_exact_trusted_release_is_required_before_financial_review(self):
        reviewer.require_review_commit({'status':'READY','worker_commit':'a'*40},'a'*40)
        for value in [None,{}, {'status':'READY','worker_commit':'b'*40},{'status':'DISABLED','worker_commit':'a'*40}]:
            with self.assertRaisesRegex(worker.AcquisitionError,'DEPLOYMENT_MISMATCH'):
                reviewer.require_review_commit(value,'a'*40)
