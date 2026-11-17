import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner_checkpoint as checkpoint
from worker import AcquisitionError


class RunnerCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.state.mkdir(mode=0o700)
        self.output = self.root / 'checkpoint'
        self.restored = self.root / 'restored'

    def test_existing_v3_checkpoint_restores_and_upgrades_without_loss(self):
        from unittest.mock import patch
        values=self.seed()
        checkpoint.queue(self.state,'receipts.history')._check_directory()
        with patch.object(checkpoint,'ALL_CHANNELS',checkpoint.HISTORY_CHANNELS):
            checkpoint.pack(self.state,self.output)
        self.assertEqual(json.loads((self.output/checkpoint.MANIFEST).read_text())['contract'],checkpoint.RECEIPT_HISTORY_CONTRACT)
        checkpoint.restore(self.output,self.restored,expected_sha256=self.pin())
        for channel,(digest,raw) in values.items():
            self.assertEqual(checkpoint.queue(self.restored,channel).read(self.restored/channel/(digest+'.json.gz')),raw)
        for channel in set(checkpoint.ALL_CHANNELS)-set(checkpoint.HISTORY_CHANNELS):
            self.assertEqual(checkpoint.queue(self.restored,channel).entries(),[])
        upgraded=self.root/'upgraded'
        checkpoint.pack(self.restored,upgraded)
        self.assertEqual(json.loads((upgraded/checkpoint.MANIFEST).read_text())['contract'],checkpoint.OFFICIAL_CONTRACT)

    def seed(self):
        values = {}
        for channel in checkpoint.CHANNELS:
            value = ('original-' + channel).encode()
            digest = hashlib.sha256(value).hexdigest()
            checkpoint.queue(self.state, channel).put(digest, value)
            values[channel] = (digest, value)
        return values

    def pin(self):
        return hashlib.sha256((self.output / checkpoint.MANIFEST).read_bytes()).hexdigest()

    def test_all_six_queues_survive_disposal_with_exact_bytes(self):
        values = self.seed()
        result = checkpoint.pack(self.state, self.output)
        self.assertEqual(result['entries'], 6)
        self.assertEqual(checkpoint.restore(self.output, self.restored,
                                          expected_sha256=result['manifest_sha256'])['entries'], 6)
        for channel, (digest, value) in values.items():
            self.assertEqual((self.restored / channel / (digest + '.json.gz')).read_bytes(), value)
            self.assertEqual((self.state / channel / (digest + '.json.gz')).read_bytes(), value)
        self.assertTrue((self.restored / checkpoint.MANIFEST).exists())

    def test_actual_publication_receipt_restores_logical_completion(self):
        import price_publication
        import market_collect
        import worker
        from test_price_publication import Publisher
        from test_app_publish import profile
        from test_market_collect import config
        from test_market_frame import body, CAPTURED
        cfg, pins = config(), profile()
        store = worker.SQLiteStore(self.root / 'isolated.sqlite')
        self.addCleanup(store.db.close)
        publications = price_publication.Publications(cfg, pins, self.state / 'quotes')
        value = market_collect.envelope(cfg, json.dumps(body()).encode(), CAPTURED,
                                       CAPTURED.isoformat(), execution='CURRENT_ACQUISITION')
        publications.enqueue(value, now=CAPTURED)
        publications.flush(store, publisher=Publisher())
        self.assertTrue(publications.complete(value['slot']))
        result = checkpoint.pack(self.state, self.output)
        self.assertEqual(result['entries'], 1)
        checkpoint.restore(self.output, self.restored, expected_sha256=result['manifest_sha256'])
        restored = price_publication.Publications(cfg, pins, self.restored / 'quotes')
        self.assertTrue(restored.complete(value['slot']))
        self.assertEqual(restored.pending.entries(), [])

    def test_wrong_producer_layout_is_rejected_without_completion_marker(self):
        (self.state / 'accepted').mkdir(mode=0o700)
        with self.assertRaisesRegex(AcquisitionError, 'UNEXPECTED_STATE'):
            checkpoint.pack(self.state, self.output)
        self.assertFalse(self.output.exists())

    def test_explicit_empty_checkpoint_does_not_resurrect_old_jobs(self):
        result = checkpoint.pack(self.state, self.output)
        self.assertEqual(result['entries'], 0)
        checkpoint.restore(self.output, self.restored, expected_sha256=self.pin())
        self.assertTrue(all(not checkpoint.queue(self.restored, c).entries()
                            for c in checkpoint.CHANNELS))

    def test_corrupt_last_channel_never_partially_restores_first(self):
        self.seed()
        checkpoint.pack(self.state, self.output)
        target = self.output / 'enrichment.zip'
        target.write_bytes(target.read_bytes()[:-1] + b'x')
        with self.assertRaises(AcquisitionError):
            checkpoint.restore(self.output, self.restored, expected_sha256=self.pin())
        self.assertFalse(self.restored.exists())

    def test_changed_pin_and_existing_target_and_symlinks_are_rejected(self):
        self.seed()
        checkpoint.pack(self.state, self.output)
        with self.assertRaises(AcquisitionError):
            checkpoint.restore(self.output, self.restored, expected_sha256='0' * 64)
        self.restored.mkdir(mode=0o700)
        with self.assertRaises(AcquisitionError):
            checkpoint.restore(self.output, self.restored, expected_sha256=self.pin())
        self.restored.rmdir()
        target = self.output / 'archive.zip'
        payload = target.read_bytes()
        target.unlink()
        elsewhere = self.root / 'elsewhere'
        elsewhere.write_bytes(payload)
        target.symlink_to(elsewhere)
        with self.assertRaises(OSError):
            checkpoint.restore(self.output, self.restored, expected_sha256=self.pin())
        self.assertFalse(self.restored.exists())

    def test_incomplete_checkpoint_and_extra_file_fail_closed(self):
        self.output.mkdir(mode=0o700)
        with self.assertRaises(FileNotFoundError):
            checkpoint.restore(self.output, self.restored, expected_sha256='0' * 64)
        self.output.rmdir()
        checkpoint.pack(self.state, self.output)
        (self.output / 'unapproved.txt').write_text('fixture')
        with self.assertRaises(AcquisitionError):
            checkpoint.restore(self.output, self.restored, expected_sha256=self.pin())
        self.assertFalse(self.restored.exists())

    def test_wrong_channel_and_count_are_rejected_even_with_recomputed_pin(self):
        for change in ({'kind': 'archive'}, {'entries': 2}, {'bytes': True}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                state = root / 'state'
                state.mkdir(mode=0o700)
                value = b'quote'
                checkpoint.queue(state, 'quotes').put(hashlib.sha256(value).hexdigest(), value)
                exported = root / 'checkpoint'
                checkpoint.pack(state, exported)
                manifest = exported / checkpoint.MANIFEST
                parsed = json.loads(manifest.read_bytes())
                parsed['channels']['quotes'].update(change)
                manifest.write_text(json.dumps(parsed))
                pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
                with self.assertRaises(AcquisitionError):
                    checkpoint.restore(exported, root / 'restored', expected_sha256=pin)
                self.assertFalse((root / 'restored').exists())

    def test_private_permissions_and_overlapping_paths_and_capacity(self):
        os.chmod(self.state, 0o755)
        with self.assertRaises(AcquisitionError):
            checkpoint.pack(self.state, self.output)
        os.chmod(self.state, 0o700)
        with self.assertRaises(AcquisitionError):
            checkpoint.pack(self.state, self.state / 'nested')
        self.seed()
        from unittest.mock import patch
        with patch.object(checkpoint, 'MAX_TOTAL', 1):
            with self.assertRaises(AcquisitionError):
                checkpoint.pack(self.state, self.output)
        self.assertFalse((self.output / checkpoint.MANIFEST).exists())
        self.assertEqual(sum(len(checkpoint.queue(self.state, c).entries())
                             for c in checkpoint.CHANNELS), 6)

    def test_legacy_v1_restores_all_original_bytes_and_initializes_only_new_empty_queues(self):
        from unittest.mock import patch
        with patch.object(checkpoint,'CONTRACT',checkpoint.LEGACY_CONTRACT),patch.object(checkpoint,'CHANNELS',checkpoint.LEGACY_CHANNELS):
            values=self.seed()
            original=checkpoint.pack(self.state,self.output)
        marker=(self.output/checkpoint.MANIFEST).read_bytes()
        checkpoint.restore(self.output,self.restored,expected_sha256=original['manifest_sha256'])
        for channel,(digest,body) in values.items():
            self.assertEqual((self.restored/channel/(digest+'.json.gz')).read_bytes(),body)
        for channel in ['dividends','dividends.accepted']:self.assertEqual(checkpoint.queue(self.restored,channel).entries(),[])
        self.assertEqual((self.output/checkpoint.MANIFEST).read_bytes(),marker)
        upgraded=self.root/'upgraded'
        checkpoint.pack(self.restored,upgraded)
        self.assertEqual(json.loads((upgraded/checkpoint.MANIFEST).read_text())['contract'],'private-runner-checkpoint/v2')

    def test_combined_headroom_blocks_capture_while_existing_state_remains_packable(self):
        from unittest.mock import patch
        import worker
        # Four individually valid8MiB entries leave insufficient space for a32MiB job.
        for channel in ['archive','quotes']:
            for i in range(2):
                body=(channel+str(i)).encode().ljust(8*1024*1024,b'x')
                checkpoint.queue(self.state,channel).put(hashlib.sha256(body).hexdigest(),body)
        with patch.dict(os.environ,{'APP_CHECKPOINT_ROOT':str(self.state)}):
            with self.assertRaisesRegex(AcquisitionError,'BYTE_HEADROOM'):
                worker.require_checkpoint_acquisition_headroom('dividends')
        checkpoint.pack(self.state,self.output)
        self.assertTrue((self.output/checkpoint.MANIFEST).exists())

    def test_entry_reservation_and_zip_overhead_are_enforced_before_mutation(self):
        for i in range(64):
            body=str(i).encode();checkpoint.queue(self.state,'dividends.accepted').put(hashlib.sha256(body).hexdigest(),body)
        with self.assertRaisesRegex(AcquisitionError,'ENTRY_HEADROOM'):
            checkpoint.require_headroom(self.state,reserve_bytes=4096,additions={'dividends.accepted':1})
        from unittest.mock import patch
        with patch.object(checkpoint,'MAX_TOTAL',8*64*1024):
            with self.assertRaisesRegex(AcquisitionError,'BYTE_HEADROOM'):
                checkpoint.require_headroom(self.state,reserve_bytes=0,additions={})


if __name__ == '__main__':
    unittest.main()
