"""Offline proposal boundaries; synthetic private profiles, no credentials/network."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'automation/managed/tests'))
import prepare_manual_trial as trial
import test_app_feed as fixtures


class ManualTrialPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'private/proposal'
        for name in set(trial.runtime.assets().values()) | {
                f'automation/{folder}/config.toml.example' for folder, _ in trial.runtime.FUNCTIONS.values()
                } | {trial.GATE}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)
        self.bundle = self.root / 'private/runtime'
        self.pin = trial.runtime.build(self.root, self.bundle)['manifest_sha256']
        config = fixtures.config()
        config['archive_project_reference'] = 'fixtureproject0000'
        config['recipe']['expected_index_identities'] = ['MASI']
        config['recipe']['views']['indices']['constants']['source_identity'] = 'MASI'
        mapping = fixtures.mapping()
        mapping['indices'] = [dict(source_identity='MASI', company_id=None,
            asset_key='index:MASI', c_name='MASI', symbol='MASI')]
        self.config = self.root / 'private/config.json'
        self.mapping = self.root / 'private/mapping.json'
        self.config.write_text(json.dumps(config))
        self.mapping.write_text(json.dumps(mapping))

    def build(self, **kwargs):
        args = dict(root=self.root, output=self.output, config_path=self.config,
            mapping_path=self.mapping, bundle=self.bundle, pin=self.pin)
        args.update(kwargs)
        return trial.build(**args)

    def test_proposal_contains_only_bounded_quote_shadow_scope(self):
        receipt = self.build()
        plan = json.loads((self.output / 'PLAN.private.json').read_text())
        self.assertEqual(plan['capabilities'], ['archive', 'shadow_feed'])
        self.assertEqual((plan['max_objects'], plan['logical_captures'], plan['lease_seconds']), (1, 1, 300))
        self.assertEqual(plan['source_request_attempts_max'], 2)
        self.assertFalse(any(plan[name] for name in ('authorized', 'schedules', 'application_table_writes',
            'projection_activation', 'prediction_eligible', 'portfolio_valuation_eligible')))
        self.assertEqual(plan['kinds'], ['quotes'])
        self.assertFalse(receipt['deployment_performed'])
        self.assertEqual(os.stat(self.output).st_mode & 0o777, 0o700)
        for path in self.output.rglob('*'):
            if path.is_file():
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_wrong_runtime_pin_refused_without_output(self):
        with self.assertRaises(ValueError):
            self.build(pin='0' * 64)
        self.assertFalse(self.output.exists())

    def test_modified_current_worker_refused_without_output(self):
        path = self.root / 'automation/managed/worker.py'
        path.write_text(path.read_text() + '\n# changed after review\n')
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_namespace_conflict_and_extra_credential_fields_refused(self):
        config = json.loads(self.config.read_text())
        for updated in (dict(config, provider_namespace='feed_fedcba9876543210'),
                        dict(config, APP_ARCHIVE_WRITE_TOKEN='fixture-not-a-real-token')):
            self.config.write_text(json.dumps(updated))
            with self.assertRaises(ValueError):
                self.build()
            self.assertFalse(self.output.exists())

    def test_output_outside_private_and_overwrite_refused(self):
        with self.assertRaises(ValueError):
            self.build(output=self.root / 'public-proposal')
        self.build()
        before = (self.output / 'PLAN.private.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual((self.output / 'PLAN.private.json').read_bytes(), before)

    def test_symlinked_private_input_refused(self):
        real = self.root / 'private/original.json'
        self.config.rename(real)
        self.config.symlink_to(real)
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_exact_main_index_refused(self):
        mapping = json.loads(self.mapping.read_text())
        mapping['indices'][0]['asset_key'] = 'index:OTHER'
        self.mapping.write_text(json.dumps(mapping))
        with self.assertRaises(ValueError):
            self.build()

    def test_captured_bytes_and_pins_are_reproducible(self):
        first = self.build()
        second = self.build(output=self.root / 'private/second')
        self.assertEqual(first, second)
        self.assertEqual((self.output / 'market-config.private.json').read_bytes(), self.config.read_bytes())
        profile = json.loads((self.output / 'publish-profile.private.json').read_text())
        self.assertEqual(profile['mapping_sha256'], trial.app_feed.fingerprint(profile['mapping']))

    def test_external_pin_is_required_and_tampered_sql_is_rejected(self):
        receipt = self.build()
        self.assertTrue(trial.verify(self.output, receipt['plan_sha256'])['verified'])
        with self.assertRaises(ValueError):
            trial.verify(self.output, None)
        path = self.output / trial.GATE
        path.write_text(path.read_text() + '\n-- altered after review\n')
        with self.assertRaises(ValueError):
            trial.verify(self.output, receipt['plan_sha256'])

    def test_extra_or_symlinked_proposal_file_is_rejected(self):
        receipt = self.build()
        extra = self.output / 'unreviewed.txt'
        extra.write_text('extra')
        with self.assertRaises(ValueError):
            trial.verify(self.output, receipt['plan_sha256'])
        extra.unlink()
        path = self.output / 'market-config.private.json'
        path.unlink()
        path.symlink_to(self.config)
        with self.assertRaises(ValueError):
            trial.verify(self.output, receipt['plan_sha256'])


if __name__ == '__main__':
    unittest.main()
