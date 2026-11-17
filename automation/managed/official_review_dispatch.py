"""Dispatch an isolated review only for durable official-close candidates."""
import hashlib,json,os,re
from pathlib import Path

import requests
import cloud_state
import runner_checkpoint
import worker


def dispatch(api, branch, inputs):
    response=api.session.post('https://api.github.com/repos/'+api.repo+'/actions/workflows/official-review.yml/dispatches',json={
        'ref':branch,'inputs':inputs},timeout=(10,25),allow_redirects=False)
    if response.status_code not in (200,204):
        raise worker.AcquisitionError('REVIEW_DISPATCH_FAILED')


def review_status(document_sha):
    if not re.fullmatch('[a-f0-9]{64}',document_sha):raise worker.AcquisitionError('INVALID_REVIEW_IDENTITY')
    api=cloud_state.GitHub()
    try:
        runs=api.call('/actions/workflows/official-review.yml/runs',params={'per_page':30,'branch':os.environ['GITHUB_REF_NAME']})['workflow_runs']
    except Exception:
        return 'UNKNOWN'
    for run in runs:
        if run.get('display_title')=='Official close review '+document_sha:
            if run.get('status')=='completed' and run.get('conclusion')!='success':return 'FAILED'
            return 'RUNNING_OR_COMPLETE'
    return 'UNKNOWN'


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True);args=parser.parse_args()
    try:
        root=runner_checkpoint.private_directory(args.state);spool=runner_checkpoint.queue(root,'official_close')
        candidates=[]
        for path in spool.entries():
            value=worker.unpacked(path.name[:64],spool.read(path),max_batch=8*1024*1024)
            if value.get('document') is not None:candidates.append(hashlib.sha256(value['document'].encode()).hexdigest())
        if not candidates:print(json.dumps({'status':'NO_CANDIDATE'}));return 0
        if len(candidates)!=1:raise worker.AcquisitionError('REVIEW_REQUIRES_ONE_CANDIDATE')
        document_sha=candidates[0]
        if review_status(document_sha)=='RUNNING_OR_COMPLETE':print(json.dumps({'status':'REVIEW_ALREADY_DISPATCHED'}));return 0
        api=cloud_state.GitHub();run_id=int(os.environ['GITHUB_RUN_ID']);current=cloud_state.current(api,run_id)
        artifact_id=int(os.environ['ARTIFACT_ID']);pin=os.environ['STATE_PIN']
        if not re.fullmatch('[a-f0-9]{64}',pin):raise worker.AcquisitionError('INVALID_CHECKPOINT_PIN')
        artifact=api.call('/actions/artifacts/'+str(artifact_id))
        if artifact.get('name')!=f'{cloud_state.PREFIX}{run_id}-1-{pin}' or artifact.get('workflow_run',{}).get('id')!=run_id:
            raise worker.AcquisitionError('REVIEW_CHECKPOINT_DIFFERS')
        dispatch(api,current['head_branch'],{'checkpoint_run_id':str(run_id),'artifact_id':str(artifact_id),
            'checkpoint_sha256':pin,'document_sha256':document_sha})
        print(json.dumps({'status':'REVIEW_DISPATCHED'}));return 0
    except Exception as error:
        print(json.dumps({'status':'FAILED','code':str(error) if isinstance(error,worker.AcquisitionError) else 'REVIEW_DISPATCH_FAILED'}));return 1


if __name__=='__main__':raise SystemExit(main())
