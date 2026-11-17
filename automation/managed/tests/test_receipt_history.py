import hashlib,json,tempfile,unittest
from pathlib import Path
import receipt_history as history
import runner_checkpoint as checkpoint
import worker


class ReceiptHistoryTests(unittest.TestCase):
    def test_more_than_two_days_preserves_every_original_receipt_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';state.mkdir(mode=0o700)
            all_receipts={}
            for i in range(120):
                value={'contract':'private-price-publication-commit/v1','job_sha256':hashlib.sha256(str(i).encode()).hexdigest(),
                       'accepted_at':f'2026-11-02T12:{i//60:02}:{i%60:02}+00:00'}
                key,raw=worker.packed(value);all_receipts[key]=raw
                checkpoint.queue(state,'quotes.accepted').put(key,raw)
                history.compact(state)
                checkpoint.require_headroom(state,reserve_bytes=0,additions={'quotes.accepted':1})
            self.assertLess(len(checkpoint.queue(state,'quotes.accepted').entries()),32)
            exported=root/'export';packed=checkpoint.pack(state,exported)
            self.assertEqual(json.loads((exported/checkpoint.MANIFEST).read_text())['contract'],checkpoint.OFFICIAL_CONTRACT)
            restored=root/'restored';checkpoint.restore(exported,restored,expected_sha256=packed['manifest_sha256'])
            actual={p.name[:64]:checkpoint.queue(restored,'quotes.accepted').read(p) for p in checkpoint.queue(restored,'quotes.accepted').entries()}
            for p in checkpoint.queue(restored,'receipts.history').entries():
                value=worker.unpacked(p.name[:64],checkpoint.queue(restored,'receipts.history').read(p))
                actual.update({key:bytes.fromhex(v['raw_hex']) for key,v in value['receipts'].items()})
            self.assertEqual(actual,all_receipts)

    def test_official_receipts_survive_more_than_64_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);expected={}
            for i in range(100):
                key,raw=worker.packed({'job_sha256':hashlib.sha256(str(i).encode()).hexdigest(),
                                      'accepted_at':f'2026-11-02T12:{i//60:02}:{i%60:02}+00:00'})
                expected[key]=raw
                checkpoint.queue(state,'official_close.accepted').put(key,raw)
                history.compact(state)
            actual={p.name[:64]:checkpoint.queue(state,'official_close.accepted').read(p) for p in checkpoint.queue(state,'official_close.accepted').entries()}
            for p in checkpoint.queue(state,'receipts.history').entries():
                actual.update({k:bytes.fromhex(v['raw_hex']) for k,v in worker.unpacked(p.name[:64],checkpoint.queue(state,'receipts.history').read(p))['receipts'].items()})
            self.assertEqual(actual,expected)

    def test_interrupted_job_receipt_stays_individual_and_pending_is_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);key,raw=worker.packed({'pending':True})
            checkpoint.queue(state,'quotes').put(key,raw)
            for i in range(4):
                receipt={'job_sha256':key if i==0 else str(i)*64,'accepted_at':f'2026-11-02T12:00:0{i}+00:00'}
                digest,body=worker.packed(receipt);checkpoint.queue(state,'quotes.accepted').put(digest,body)
                if i==0: protected=digest
            history.compact(state,threshold=4,keep=1)
            self.assertEqual(checkpoint.queue(state,'quotes').read(checkpoint.queue(state,'quotes').entries()[0]),raw)
            self.assertTrue(any(p.name.startswith(protected) for p in checkpoint.queue(state,'quotes.accepted').entries()))
