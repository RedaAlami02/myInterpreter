#!/usr/bin/env python3
"""Create or verify a generic, immutable review bundle. Never deploys anything."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
WORKERS = (
    'app_feed', 'app_publish', 'archive_store', 'depth_collect', 'depth_frame',
    'dividend_calendar', 'dividend_collect', 'dividend_feed', 'flush_outbox',
    'enrichment_jobs', 'fundamental_collect', 'fundamental_feed', 'fundamental_frame', 'market_collect',
    'market_frame', 'outbox', 'outbox_bundle', 'probe_source', 'projection_store',
    'price_jobs', 'price_publication', 'price_refresh', 'publish_store', 'run_collection', 'worker',
)
V2_WORKERS = tuple(name for name in WORKERS if name != 'price_publication')
LEGACY_WORKERS = tuple(name for name in V2_WORKERS if name not in {'enrichment_jobs', 'price_jobs', 'price_refresh'})
FUNCTIONS = {
    'private-market-archive': ('archive-gateway', 'gateway'),
    'private-app-publisher': ('app-publisher', 'publisher'),
    'private-projection-publisher': ('projection-publisher', 'publisher'),
}
MIGRATIONS = ('009_private_object_archive', '010_shadow_market_feed',
              '011_admin_market_maintenance', '012_portfolio_valuation',
              '013_projection_publication', '014_manual_trial_leases',
              '015_display_price_fallback', '016_shadow_application_rows',
              '017_subject_archive_slots','018_enrichment_context','019_saved_portfolio_claims')
V2_MIGRATIONS = MIGRATIONS[:-2]
LEGACY_MIGRATIONS = MIGRATIONS[:5]
MAX_FILE = 2 * 1024 * 1024
MAX_BUNDLE = 8 * 1024 * 1024
CONFIG = 'supabase/config.toml'
NOTICE = 'REVIEW_ONLY.md'
MANIFEST = 'MANIFEST.json'
NOTICE_BYTES = b'''# Review bundle only

No deployment, linking, secrets, native recipes, raw data, user records or schedules
are included or activated. Function environment switches remain unset; SQL control
rows start disabled. Review and scoped authorization are still required.

Apply SQL only in the recorded order, after checking installed dependencies and
hosted quotas/timezone/privacy. Do not use this directory as an automatic deploy
trigger. This manifest proves byte integrity when its hash is pinned separately;
a self-contained hash manifest does not authenticate its own origin.

Requirements are pinned in automation/managed/requirements.txt. Worker regression
and SQL acceptance tests run from the original reviewed project, not this runtime
bundle. The three function unit tests are included for offline Deno verification.
'''


def assets(*, legacy=False, version=3):
    selected = {}
    for name in (LEGACY_WORKERS if legacy else V2_WORKERS if version==2 else WORKERS):
        path = f'automation/managed/{name}.py'
        selected[path] = path
    path = 'automation/managed/requirements.txt'
    selected[path] = path
    for function, (folder, main) in FUNCTIONS.items():
        for name in ('index.ts', f'{main}.ts', 'supabase.ts', f'{main}_test.ts'):
            selected[f'supabase/functions/{function}/{name}'] = f'automation/{folder}/{name}'
    for name in (LEGACY_MIGRATIONS if legacy else V2_MIGRATIONS if version==2 else MIGRATIONS):
        path = f'migrations/supabase/{name}.sql'
        selected[path] = path
    return selected


def read_regular(root, relative):
    root = Path(root).resolve()
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts:
        raise ValueError('Invalid review path')
    current = root
    for component in part.parts:
        current /= component
        if current.is_symlink():
            raise ValueError('Symlinks are not review inputs')
    fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise ValueError('Invalid review input size/type')
        data = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
        if len(data) != info.st_size or (info.st_mtime_ns, info.st_size) != (after.st_mtime_ns, after.st_size):
            raise ValueError('Review input changed during reading')
    return data


def validate_contents(contents, deny_literals=()):
    if sum(map(len, contents.values())) > MAX_BUNDLE:
        raise ValueError('Review package exceeds bound')
    local_modules = {Path(name).stem for name in contents if name.startswith('automation/managed/') and name.endswith('.py')}
    for path, body in contents.items():
        text = body.decode('utf-8')
        if any(value and value.encode() in body for value in deny_literals):
            raise ValueError('Private literal in selected review input')
        if re.search(r'\b(?:postgres|postgresql)://[^\s]+|\bsb_secret_[A-Za-z0-9_-]{20,}', text):
            raise ValueError('Credential-shaped literal in review input')
        if path.endswith('.py'):
            tree = ast.parse(text)
            for node in ast.walk(tree):
                imports = ([entry.name for entry in node.names] if isinstance(node, ast.Import)
                           else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                for name in imports:
                    if name.split('.')[0] not in local_modules | sys.stdlib_module_names | {'requests', 'psycopg'}:
                        raise ValueError('Unbundled Python dependency')
        if path.endswith('.ts'):
            if re.search(r'\bimport\s*\(', text):
                raise ValueError('Dynamic imports require separate review')
            imports = re.findall(r'\b(?:from|import)\s+[\'"]([^\'"]+)[\'"]', text)
            for imported in imports:
                if not re.fullmatch(r'\./[a-z_]+\.ts', imported):
                    raise ValueError('Nonlocal TypeScript dependency')
                if str(Path(path).parent / imported[2:]) not in contents:
                    raise ValueError('Missing TypeScript dependency')
    config = tomllib.loads(contents[CONFIG].decode())
    if set(config) != {'project_id', 'functions'} or config['project_id'] != 'myinterpreter-review-only':
        raise ValueError('Invalid review project configuration')
    if set(config['functions']) != set(FUNCTIONS):
        raise ValueError('Unexpected function configuration')
    for name, value in config['functions'].items():
        if value != {'verify_jwt': False, 'entrypoint': f'./functions/{name}/index.ts'}:
            raise ValueError('Unexpected auth/entrypoint configuration')


def selected_contents(root, deny_literals=()):
    contents = {destination: read_regular(root, source) for destination, source in assets().items()}
    configs = []
    for function, (folder, _) in FUNCTIONS.items():
        body = read_regular(root, f'automation/{folder}/config.toml.example')
        parsed = tomllib.loads(body.decode())
        if set(parsed) != {'functions'} or set(parsed['functions']) != {function}:
            raise ValueError('Unexpected source function template')
        configs.append(body)
    contents[CONFIG] = b'project_id = "myinterpreter-review-only"\n\n' + b'\n'.join(configs)
    contents[NOTICE] = NOTICE_BYTES
    validate_contents(contents, deny_literals)
    return contents


def build(root, output, deny_literals=()):
    root = Path(root).resolve()
    target = Path(output).absolute()
    if not target.resolve().is_relative_to(root / 'private') or target.is_symlink():
        raise ValueError('Review bundles must remain under private/')
    # Prepare all bytes first. Never traverse/copy an arbitrary private directory.
    contents = selected_contents(root, deny_literals)
    manifest = {
        'contract': 'app-deployment-review/v3', 'review_only': True,
        'deployment_performed': False, 'schedules_included': False,
        'sql_order': [f'migrations/supabase/{name}.sql' for name in MIGRATIONS],
        'files': {name: {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
                         'source': assets().get(name, 'GENERATED_GENERIC')}
                  for name, body in sorted(contents.items())},
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700)  # Exclusive directory creation; preserve earlier bundles.
    for name, body in sorted(contents.items()):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    # Last file is the completion marker. Partial output is never a valid bundle.
    with (target / MANIFEST).open('xb') as stream:
        stream.write(manifest_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    return verify(target, hashlib.sha256(manifest_bytes).hexdigest(), deny_literals)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest key')
        result[key] = value
    return result


def verify(target, expected_manifest_sha256=None, deny_literals=()):
    target = Path(target).absolute()
    if target.is_symlink():
        raise ValueError('Review bundle must not be a symlink')
    manifest_bytes = read_regular(target, MANIFEST)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if expected_manifest_sha256 is not None and digest != expected_manifest_sha256:
        raise ValueError('Review manifest pin mismatch')
    document = json.loads(manifest_bytes, object_pairs_hook=no_duplicate_keys)
    legacy = document.get('contract') == 'app-deployment-review/v1'
    version = 2 if document.get('contract')=='app-deployment-review/v2' else 3
    selected = assets(legacy=legacy,version=version)
    expected = set(selected) | {CONFIG, NOTICE}
    if (document.get('contract') not in {'app-deployment-review/v1', 'app-deployment-review/v2','app-deployment-review/v3'}
            or document.get('review_only') is not True
            or document.get('deployment_performed') is not False
            or document.get('schedules_included') is not False
            or document.get('sql_order') != [f'migrations/supabase/{name}.sql' for name in (LEGACY_MIGRATIONS if legacy else V2_MIGRATIONS if version==2 else MIGRATIONS)]
            or set(document.get('files', {})) != expected):
        raise ValueError('Invalid review manifest contract')
    actual = set()
    allowed_dirs = {str(parent) for name in expected
                    for parent in Path(name).parents if str(parent) != '.'}
    for path in target.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in review bundle')
        if path.is_file():
            actual.add(str(path.relative_to(target)))
        elif not path.is_dir() or str(path.relative_to(target)) not in allowed_dirs:
            raise ValueError('Unexpected review object')
    if actual != expected | {MANIFEST}:
        raise ValueError('Unexpected or missing review file')
    contents = {}
    for name in sorted(expected):
        body = read_regular(target, name)
        entry = document['files'][name]
        if entry != {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
                     'source': selected.get(name, 'GENERATED_GENERIC')}:
            raise ValueError('Review file hash, size or origin mismatch')
        contents[name] = body
    validate_contents(contents, deny_literals)
    return {'ok': True, 'files_verified': len(expected), 'total_bytes': sum(map(len, contents.values())),
            'manifest_sha256': digest, 'external_manifest_pin_verified': expected_manifest_sha256 is not None,
            'deployment_performed': False, 'activation_ready': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--expected-manifest-sha256')
    args = parser.parse_args(argv)
    try:
        if bool(args.output) == bool(args.verify):
            raise ValueError('Choose exactly one operation')
        # Credentials are compared in memory only; never copied into the bundle.
        from stage_supabase import local_config
        config = local_config(ROOT / '.supabase-migration.env')
        deny = tuple(value for value in config.values() if len(value) >= 12)
        report = (verify(args.verify, args.expected_manifest_sha256, deny)
                  if args.verify else build(ROOT, args.output, deny))
        print(json.dumps(report))
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__, 'deployment_performed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
