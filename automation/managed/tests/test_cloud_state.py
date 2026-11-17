import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cloud_state as cloud
import runner_checkpoint
from worker import AcquisitionError

PIN = 'a' * 64


def run(identifier=20, number=2):
    return {'id': identifier, 'workflow_id': 7, 'head_branch': 'main', 'path': cloud.WORKFLOW,
            'event': 'workflow_dispatch', 'run_attempt': 1, 'run_number': number,
            'status': 'completed', 'conclusion': 'success'}


def artifact(identifier=100, owner=10):
    return {'id': identifier, 'name': f'{cloud.PREFIX}{owner}-1-{PIN}',
            'size_in_bytes': 1024, 'expired': False, 'workflow_run': {'id': owner}}


class API:
    def __init__(self):
        self.repository = {'private': True, 'default_branch': 'main'}
        self.current, self.previous = run(), run(10, 1)
        self.runs = [self.current, self.previous]
        self.artifacts = [artifact()]
        self.calls = []
        self.skipped_jobs = set()

    def call(self, path, method='GET', params=None):
        self.calls.append((method, path))
        if path == '': return copy.deepcopy(self.repository)
        if path == '/actions/workflows/7/runs': return {'workflow_runs': copy.deepcopy(self.runs)}
        if path == '/actions/artifacts': return {'artifacts': copy.deepcopy(self.artifacts)}
        if path.endswith('/attempts/1/jobs'):
            owner = int(path.split('/')[3])
            return {'jobs':[{'name':'collect','conclusion':'skipped' if owner in self.skipped_jobs else 'success'}]}
        if path.endswith('/artifacts'):
            owner = int(path.split('/')[-2])
            return {'artifacts': [copy.deepcopy(v) for v in self.artifacts if v['workflow_run']['id'] == owner]}
        if path.startswith('/actions/runs/'):
            return copy.deepcopy(next(v for v in self.runs if v['id'] == int(path.rsplit('/', 1)[1])))
        if path.startswith('/actions/artifacts/'):
            value = next(v for v in self.artifacts if v['id'] == int(path.rsplit('/', 1)[1]))
            if method == 'DELETE': self.artifacts.remove(value)
            return copy.deepcopy(value)
        raise AssertionError(path)


class CloudStateTests(unittest.TestCase):
    def test_only_reviewed_no_job_incident_runs_are_bypassed(self):
        api = API()
        middle = run(42671126097, 2)
        middle['conclusion'] = 'failure'
        api.current['run_number'] = 3
        api.runs.append(middle)
        original = api.call
        def call(path, **kwargs):
            if path.endswith('/attempts/1/jobs') and str(middle['id']) in path:
                return {'jobs': []}
            return original(path, **kwargs)
        api.call = call
        self.assertEqual(cloud.select(api, 20)['previous_run_id'], '10')
        middle['id'] = 12345
        with self.assertRaisesRegex(AcquisitionError, 'LATEST_CHECKPOINT_MISSING'):
            cloud.select(api, 20)

    def test_exact_predecessor_pin_and_failed_collector_checkpoint_supported(self):
        api = API()
        expected = {'bootstrap': 'false', 'previous_run_id': '10', 'artifact_id': '100', 'sha256': PIN}
        self.assertEqual(cloud.select(api, 20), expected)
        api.previous['conclusion'] = 'failure'
        self.assertEqual(cloud.select(api, 20), expected)
        self.assertFalse(any(method != 'GET' for method, _ in api.calls))

    def test_lost_latest_never_falls_back_to_older_artifact(self):
        api = API()
        api.artifacts = [artifact(owner=5)]
        with self.assertRaisesRegex(AcquisitionError, 'LATEST_CHECKPOINT_MISSING'):
            cloud.select(api, 20)
        with self.assertRaises(AcquisitionError): cloud.select(api, 20, bootstrap=True)

    def test_selector_failure_can_be_bypassed_only_before_state_execution(self):
        api = API()
        middle = run(15, 2)
        middle['conclusion'] = 'failure'
        api.current['run_number'] = 3
        api.runs.append(middle)
        original = api.call
        steps = [
            {'name': 'Select exact preceding checkpoint', 'conclusion': 'failure'},
            *[{'name': name, 'conclusion': 'skipped'} for name in [
                'Restore or explicitly bootstrap private queues',
                'Run existing collector with bounded execution',
                'Checkpoint even after collector failure']],
        ]
        def call(path, **kwargs):
            if path == '/actions/runs/15/attempts/1/jobs':
                return {'jobs': [{'name': 'collect', 'steps': steps}]}
            return original(path, **kwargs)
        api.call = call
        self.assertEqual(cloud.select(api, 20)['previous_run_id'], '10')
        steps[2]['conclusion'] = 'success'
        with self.assertRaisesRegex(AcquisitionError, 'LATEST_CHECKPOINT_MISSING'):
            cloud.select(api, 20)
        steps[2]['conclusion'] = 'skipped'
        steps.pop(1)
        with self.assertRaisesRegex(AcquisitionError, 'LATEST_CHECKPOINT_MISSING'):
            cloud.select(api, 20)

    def test_empty_bootstrap_is_explicit_and_only_at_start(self):
        api = API(); api.runs = [api.current]; api.artifacts = []
        with self.assertRaises(AcquisitionError): cloud.select(api, 20)
        self.assertEqual(cloud.select(api, 20, bootstrap=True)['bootstrap'], 'true')
        api.artifacts = [artifact()]
        with self.assertRaises(AcquisitionError): cloud.select(api, 20, bootstrap=True)

    def test_successful_workflow_with_guard_skipped_job_does_not_break_chain(self):
        api = API()
        api.skipped_jobs.add(10)
        api.artifacts = []
        self.assertEqual(cloud.select(api,20,bootstrap=True)['bootstrap'], 'true')
        middle = run(15, 2); api.current['run_number'] = 3
        api.runs.append(middle); api.skipped_jobs = {15}; api.artifacts = [artifact()]
        self.assertEqual(cloud.select(api,20)['previous_run_id'], '10')

    def test_private_default_branch_and_first_attempt_are_required(self):
        for change in ({'head_branch': 'other'}, {'run_attempt': 2}, {'path': 'other.yml'}, {'event': 'pull_request'}):
            api = API(); api.current.update(change)
            with self.subTest(change=change), self.assertRaises(AcquisitionError): cloud.select(api, 20)
        api = API(); api.repository['private'] = False
        with self.assertRaises(AcquisitionError): cloud.select(api, 20)

    def test_cancelled_inflight_rerun_or_newer_run_never_uses_stale_state(self):
        for change in ({'status': 'in_progress'}, {'run_attempt': 2}):
            api = API(); api.previous.update(change)
            with self.subTest(change=change), self.assertRaises(AcquisitionError): cloud.select(api, 20)
        api = API(); api.runs.append(run(30, 3))
        with self.assertRaisesRegex(AcquisitionError, 'STALE_RUN'): cloud.select(api, 20)
        api = API(); api.previous['conclusion'] = 'cancelled'; api.artifacts = []
        with self.assertRaises(AcquisitionError): cloud.select(api, 20)

    def test_expired_wrong_owner_duplicate_and_oversized_artifacts_fail(self):
        for change in ({'expired': True}, {'name': f'{cloud.PREFIX}99-1-{PIN}'},
                       {'size_in_bytes': cloud.MAX_ARTIFACT + 1}):
            api = API(); api.artifacts[0].update(change)
            with self.subTest(change=change), self.assertRaises(AcquisitionError): cloud.select(api, 20)
        api = API(); api.artifacts.append(artifact(101))
        with self.assertRaises(AcquisitionError): cloud.select(api, 20)

    def test_storage_budget_fails_before_new_capture(self):
        api = API()
        api.artifacts[0]['size_in_bytes'] = cloud.BUDGET
        with self.assertRaisesRegex(AcquisitionError, 'STORAGE_BUDGET'): cloud.select(api, 20)

    def test_retention_preserves_current_previous_and_unrelated_workflows(self):
        api = API()
        old = run(5, 0); old['run_number'] = 1
        unrelated = run(6, 1); unrelated['workflow_id'] = 999
        api.runs += [old, unrelated]
        api.artifacts += [artifact(200, 20), artifact(50, 5), artifact(60, 6)]
        self.assertEqual(cloud.prune(api, 20, 200, PIN, 10)['superseded_checkpoints_removed'], 1)
        self.assertEqual({v['id'] for v in api.artifacts}, {100, 200, 60})

    def test_bad_uploaded_receipt_causes_zero_deletions(self):
        api = API(); api.artifacts += [artifact(200, 20)]
        with self.assertRaises(AcquisitionError): cloud.prune(api, 20, 200, 'b'*64, 10)
        self.assertFalse(any(method == 'DELETE' for method, _ in api.calls))

    def test_download_modes_can_be_normalized_but_no_extra_files_or_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); state = root/'state'; state.mkdir(mode=0o700)
            output = root/'exported'
            result = runner_checkpoint.pack(state, output)
            os.chmod(output, 0o755)
            os.chmod(output/runner_checkpoint.MANIFEST, 0o644)
            cloud.verify_download(output, root/'restored', result['manifest_sha256'])
            self.assertEqual((output.stat().st_mode & 0o777), 0o700)
            (output/'private-key').write_text('fixture')
            with self.assertRaises(AcquisitionError): cloud.downloaded(output)

    def test_failed_readback_never_calls_retention_api(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(cloud, 'GitHub') as api:
            root = Path(temporary)
            with patch.dict(os.environ, {'GITHUB_RUN_ID': '20'}):
                status = cloud.main(['finish', '--checkpoint', str(root/'missing'),
                    '--verify-state', str(root/'restored'), '--sha256', PIN,
                    '--artifact-id', '200', '--previous-run-id', '10'])
            self.assertEqual(status, 1)
            api.assert_not_called()


if __name__ == '__main__': unittest.main()
