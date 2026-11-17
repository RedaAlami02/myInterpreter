"""Local-only bundle integrity and privacy boundaries; no remote services."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_review', ROOT / 'tools/build_deployment_review.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeploymentReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'private/bundle'
        sources = set(module.assets().values()) | {
            f'automation/{folder}/config.toml.example' for folder, _ in module.FUNCTIONS.values()}
        for name in sources:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def build(self):
        return module.build(self.root, self.output)

    def test_fixed_selection_has_no_workflows_configs_raw_or_credentials(self):
        receipt = self.build()
        self.assertEqual(receipt['files_verified'], 51)
        self.assertFalse(receipt['deployment_performed'])
        self.assertFalse(receipt['activation_ready'])
        self.assertTrue(receipt['external_manifest_pin_verified'])
        self.assertFalse(any(path.name in ['.env', '.git', '.github', 'sources.py']
                             for path in self.output.rglob('*')))
        self.assertEqual(module.verify(self.output, receipt['manifest_sha256']), receipt)

    def test_identical_inputs_produce_identical_manifest_and_bytes(self):
        first = self.build()
        other = self.root / 'private/other'
        second = module.build(self.root, other)
        self.assertEqual(first, second)
        for name in module.assets():
            self.assertEqual((self.output / name).read_bytes(), (other / name).read_bytes())

    def test_legacy_v1_selection_remains_verifiable_after_v2_additions(self):
        # Synthetic old contract, not a rewritten actual historical package.
        for relative in module.assets(legacy=True).values():
            if relative.endswith('.py'):
                (self.root / relative).write_text('"""Synthetic legacy fixture."""\n')
        with patch.object(module, 'WORKERS', module.LEGACY_WORKERS), \
                patch.object(module, 'MIGRATIONS', module.LEGACY_MIGRATIONS):
            self.build()
        manifest = self.output / module.MANIFEST
        value = json.loads(manifest.read_text())
        value['contract'] = 'app-deployment-review/v1'
        manifest.write_text(json.dumps(value))
        pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.assertEqual(module.verify(self.output, pin)['files_verified'], 41)

    def test_refuses_overwrite_or_output_outside_private(self):
        self.build()
        original = (self.output / module.MANIFEST).read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual((self.output / module.MANIFEST).read_bytes(), original)
        with self.assertRaises(ValueError):
            module.build(self.root, self.root / 'public-review')

    def test_missing_source_fails_before_creating_output(self):
        (self.root / 'automation/managed/worker.py').unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_source_and_bundle_symlinks_are_refused(self):
        source = self.root / 'automation/managed/worker.py'
        source.unlink()
        source.symlink_to(ROOT / 'automation/managed/worker.py')
        with self.assertRaises(ValueError):
            self.build()
        source.unlink()
        shutil.copyfile(ROOT / 'automation/managed/worker.py', source)
        self.build()
        target = self.output / 'automation/managed/worker.py'
        target.unlink()
        target.symlink_to(source)
        with self.assertRaises(ValueError):
            module.verify(self.output)

    def test_source_fifo_does_not_block_and_is_refused(self):
        source = self.root / 'automation/managed/worker.py'
        source.unlink()
        os.mkfifo(source)
        with self.assertRaises(ValueError):
            self.build()

    def test_known_private_literal_rejected_without_output(self):
        source = self.root / 'automation/managed/worker.py'
        source.write_text(source.read_text() + '\n# fixture-private-identity\n')
        with self.assertRaises(ValueError):
            module.build(self.root, self.output, ('fixture-private-identity',))
        self.assertFalse(self.output.exists())

    def test_secret_and_database_uri_literals_are_refused(self):
        source = self.root / 'automation/managed/worker.py'
        body = source.read_text()
        for literal in ['sb_secret_' + 'X' * 32, 'postgresql://fixture:password@fixture/db']:
            source.write_text(body + '\n# ' + literal + '\n')
            with self.assertRaises(ValueError):
                self.build()
            self.assertFalse(self.output.exists())

    def test_missing_local_or_remote_ts_dependency_is_refused(self):
        source = self.root / 'automation/app-publisher/index.ts'
        body = source.read_text()
        for statement in ['import "https://example.invalid/runtime.ts";',
                          'import { x } from "./missing.ts";',
                          'const x = import("./publisher.ts");']:
            source.write_text(body + '\n' + statement)
            with self.assertRaises(ValueError):
                self.build()

    def test_unbundled_python_dependency_is_refused(self):
        source = self.root / 'automation/managed/worker.py'
        source.write_text(source.read_text() + '\nimport unavailable_private_module\n')
        with self.assertRaises(ValueError):
            self.build()

    def test_configuration_cannot_silently_change_authorization(self):
        source = self.root / 'automation/archive-gateway/config.toml.example'
        source.write_text(source.read_text().replace('verify_jwt = false', 'verify_jwt = true'))
        with self.assertRaises(ValueError):
            self.build()

    def test_byte_tamper_missing_file_extra_file_and_directory_are_refused(self):
        self.build()
        target = self.output / 'automation/managed/worker.py'
        original = target.read_bytes()
        target.write_bytes(original + b'\n')
        with self.assertRaises(ValueError):
            module.verify(self.output)
        target.unlink()
        with self.assertRaises(ValueError):
            module.verify(self.output)
        target.write_bytes(original)
        extra = self.output / '.env'
        extra.write_text('fixture-only')
        with self.assertRaises(ValueError):
            module.verify(self.output)
        extra.unlink()
        (self.output / 'unexpected').mkdir()
        with self.assertRaises(ValueError):
            module.verify(self.output)

    def test_external_manifest_pin_detects_rewritten_content_and_claims(self):
        receipt = self.build()
        target = self.output / 'automation/managed/worker.py'
        target.write_bytes(target.read_bytes() + b'\n# altered\n')
        manifest = self.output / module.MANIFEST
        document = json.loads(manifest.read_text())
        row = document['files']['automation/managed/worker.py']
        row['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        row['bytes'] = target.stat().st_size
        manifest.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            module.verify(self.output, receipt['manifest_sha256'])
        self.assertFalse(module.verify(self.output)['external_manifest_pin_verified'])

    def test_duplicate_manifest_keys_and_partial_bundle_fail(self):
        self.output.mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):
            module.verify(self.output)
        (self.output / module.MANIFEST).write_text('{"files":{},"files":{}}')
        with self.assertRaises(ValueError):
            module.verify(self.output)


if __name__ == '__main__':
    unittest.main()
