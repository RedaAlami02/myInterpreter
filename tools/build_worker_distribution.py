#!/usr/bin/env python3
"""Build a fixed private-worker distribution; never publishes or activates it."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import yaml

import build_deployment_review as review

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('worker_verification', ROOT/'automation/managed/verify_worker.py')
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)
EXTRA = ('runner_checkpoint', 'cloud_state', 'cloud_collect', 'verify_worker', 'checkpoint_smoke',
         'official_close', 'schedule_plan', 'receipt_history', 'recurring_schedule', 'official_close_collect', 'official_close_verify', 'official_review_dispatch', 'official_review_target', 'health_check')
WORKFLOWS = ('probe', 'source-probe', 'verify', 'collect', 'collect-durable', 'official-review', 'health')


def selection():
    files = {name+'.py': 'automation/managed/'+name+'.py' for name in (*review.WORKERS, *EXTRA)}
    files['requirements.txt'] = 'automation/managed/requirements.txt'
    for name in (*verification.SUITES, *verification.HELPERS):
        files['tests/'+name+'.py'] = 'automation/managed/tests/'+name+'.py'
    for name in WORKFLOWS:
        files[f'.github/workflows/{name}.yml'] = f'automation/managed/.github/workflows/{name}.yml'
    for name, (folder, main) in review.FUNCTIONS.items():
        target = 'gateway' if folder == 'archive-gateway' else folder
        for filename in (main+'.ts', main+'_test.ts', 'supabase.ts'):
            files[target+'/'+filename] = 'automation/'+folder+'/'+filename
    for filename in ['handler.ts','handler_test.ts','supabase.ts']:
        files['official-close-publisher/'+filename]='automation/official-close-publisher/'+filename
    return files


def validate(contents, deny=()):
    modules = {Path(path).stem for path in contents if path.endswith('.py')}
    for path, body in contents.items():
        if any(value and value.lower().encode() in body.lower() for value in deny):
            raise ValueError('Private literal in worker distribution')
        if path.endswith('.py'):
            for node in ast.walk(ast.parse(body)):
                imports = ([v.name for v in node.names] if isinstance(node, ast.Import)
                           else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                if any(v.split('.')[0] not in modules | sys.stdlib_module_names | {'requests','psycopg'} for v in imports):
                    raise ValueError('Missing worker dependency')
        elif path.endswith('.yml'):
            workflow = yaml.safe_load(body)
            triggers = workflow.get('on', workflow.get(True))
            if not isinstance(triggers, dict):
                raise ValueError('Invalid worker triggers')
            if set(triggers) != {'workflow_dispatch'}:
                expected = [{'cron':'*/5 8-18 * * 1-5'}, {'cron':'5 6,7 * * 1'}]
                if (path != '.github/workflows/collect-durable.yml'
                    or set(triggers) != {'workflow_dispatch','schedule'}
                    or triggers['schedule'] != expected
                    or body.count(b'  schedule:') != 1
                    or workflow.get('env',{}).get('APP_SCHEDULE_CONTRACT') != 'recurring-casablanca/v1'
                    or 'APP_RECURRING_SCHEDULE_ENABLED' not in workflow['jobs']['collect'].get('if','')):
                    raise ValueError('Unreviewed recurring worker triggers')
            financial_secrets=('APP_OFFICIAL_ATTESTATION_KEY','APP_OFFICIAL_CLOSE_TOKEN','APP_OFFICIAL_REVIEW_CONFIG')
            if path != '.github/workflows/official-review.yml' and any(key.encode() in body for key in financial_secrets):
                raise ValueError('Financial credentials outside protected review')
            if path == '.github/workflows/official-review.yml':
                jobs=workflow.get('jobs',{})
                if (set(jobs)!={'verify'} or jobs['verify'].get('environment')!='official-close-review'
                    or 'github.event.repository.private' not in jobs['verify'].get('if','')
                    or 'github.event.repository.default_branch' not in jobs['verify'].get('if','')
                    or workflow.get('permissions')!={'contents':'read','actions':'read'}):
                    raise ValueError('Protected independent review required')
            for job in workflow['jobs'].values():
                if job.get('runs-on') not in {'ubuntu-latest', 'ubuntu-slim'} or job.get('timeout-minutes', 100) > 10:
                    raise ValueError('Unexpected worker runtime budget')
                for step in job['steps']:
                    if 'uses' in step:
                        import re
                        if not re.fullmatch(r'[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+@[a-f0-9]{40}', step['uses']):
                            raise ValueError('Action must be commit-pinned')
        elif path.endswith('.ts'):
            import re
            for imported in re.findall(r'\bfrom\s+[\'"]([^\'"]+)[\'"]', body.decode()):
                if not re.fullmatch(r'\./[a-z_]+\.ts', imported) or str(Path(path).parent/imported[2:]) not in contents:
                    raise ValueError('Unbundled boundary dependency')


def build(root, output, deny=()):
    root, output = Path(root).resolve(), Path(output).absolute()
    if output.is_symlink() or not output.resolve().is_relative_to(root/'private'):
        raise ValueError('Worker packages must stay private')
    contents = {target: review.read_regular(root, source) for target, source in selection().items()}
    contents['README.md'] = b'''# Private managed workers

Versioned recurring application collection and synthetic acceptance. Live collection
requires separately approved backend controls, scoped credentials, verified
shared artifact headroom and APP_DURABLE_COLLECTION_ENABLED=true plus
APP_CHECKPOINT_HEADROOM_VERIFIED=true. Both gates remain unset/off at publication.
The old collection entry is disabled. Recurring schedules also require
APP_RECURRING_SCHEDULE_ENABLED=true and matching enabled server policy.

Run python3 verify_worker.py for the standalone synthetic suites. Main-project
legacy/source parity, SQL, PHP and Flutter acceptance are separate, not replaced.
No recipe, provider identity, account data or production credential is bundled.
'''
    validate(contents, deny)
    manifest = {'contract':'private-worker-distribution/v2', 'files':{
        name:{'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
        for name,body in sorted(contents.items())}, 'source_requests':0,'schedules_enabled':False}
    body = (json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, payload in {**contents,'DISTRIBUTION.json':body}.items():
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return {'files':len(contents),'manifest_sha256':hashlib.sha256(body).hexdigest(),
            'source_requests':0,'schedules_enabled':False,'published':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(ROOT,args.output)))
