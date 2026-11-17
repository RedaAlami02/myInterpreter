#!/usr/bin/env python3
"""Private Actions checkpoint chain. No market requests or production activation."""
import argparse
import json
import os
from pathlib import Path
import re
import stat

import requests

import runner_checkpoint as checkpoint
from worker import AcquisitionError

PREFIX = 'private-state-v1-'
NAME = re.compile(r'private-state-v1-([1-9][0-9]*)-1-([a-f0-9]{64})')
WORKFLOW = '.github/workflows/collect-durable.yml'
MAX_ARTIFACT = 65 * 1024 * 1024
BUDGET = 3 * MAX_ARTIFACT
# Incident review: these two completed runs have no jobs, checks or artifacts.
# Scope this exception to their exact immutable run IDs, never all empty jobs.
NO_JOB_INCIDENT_RUNS = frozenset({42671126097, 42671914337})


def positive(value):
    if type(value) is not int or value <= 0:
        raise AcquisitionError('INVALID_CLOUD_STATE_METADATA')
    return value


class GitHub:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repo):
            raise AcquisitionError('INVALID_REPOSITORY')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(Authorization='Bearer ' + os.environ['GH_TOKEN'],
            Accept='application/vnd.github+json', **{'X-GitHub-Api-Version': '2026-03-10'})

    def call(self, path, *, method='GET', params=None):
        try:
            with self.session.request(method, 'https://api.github.com/repos/' + self.repo + path,
                    params=params, timeout=(10, 25), allow_redirects=False, stream=True) as response:
                if response.status_code != (204 if method == 'DELETE' else 200):
                    raise AcquisitionError('CLOUD_STATE_API_REJECTED')
                if method == 'DELETE':
                    return None
                body = bytearray()
                for part in response.iter_content(8192):
                    body.extend(part)
                    if len(body) > 2 * 1024 * 1024:
                        raise AcquisitionError('CLOUD_STATE_API_LIMIT')
                return json.loads(body)
        except (requests.RequestException, ValueError):
            raise AcquisitionError('CLOUD_STATE_API_FAILED') from None


def pages(api, path, key, params=None):
    result = []
    for page in range(1, 11):
        value = api.call(path, params={**(params or {}), 'per_page': 100, 'page': page})
        rows = value.get(key)
        if not isinstance(rows, list) or len(rows) > 100:
            raise AcquisitionError('CLOUD_STATE_API_INVALID')
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise AcquisitionError('CLOUD_STATE_HISTORY_LIMIT')


def current(api, run_id):
    repo = api.call('')
    run = api.call('/actions/runs/' + str(positive(run_id)))
    if repo.get('private') is not True or run.get('head_branch') != repo.get('default_branch') or run.get('path') != WORKFLOW or (run.get('event') != 'workflow_dispatch' and not (run.get('event') == 'schedule' and os.environ.get('APP_SCHEDULE_CONTRACT') == 'recurring-casablanca/v1')) or run.get('run_attempt') != 1 or run.get('id') != run_id:
        raise AcquisitionError('CLOUD_STATE_REQUIRES_PRIVATE_DEFAULT_BRANCH_FIRST_ATTEMPT')
    positive(run['workflow_id'])
    positive(run['run_number'])
    return run


def checkpoint_artifacts(api):
    return [v for v in pages(api, '/actions/artifacts', 'artifacts')
            if isinstance(v.get('name'), str) and v['name'].startswith(PREFIX)]


def select(api, run_id, *, bootstrap=False):
    run = current(api, run_id)
    all_runs = pages(api, '/actions/workflows/' + str(run['workflow_id']) + '/runs',
                     'workflow_runs', {'branch': run['head_branch']})
    previous = None
    for candidate in sorted(all_runs, key=lambda v: positive(v['run_number']), reverse=True):
        if candidate['id'] == run_id or candidate.get('conclusion') == 'skipped':
            continue
        # Job-level guards can produce a successful workflow whose only job
        # was skipped. Only this exact no-execution case is safe to bypass.
        if candidate.get('status') == 'completed' and candidate.get('run_attempt') == 1:
            jobs = pages(api, '/actions/runs/' + str(positive(candidate['id'])) + '/attempts/1/jobs', 'jobs')
            if candidate['id'] == 43285107945 and candidate.get('conclusion') == 'cancelled' and len(jobs) == 1:
                outcomes = {step.get('name'): step.get('conclusion') for step in jobs[0].get('steps', [])}
                if all(outcomes.get(name) == 'skipped' for name in [
                        'Restore or explicitly bootstrap private queues',
                        'Run existing collector with bounded execution',
                        'Checkpoint even after collector failure']):
                    continue
            if not jobs and candidate['id'] in NO_JOB_INCIDENT_RUNS and candidate.get('conclusion') == 'failure':
                missing = pages(api, '/actions/runs/' + str(candidate['id']) + '/artifacts', 'artifacts')
                if not missing:
                    continue
            if len(jobs) == 1 and jobs[0].get('name') == 'collect' and jobs[0].get('conclusion') == 'skipped':
                continue
            # A failed selector cannot mutate queues: every subsequent step
            # must explicitly be skipped. Never bypass a collector failure.
            if len(jobs) == 1 and jobs[0].get('name') == 'collect':
                steps = jobs[0].get('steps', [])
                selectors = [i for i, step in enumerate(steps)
                             if step.get('name') == 'Select exact preceding checkpoint']
                if len(selectors) == 1:
                    index = selectors[0]
                    later = [step for step in steps[index + 1:]
                             if not step.get('name', '').startswith('Post ')
                             and step.get('name') != 'Complete job']
                    if (steps[index].get('conclusion') == 'failure'
                            and later
                            and {'Restore or explicitly bootstrap private queues',
                                 'Run existing collector with bounded execution',
                                 'Checkpoint even after collector failure'}
                            <= {step.get('name') for step in later}
                            and all(step.get('conclusion') == 'skipped' for step in later)):
                        continue
        if candidate['run_number'] >= run['run_number']:
            raise AcquisitionError('CLOUD_STATE_STALE_RUN')
        previous = candidate
        break
    artifacts = checkpoint_artifacts(api)
    used = sum(positive(v['size_in_bytes']) for v in artifacts if not v.get('expired'))
    if used + MAX_ARTIFACT > BUDGET:
        raise AcquisitionError('CLOUD_STATE_STORAGE_BUDGET')
    if previous is None:
        if not bootstrap or artifacts:
            raise AcquisitionError('CLOUD_STATE_EXPLICIT_EMPTY_BOOTSTRAP_REQUIRED')
        return {'bootstrap': 'true', 'previous_run_id': '0', 'artifact_id': '0', 'sha256': ''}
    if bootstrap or previous.get('status') != 'completed' or previous.get('run_attempt') != 1:
        raise AcquisitionError('CLOUD_STATE_PREDECESSOR_NOT_USABLE')
    values = pages(api, '/actions/runs/' + str(previous['id']) + '/artifacts', 'artifacts')
    candidates = [v for v in values if isinstance(v.get('name'), str) and v['name'].startswith(PREFIX)]
    if len(candidates) != 1:
        raise AcquisitionError('CLOUD_STATE_LATEST_CHECKPOINT_MISSING')
    artifact = candidates[0]
    match = NAME.fullmatch(artifact['name'])
    if not match or int(match[1]) != previous['id'] or artifact.get('expired') is not False or not 0 < positive(artifact['size_in_bytes']) <= MAX_ARTIFACT:
        raise AcquisitionError('CLOUD_STATE_LATEST_CHECKPOINT_INVALID')
    return {'bootstrap': 'false', 'previous_run_id': str(previous['id']),
            'artifact_id': str(positive(artifact['id'])), 'sha256': match[2]}


def downloaded(directory):
    """Artifacts drop POSIX modes. Tighten only fixed regular checkpoint files."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise AcquisitionError('CLOUD_STATE_DOWNLOAD_INVALID')
    allowed = {checkpoint.MANIFEST} | {name + '.zip' for name in checkpoint.ALL_CHANNELS}
    for path in directory.iterdir():
        info = path.lstat()
        if path.name not in allowed or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > MAX_ARTIFACT:
            raise AcquisitionError('CLOUD_STATE_DOWNLOAD_INVALID')
        os.chmod(path, 0o600)
    os.chmod(directory, 0o700)


def verify_download(directory, state, pin):
    downloaded(directory)
    return checkpoint.restore(directory, state, expected_sha256=pin)


def prune(api, run_id, artifact_id, pin, previous_run_id):
    run = current(api, run_id)
    artifact = api.call('/actions/artifacts/' + str(positive(artifact_id)))
    if artifact.get('name') != f'{PREFIX}{run_id}-1-{pin}' or artifact.get('expired') is not False or artifact.get('workflow_run', {}).get('id') != run_id:
        raise AcquisitionError('CLOUD_STATE_UPLOADED_METADATA_MISMATCH')
    removed = 0
    for old in checkpoint_artifacts(api):
        match = NAME.fullmatch(old['name'])
        owner = old.get('workflow_run', {}).get('id')
        if not match or owner != int(match[1]) or owner in {run_id, previous_run_id}:
            continue
        older_run = api.call('/actions/runs/' + str(positive(owner)))
        if older_run.get('workflow_id') != run['workflow_id'] or older_run.get('head_branch') != run['head_branch'] or older_run.get('status') != 'completed' or positive(older_run['run_number']) >= run['run_number']:
            continue
        api.call('/actions/artifacts/' + str(positive(old['id'])), method='DELETE')
        removed += 1
    return {'status': 'VERIFIED_AND_RETAINED', 'superseded_checkpoints_removed': removed}


def emit(result):
    # Every output is a fixed status, integer or digest; never config/identity.
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            for key, value in result.items():
                stream.write(f'{key}={value}\n')
    print(json.dumps(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    choosing = sub.add_parser('select')
    choosing.add_argument('--bootstrap', action='store_true')
    packing = sub.add_parser('pack')
    packing.add_argument('--state', type=Path, required=True)
    packing.add_argument('--output', type=Path, required=True)
    restoring = sub.add_parser('restore')
    restoring.add_argument('--checkpoint', type=Path, required=True)
    restoring.add_argument('--state', type=Path, required=True)
    restoring.add_argument('--sha256', required=True)
    finishing = sub.add_parser('finish')
    finishing.add_argument('--checkpoint', type=Path, required=True)
    finishing.add_argument('--verify-state', type=Path, required=True)
    finishing.add_argument('--sha256', required=True)
    finishing.add_argument('--artifact-id', type=int, required=True)
    finishing.add_argument('--previous-run-id', type=int, required=True)
    args = parser.parse_args(argv)
    previous_mask = os.umask(0o077)
    try:
        if args.command == 'restore':
            result = verify_download(args.checkpoint, args.state, args.sha256)
        else:
            run_id = positive(int(os.environ['GITHUB_RUN_ID']))
            if args.command == 'select':
                result = select(GitHub(), run_id, bootstrap=args.bootstrap)
            elif args.command == 'pack':
                result = checkpoint.pack(args.state, args.output)
                result['artifact_name'] = f"{PREFIX}{run_id}-1-{result['manifest_sha256']}"
            else:
                verify_download(args.checkpoint, args.verify_state, args.sha256)
                result = prune(GitHub(), run_id, args.artifact_id, args.sha256, args.previous_run_id)
        emit(result)
        return 0
    except Exception as error:
        print(json.dumps({'status': 'FAILED', 'code': str(error) if isinstance(error, AcquisitionError) else 'CLOUD_STATE_FAILED'}))
        return 1
    finally:
        os.umask(previous_mask)


if __name__ == '__main__':
    raise SystemExit(main())
