#!/usr/bin/env python3
"""Hosted checkpoint transport acceptance using synthetic bytes only."""
import argparse
import os
from pathlib import Path

import cloud_state
import runner_checkpoint
import worker

PREFIX = 'synthetic-checkpoint-'


def fixture(channel):
    return {'contract': 'synthetic-checkpoint-test/v1', 'channel': channel, 'real_observations': False}


def create(state, output, run_id):
    runner_checkpoint.private_directory(state, create=True)
    for channel in runner_checkpoint.CHANNELS:
        key, body = worker.packed(fixture(channel))
        runner_checkpoint.queue(state, channel).put(key, body)
    result = runner_checkpoint.pack(state, output)
    result['artifact_name'] = f"{PREFIX}{cloud_state.positive(run_id)}-{result['manifest_sha256']}"
    return result


def finish(api, directory, restored, pin, artifact_id, run_id):
    result = cloud_state.verify_download(directory, restored, pin)
    for channel in runner_checkpoint.CHANNELS:
        spool = runner_checkpoint.queue(restored, channel)
        paths = spool.entries()
        if len(paths) != 1 or worker.unpacked(paths[0].name[:64], spool.read(paths[0])) != fixture(channel):
            raise worker.AcquisitionError('SYNTHETIC_CHECKPOINT_CHANGED')
    repo = api.call('')
    run = api.call('/actions/runs/' + str(cloud_state.positive(run_id)))
    artifact = api.call('/actions/artifacts/' + str(cloud_state.positive(artifact_id)))
    if repo.get('private') is not True or run.get('path') != '.github/workflows/verify.yml' or run.get('event') != 'workflow_dispatch' or artifact.get('name') != f'{PREFIX}{run_id}-{pin}' or artifact.get('workflow_run', {}).get('id') != run_id:
        raise worker.AcquisitionError('SYNTHETIC_CHECKPOINT_RECEIPT_INVALID')
    # Only this exact synthetic artifact; never a production retry checkpoint.
    api.call('/actions/artifacts/' + str(artifact_id), method='DELETE')
    return {**result, 'synthetic_artifact_removed': True, 'source_requests': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    creating = commands.add_parser('create')
    creating.add_argument('--state', type=Path, required=True)
    creating.add_argument('--output', type=Path, required=True)
    finishing = commands.add_parser('finish')
    finishing.add_argument('--checkpoint', type=Path, required=True)
    finishing.add_argument('--state', type=Path, required=True)
    finishing.add_argument('--sha256', required=True)
    finishing.add_argument('--artifact-id', type=int, required=True)
    args = parser.parse_args(argv)
    previous = os.umask(0o077)
    try:
        run_id = cloud_state.positive(int(os.environ['GITHUB_RUN_ID']))
        result = (create(args.state, args.output, run_id) if args.command == 'create' else
                  finish(cloud_state.GitHub(), args.checkpoint, args.state, args.sha256, args.artifact_id, run_id))
        cloud_state.emit(result)
        return 0
    except Exception as error:
        import json
        print(json.dumps({'status': 'FAILED', 'code': str(error) if isinstance(error, worker.AcquisitionError) else 'SYNTHETIC_CHECKPOINT_FAILED'}))
        return 1
    finally:
        os.umask(previous)


if __name__ == '__main__': raise SystemExit(main())
