#!/usr/bin/env python3
"""Prepare a private, pinned quote-only trial proposal. No network or deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import build_deployment_review as runtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
import app_feed
import market_collect
import worker

GATE = 'migrations/supabase/014_manual_trial_leases.sql'
FILES = {GATE, 'market-config.private.json', 'company-mapping.private.json', 'publish-profile.private.json'}


def private_read(root, path):
    path = Path(path).absolute()
    relative = path.relative_to(Path(root).absolute() / 'private')
    return runtime.read_regular(Path(root) / 'private', str(relative))


def write_exclusive(path, body):
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def verify(output, pin):
    output = Path(output)
    if output.is_symlink() or not isinstance(pin, str) or not re.fullmatch('[a-f0-9]{64}', pin):
        raise ValueError('External proposal pin required')
    body = runtime.read_regular(output, 'PLAN.private.json')
    if hashlib.sha256(body).hexdigest() != pin:
        raise ValueError('Proposal pin mismatch')
    plan = json.loads(body, object_pairs_hook=runtime.no_duplicate_keys)
    if plan.get('contract') != 'manual-quote-trial-proposal/v1' or plan.get('authorized') is not False or set(plan.get('files', {})) != FILES:
        raise ValueError('Invalid proposal contract')
    actual = set()
    directories = {str(parent) for name in FILES for parent in Path(name).parents if str(parent) != '.'}
    for path in output.rglob('*'):
        if path.is_symlink():
            raise ValueError('Proposal symlink refused')
        if path.is_file():
            actual.add(str(path.relative_to(output)))
        elif not path.is_dir() or str(path.relative_to(output)) not in directories:
            raise ValueError('Unexpected proposal object')
    if actual != FILES | {'PLAN.private.json'}:
        raise ValueError('Unexpected proposal files')
    for name, entry in plan['files'].items():
        content = runtime.read_regular(output, name)
        if entry != {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}:
            raise ValueError('Proposal content mismatch')
    return {'verified': True, 'authorized': False, 'plan_sha256': pin, 'files_verified': len(FILES)}


def build(root, output, config_path, mapping_path, bundle, pin):
    root, output = Path(root).absolute(), Path(output).absolute()
    if output.is_symlink() or not output.resolve().is_relative_to((root / 'private').resolve()):
        raise ValueError('Trial proposals must remain private')
    if output.exists():
        raise FileExistsError('Trial proposal already exists')
    receipt = runtime.verify(bundle, pin)
    config_bytes, mapping_bytes = private_read(root, config_path), private_read(root, mapping_path)
    config, mapping = worker.decode(config_bytes), worker.decode(mapping_bytes)
    market_collect.validate(config)
    app_feed.validate_mapping(mapping, config)
    if len(mapping['indices']) != 1 or mapping['indices'][0]['asset_key'] != 'index:MASI':
        raise ValueError('Exact main-index identity required')
    # A proposal must not accidentally carry credentials from an enriched config.
    if set(config) != {'contract', 'provider_namespace', 'recipe', 'archive_project_reference'}:
        raise ValueError('Unexpected private configuration fields')
    manifest_bytes = runtime.read_regular(bundle, runtime.MANIFEST)
    manifest = json.loads(manifest_bytes)
    for destination, entry in manifest['files'].items():
        source = entry['source']
        if source != 'GENERATED_GENERIC' and runtime.read_regular(root, source) != runtime.read_regular(bundle, destination):
            raise ValueError('Current runtime differs from pinned review')
    profile = {'contract': 'private-app-publish/v1',
        'provider_namespace': config['provider_namespace'], 'mapping': mapping,
        'mapping_sha256': app_feed.fingerprint(mapping),
        'recipe_sha256': app_feed.fingerprint(config['recipe'])}
    contents = {GATE: runtime.read_regular(root, GATE),
        'market-config.private.json': config_bytes,
        'company-mapping.private.json': mapping_bytes,
        'publish-profile.private.json': (app_feed.canonical(profile) + '\n').encode()}
    plan = {'contract': 'manual-quote-trial-proposal/v1', 'authorized': False,
        'runtime_manifest_sha256': receipt['manifest_sha256'],
        'provider_namespace': config['provider_namespace'],
        'mapping_sha256': profile['mapping_sha256'], 'recipe_sha256': profile['recipe_sha256'],
        'mode': 'SHADOW_ONLY', 'lease_seconds': 300, 'max_objects': 1, 'max_bytes': 8388608,
        'capabilities': ['archive', 'shadow_feed'], 'kinds': ['quotes'],
        'logical_captures': 1, 'source_request_attempts_max': 2, 'automatic_source_retry': True,
        'capture_policy': 'GENUINE_CURRENT_ONLY', 'stocks': len(mapping['stocks']), 'indices': 1,
        'prediction_eligible': False, 'portfolio_valuation_eligible': False,
        'schedules': False, 'application_table_writes': False,
        'projection_activation': False, 'application_reader_activation': False,
        'required_outer_statement_timeout_ms': 20000,
        'files': {name: {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
                  for name, body in sorted(contents.items())}}
    body = (app_feed.canonical(plan) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    for name, value in contents.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_exclusive(path, value)
    write_exclusive(output / 'PLAN.private.json', body)  # Last file marks completion.
    verify(output, hashlib.sha256(body).hexdigest())
    return {'prepared': True, 'authorized': False, 'deployment_performed': False,
        'plan_sha256': hashlib.sha256(body).hexdigest(), 'stocks': plan['stocks'], 'indices': 1,
        'max_objects': 1, 'lease_seconds': 300, 'runtime_pin_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'mapping', 'runtime-bundle', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--runtime-pin', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(ROOT, args.output, args.config, args.mapping,
            args.runtime_bundle, args.runtime_pin)))
        return 0
    except Exception:
        # Native config validation failures may contain private identities.
        print(json.dumps({'prepared': False, 'code': 'PRIVATE_TRIAL_PREPARATION_FAILED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
