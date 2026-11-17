from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import checkpoint_smoke as smoke
from worker import AcquisitionError


class API:
    def __init__(self, pin): self.pin, self.deleted, self.prefix = pin, [], smoke.PREFIX
    def call(self, path, method='GET'):
        if method == 'DELETE': self.deleted.append(path); return
        if path == '': return {'private':True}
        if path.startswith('/actions/runs/'): return {'path':'.github/workflows/verify.yml','event':'workflow_dispatch'}
        return {'name':self.prefix+'20-'+self.pin,'workflow_run':{'id':20}}


class SyntheticCheckpointTests(unittest.TestCase):
    def test_roundtrip_checks_every_synthetic_queue_then_removes_only_own_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = smoke.create(root/'state', root/'checkpoint', 20)
            api = API(prepared['manifest_sha256'])
            result = smoke.finish(api,root/'checkpoint',root/'restored',api.pin,100,20)
            self.assertEqual(result['entries'],6)
            self.assertTrue(result['synthetic_artifact_removed'])
            self.assertEqual(api.deleted,['/actions/artifacts/100'])

    def test_synthetic_cleanup_cannot_delete_a_production_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = smoke.create(root/'state',root/'checkpoint',20)
            api = API(prepared['manifest_sha256']); api.prefix = 'private-state-v1-'
            with self.assertRaises(AcquisitionError):
                smoke.finish(api,root/'checkpoint',root/'restored',api.pin,100,20)
            self.assertEqual(api.deleted,[])


if __name__ == '__main__': unittest.main()
