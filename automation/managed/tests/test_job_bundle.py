import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from outbox import Outbox
import outbox_bundle as bundle
import worker


class JobBundleTests(unittest.TestCase):
    def test_large_job_survives_runner_disposal_without_changing_any_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blob = b'x' * (worker.MAX_BATCH + 1)
            digest = hashlib.sha256(blob).hexdigest()
            Outbox(root/'before', entry_limit=24*1024*1024).put(digest, blob)
            exported = root/'private.zip'
            bundle.pack(root/'before', exported, kind='enrichment')
            result = bundle.unpack(exported, root/'after', kind='enrichment')
            self.assertEqual(result['restored'], 1)
            self.assertEqual((root/'after'/(digest+'.json.gz')).read_bytes(), blob)
            self.assertEqual(bundle.unpack(exported, root/'after', kind='enrichment')['already_present'], 1)
            with self.assertRaises(worker.AcquisitionError):
                bundle.unpack(exported, root/'wrong')
            self.assertEqual(list((root/'before').glob('*.json.gz'))[0].read_bytes(), blob)

    def test_payload_type_and_entry_limits_cannot_be_relabelled(self):
        for update in [{'entry_limit': 1000000000}, {'payload_kind': 'archive'},
                       {'contract': bundle.CONTRACT}, {'entry_limit': True}]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                blob = b'fixture'
                digest = hashlib.sha256(blob).hexdigest()
                manifest = {'contract': bundle.JOB_CONTRACT, 'payload_kind': 'enrichment',
                            'entry_limit': bundle.MAX_JOB_ENTRY, 'entries': [
                                {'name': digest+'.json.gz', 'sha256': digest, 'bytes': len(blob)}], **update}
                with zipfile.ZipFile(root/'bad.zip', 'w') as archive:
                    archive.writestr('manifest.json', json.dumps(manifest))
                    archive.writestr(digest+'.json.gz', blob)
                with self.assertRaises(worker.AcquisitionError):
                    bundle.unpack(root/'bad.zip', root/'after', kind='enrichment')
                self.assertFalse((root/'after').exists())
