#!/usr/bin/env python3
"""Recover empty financial series through a verified saved issuer-name alias.

Retains the original raw capture, keeps the current display name and records the
alias used to query public statements. No database or Appwrite writes occur.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import threading

from capture_nonpersonal_data import make_profile
from refetch_public_data import ROOT, adapter
from stage_supabase import sha256


def run(root):
    manifest=json.loads((root/'manifest.json').read_text())
    baseline={r['name']:r for r in json.loads((ROOT/'backup_live_recovery_20261022/baseline/company.json').read_text())}
    recovered=0
    for entry in list(manifest['files']):
        if not entry['path'].startswith('profiles/'):continue
        path=root/entry['path']
        if sha256(path)!=entry['sha256']:raise ValueError('Capture hash changed')
        original=json.loads(path.read_text())
        profile=original['profile']
        alias=baseline[profile['c_name']].get('ext_name')
        if not alias or alias==profile.get('ext_name') or any(profile['charts'].values()):continue
        module=adapter('onboard_company')
        raw=dict(original['raw_responses'])
        request=module._request
        lock=threading.Lock()
        def cached_get(url):
            kind=url.rsplit('/',2)[-2]
            if url.endswith('/symblinks'):
                return [dict(item,name=alias) if item.get('symbol')==profile['symbol'] else item
                        for item in raw['GET/registry']]
            return raw.get('GET/'+kind)
        def record_request(method,url,what,**kwargs):
            result=request(method,url,what,**kwargs)
            with lock:
                raw['TABLE/'+json.loads(kwargs['data'])['table']]=result
            return result
        module._get=cached_get
        module._request=record_request
        module.reset_failures()
        result=module.fetch_symbol(profile['symbol'])
        captured_at=datetime.now(timezone.utc).isoformat()
        replacement=make_profile(profile['symbol'],profile['c_name'],result,raw,captured_at)
        if not any(replacement['charts'].values()):continue
        replacement['ext_name']=profile['ext_name']
        replacement['financial_statement_issuer_alias']=alias
        replacement['identity_evidence']='same_symbol_and_saved_Appwrite_external_name'
        replacement['prior_capture_sha256']=entry['sha256']
        prior_name='prior_profiles/'+profile['symbol']+'_'+entry['sha256'][:16]+'.json'
        prior=root/prior_name
        prior.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,prior)
        if sha256(prior)!=entry['sha256']:raise ValueError('Prior capture preservation failed')
        manifest['files'].append(dict(entry,path=prior_name))
        payload={'profile':replacement,'raw_responses':raw,
                 'fetch_failure_count':original['fetch_failure_count']+len(module.fetch_failures()),
                 'alias_request_failures':len(module.fetch_failures())}
        data=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode()
        path.write_bytes(data)
        entry['bytes']=len(data);entry['sha256']=hashlib.sha256(data).hexdigest()
        for summary in manifest['profiles']:
            if summary['symbol']==profile['symbol']:
                summary['annual_series_with_values']=sum(bool(v) for v in replacement['charts'].values())
                summary['historical_name_alias_reconciled']=True
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        recovered+=1
    print(json.dumps({'profiles_reconciled_through_saved_identity':recovered,'prior_captures_preserved':True,'database_writes':False}),flush=True)


if __name__=='__main__':
    try:run(ROOT/'backup_live_nonpersonal_20261024')
    except Exception as error:
        print(json.dumps({'ok':False,'error_category':type(error).__name__}),flush=True)
        raise SystemExit(1)
