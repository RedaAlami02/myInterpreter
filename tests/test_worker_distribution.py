import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_worker_distribution as worker
import build_deployment_review as review


class WorkerDistributionTests(unittest.TestCase):
    def contents(self):
        return {path:review.read_regular(ROOT,source) for path,source in worker.selection().items()}

    def test_selected_files_validate_and_include_all_new_worker_and_boundary_dependencies(self):
        files = self.contents()
        worker.validate(files)
        for path in ['cloud_state.py','cloud_collect.py','runner_checkpoint.py','verify_worker.py',
                     'gateway/supabase.ts','app-publisher/supabase.ts','projection-publisher/supabase.ts']:
            self.assertIn(path, files)
        self.assertFalse(any('cloud_function/' in path or path.endswith('.sql') for path in files))
        self.assertFalse(any('test_price_ratio_parity' in path for path in files))

    def test_slim_runtime_keeps_collection_gates_and_rejects_unknown_runner(self):
        files = self.contents()
        durable = files['.github/workflows/collect-durable.yml']
        self.assertIn(b'runs-on: ubuntu-slim', durable)
        self.assertIn(b'APP_DURABLE_COLLECTION_ENABLED', durable)
        self.assertIn(b'APP_CHECKPOINT_HEADROOM_VERIFIED', durable)
        self.assertIn(b'--target "$RUNNER_TEMP/worker-deps"', durable)
        files['.github/workflows/collect-durable.yml'] = durable.replace(
            b'runs-on: ubuntu-slim', b'runs-on: self-hosted')
        with self.assertRaises(ValueError):
            worker.validate(files)

    def test_financial_secrets_are_isolated_to_protected_review(self):
        for mutation in ['collector_secret','missing_environment','write_permission']:
            files=self.contents()
            if mutation=='collector_secret':
                files['.github/workflows/collect-durable.yml']+=b'\n# APP_OFFICIAL_ATTESTATION_KEY\n'
            elif mutation=='missing_environment':
                files['.github/workflows/official-review.yml']=files['.github/workflows/official-review.yml'].replace(b'environment: official-close-review',b'environment: unprotected')
            else:
                files['.github/workflows/official-review.yml']=files['.github/workflows/official-review.yml'].replace(b'actions: read',b'actions: write')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):worker.validate(files)

    def test_private_literal_cannot_be_published(self):
        files = self.contents()
        files['worker.py'] += b'\n# private-fixture-identity\n'
        with self.assertRaises(ValueError): worker.validate(files, ['private-fixture-identity'])

    def test_recurring_unpinned_or_incomplete_boundary_packages_rejected(self):
        for mutation in ['schedule', 'action', 'dependency']:
            files = self.contents()
            path = '.github/workflows/collect-durable.yml'
            if mutation == 'schedule':
                files[path] = files[path].replace(b'on:\n', b'on:\n  schedule: []\n')
            elif mutation == 'action':
                files[path] = files[path].replace(b'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02', b'actions/upload-artifact@v4')
            else: del files['gateway/supabase.ts']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): worker.validate(files)


if __name__ == '__main__': unittest.main()
