"""Sanitized operational acceptance; no source identities or account data."""
import json,os,sys
from datetime import datetime,timezone
import requests

FIELDS={'database_bytes','guard_bytes','warning_bytes','market_due','close_due',
        'depth_age_seconds','quotes_age_seconds','depth_complete','quotes_complete',
        'official_batches','valuation_receipts','portfolio_owners','measured_at'}

def issues(snapshot, latest_run, now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(snapshot,dict) or set(snapshot)!=FIELDS:
        raise ValueError('INVALID_HEALTH_SNAPSHOT')
    for key in ['database_bytes','guard_bytes','warning_bytes','official_batches','valuation_receipts','portfolio_owners']:
        if type(snapshot[key]) is not int or snapshot[key]<0:raise ValueError('INVALID_HEALTH_COUNT')
    for key in ['market_due','close_due','depth_complete','quotes_complete']:
        if type(snapshot[key]) is not bool:raise ValueError('INVALID_HEALTH_FLAG')
    for key in ['depth_age_seconds','quotes_age_seconds']:
        if snapshot[key] is not None and (type(snapshot[key]) not in (int,float) or snapshot[key]<0):raise ValueError('INVALID_HEALTH_AGE')
    measured=datetime.fromisoformat(snapshot['measured_at'])
    if measured.tzinfo is None or abs((now-measured).total_seconds())>600:raise ValueError('STALE_HEALTH_SNAPSHOT')
    found=[]
    if snapshot['guard_bytes']<=0:raise ValueError('INVALID_STORAGE_GUARD')
    if snapshot['guard_bytes']-snapshot['database_bytes']<=snapshot['warning_bytes']:found.append('STORAGE_HEADROOM_LOW')
    if snapshot['market_due']:
        for kind,max_age in [('depth',900),('quotes',1800)]:
            age=snapshot[kind+'_age_seconds']
            if age is None or age>max_age:found.append(kind.upper()+'_MISSING_OR_STALE')
            if not snapshot[kind+'_complete']:found.append(kind.upper()+'_COVERAGE_INCOMPLETE')
    if snapshot['close_due']:
        if snapshot['official_batches']==0:found.append('OFFICIAL_CLOSE_UNVERIFIED')
        elif snapshot['portfolio_owners']>0 and snapshot['valuation_receipts']==0:found.append('PORTFOLIO_VALUATIONS_UNVERIFIED')
    if latest_run is None:found.append('COLLECTION_RUN_MISSING')
    elif latest_run.get('status')=='completed' and latest_run.get('conclusion')!='success':found.append('COLLECTION_RUN_FAILED')
    return found

def main():
    try:
        raw=os.environ['HEALTH_SNAPSHOT']
        if len(raw)>4096:raise ValueError('HEALTH_SNAPSHOT_LIMIT')
        snapshot=json.loads(raw)
        session=requests.Session();session.trust_env=False
        response=session.get('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/workflows/collect-durable.yml/runs',params={'per_page':1},headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},timeout=(8,20),allow_redirects=False)
        if response.status_code!=200:raise ValueError('COLLECTION_HISTORY_UNAVAILABLE')
        runs=response.json()['workflow_runs'];found=issues(snapshot,runs[0] if runs else None)
        print(json.dumps({'status':'ATTENTION_REQUIRED' if found else 'HEALTHY','issues':found,'database_bytes':snapshot['database_bytes'],'headroom_bytes':snapshot['guard_bytes']-snapshot['database_bytes']}))
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a') as f:
                f.write('Operational checks: '+('attention required' if found else 'passed')+'\n\n')
                for code in found:f.write('- '+code+'\n')
                f.write('\nNo source identities, credentials or portfolio details are included.\n')
        return 1 if found else 0
    except Exception:
        print(json.dumps({'status':'ATTENTION_REQUIRED','issues':['MONITOR_CHECK_FAILED']}));return 1

if __name__=='__main__':raise SystemExit(main())
