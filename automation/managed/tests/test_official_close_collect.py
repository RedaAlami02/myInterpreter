from datetime import datetime,timezone,timedelta
from pathlib import Path
import shutil,tempfile,unittest,hashlib,json
import official_close_collect as collect
import runner_checkpoint,worker
from fixture_official import config,pdf


class Store:
    def __init__(self):self.saved=[];self.reviewed=False
    def admit(self,*args,**kwargs):return True
    def save_blob(self,digest,blob):self.saved.append((digest,blob));return digest
    def official_complete(self,*args):return self.reviewed


@unittest.skipUnless(shutil.which('pdftotext'),'Official PDF text dependency required')
class OfficialCollectorTests(unittest.TestCase):
    def test_collection_waits_for_independent_acceptance_and_restart_ack_is_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);store=Store();cfg=config();now=datetime(2026,11,3,18,5,tzinfo=worker.ZONE).astimezone(timezone.utc)
            captures=[]
            def fetch(*args):captures.append(1);return pdf(),now,200
            args={'store':store,'clock':lambda:now,'fetcher':fetch,'review_status':lambda sha:'UNKNOWN'}
            result=collect.run(cfg,state,**args)
            self.assertEqual(result['status'],'AWAITING_INDEPENDENT_REVIEW');self.assertEqual(len(captures),1)
            self.assertEqual(len(runner_checkpoint.queue(state,'official_close').entries()),1)
            self.assertEqual(runner_checkpoint.queue(state,'official_close.accepted').entries(),[])
            store.reviewed=True;result=collect.run(cfg,state,**args)
            self.assertEqual(result['status'],'COMPLETE');self.assertEqual(len(captures),1)
            self.assertEqual(runner_checkpoint.queue(state,'official_close').entries(),[])
            self.assertEqual(len(runner_checkpoint.queue(state,'official_close.accepted').entries()),1)

    def test_capture_identity_matches_archive_gateway_contract(self):
        now=datetime(2026,11,3,18,5,tzinfo=timezone.utc)
        job=collect.build(config(),pdf(),now,now.replace(minute=0).isoformat(),200)
        envelope=worker.unpacked(job['archive_sha256'],bytes.fromhex(job['archive_hex']))
        capture=envelope['captures'][0]
        expected=hashlib.sha256(json.dumps([envelope['provider_namespace'],capture['sha256'],capture['received_at']],separators=(',',':')).encode()).hexdigest()
        self.assertEqual(capture['capture_id'],expected)

    def test_invalid_old_capture_is_preserved_without_remote_write_or_relabel(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);cfg=config();now=datetime(2026,11,3,18,5,tzinfo=timezone.utc)
            job=collect.build(cfg,pdf(),now,now.replace(minute=0).isoformat(),200)
            envelope=worker.unpacked(job['archive_sha256'],bytes.fromhex(job['archive_hex']))
            envelope['captures'][0]['capture_id']='f'*64
            digest,blob=worker.packed(envelope);job['archive_sha256']=digest;job['archive_hex']=blob.hex()
            key,original=worker.packed(job)
            pending=runner_checkpoint.queue(state,'official_close');pending.put(key,original)
            store=Store()
            result=collect.deliver_only(cfg,state,store,lambda:now,lambda sha:'UNKNOWN')
            self.assertEqual(result['status'],'INVALID_CAPTURE_QUARANTINED')
            self.assertEqual(store.saved,[])
            self.assertEqual(pending.entries(),[])
            quarantine=runner_checkpoint.queue(state,'official_close.quarantine')
            self.assertEqual(quarantine.read(quarantine.entries()[0]),original)

    def test_failed_review_preserves_exact_intent_and_never_calls_financial_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);store=Store();now=datetime(2026,11,3,18,5,tzinfo=worker.ZONE).astimezone(timezone.utc)
            collect.run(config(),state,store=store,clock=lambda:now,fetcher=lambda *args:(pdf(),now,200),review_status=lambda sha:'UNKNOWN')
            pending=runner_checkpoint.queue(state,'official_close');path=pending.entries()[0];original=pending.read(path)
            result=collect.run(config(),state,store=store,clock=lambda:now,fetcher=lambda *args:self.fail('No refetch during failed-review preservation'),review_status=lambda sha:'FAILED')
            self.assertEqual(result['status'],'REPORT_UNAVAILABLE');self.assertEqual(pending.entries(),[])
            quarantine=runner_checkpoint.queue(state,'official_close.quarantine')
            self.assertEqual(quarantine.read(quarantine.entries()[0]),original)
