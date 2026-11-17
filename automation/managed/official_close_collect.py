"""Private daily report acquisition and automatic official-close handoff.

No account identities/passwords are inputs. The server derives eligible owners.
Raw receipts and pending intent survive runner restarts without refetching them.
"""
from datetime import datetime,timezone
import hashlib,json,os,re,tempfile
from pathlib import Path
from urllib.parse import urlsplit

import requests
import official_close
from outbox import Outbox
import worker,runner_checkpoint

CONTRACT='private-official-close-job/v1'
MAX_JOB=8*1024*1024


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def validate(config):
    keys={'contract','provider_namespace','archive_project_reference','worker_repository',
          'url_template','ca_pem','identities','parser_sha256','source_policy_sha256'}
    if not isinstance(config,dict) or set(config)!=keys:
        raise worker.AcquisitionError('INVALID_OFFICIAL_CLOSE_CONFIG')
    material={k:v for k,v in config.items() if k!='source_policy_sha256'}
    if hashlib.sha256(canonical(material).encode()).hexdigest()!=config['source_policy_sha256']:
        raise worker.AcquisitionError('OFFICIAL_POLICY_PIN_DIFFERS')
    if (config.get('contract')!='private-official-close-config/v1'
        or not re.fullmatch('feed_[a-f0-9]{16}',config.get('provider_namespace',''))
        or not re.fullmatch('[a-f0-9]{64}',config.get('source_policy_sha256',''))
        or not re.fullmatch('[a-f0-9]{64}',config.get('parser_sha256',''))
        or not isinstance(config.get('identities'),list)):
        raise worker.AcquisitionError('INVALID_OFFICIAL_CLOSE_CONFIG')
    if hashlib.sha256(Path(official_close.__file__).read_bytes()).hexdigest()!=config['parser_sha256']:
        raise worker.AcquisitionError('OFFICIAL_PARSER_PIN_DIFFERS')
    seen=[set(),set(),set()]
    for item in config['identities']:
        if set(item)!={'company_id','c_name','symbol','isin'} or not re.fullmatch('MA[0-9]{10}',item['isin']):
            raise worker.AcquisitionError('INVALID_OFFICIAL_IDENTITIES')
        for values,key in zip(seen,['company_id','symbol','isin']):
            if not isinstance(item[key],str) or not item[key] or item[key] in values:
                raise worker.AcquisitionError('AMBIGUOUS_OFFICIAL_IDENTITIES')
            values.add(item[key])
    url=urlsplit(config['url_template'])
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise worker.AcquisitionError('INVALID_OFFICIAL_ENDPOINT')
    if not isinstance(config.get('ca_pem'),str) or 'BEGIN CERTIFICATE' not in config['ca_pem']:
        raise worker.AcquisitionError('OFFICIAL_TLS_ROOTS_REQUIRED')


def fetch_report(config,day):
    compact=day.replace('-','')
    url=config['url_template'].format(ym=day[:7],ymd=compact)
    session=requests.Session();session.trust_env=False
    with tempfile.TemporaryDirectory(prefix='private-official-tls-') as folder:
        ca=Path(folder)/'roots.pem'
        ca.write_text(Path(requests.certs.where()).read_text()+'\n'+config['ca_pem']);ca.chmod(0o600)
        with session.get(url,verify=str(ca),timeout=(8,25),allow_redirects=False,stream=True) as response:
            raw=bytearray()
            for block in response.iter_content(16384):
                raw.extend(block)
                if len(raw)>3*1024*1024:raise worker.AcquisitionError('OFFICIAL_RESPONSE_LIMIT')
            return bytes(raw),datetime.now(timezone.utc),response.status_code


def build(config,raw,captured,slot,status,*,parser=official_close.parse_pdf):
    day=captured.astimezone(worker.ZONE).date().isoformat();error=None;parsed=None
    try:
        if status!=200:raise worker.AcquisitionError('OFFICIAL_HTTP_UNAVAILABLE')
        parsed=parser(raw,day)
    except Exception:
        error='OFFICIAL_REPORT_NOT_USABLE'
    raw_sha=hashlib.sha256(raw).hexdigest()
    envelope={'contract':'private-acquisition/v2','provider_namespace':config['provider_namespace'],
        'kind':'quotes','slot':slot,'completed_at':datetime.now(timezone.utc).isoformat(),
        'execution':'CURRENT_ACQUISITION','completeness':'COMPLETE' if parsed else 'INCOMPLETE',
        'authority':'UNPROMOTED','prediction_eligible':False,'parser_sha256':config['parser_sha256'],
        'errors':[] if parsed else [{'code':error}],
        'captures':[{'request_index':0,'capture_id':hashlib.sha256(json.dumps(
            [config['provider_namespace'],raw_sha,captured.isoformat()],separators=(',',':')).encode()).hexdigest(),
                     'received_at':captured.isoformat(),'http_status':status,'sha256':raw_sha,'raw_hex':raw.hex()}],
        'official_report':parsed}
    digest,blob=worker.packed(envelope)
    document=None
    if parsed:
        prices={r['isin']:r for r in parsed['rows']};rows=[]
        for identity in config['identities']:
            row=prices.get(identity['isin'])
            if row is None or row['price_decimal'] is None:continue
            rows.append({k:identity[k] for k in ['company_id','c_name','symbol']}|{
                'price_decimal':row['price_decimal'],'observation_id':row['observation_id'],'raw_sha256':raw_sha})
        if not rows:raise worker.AcquisitionError('OFFICIAL_MAPPED_PRICES_MISSING')
        document=canonical({'contract':'reviewed-official-closes/v1','price_basis':'OFFICIAL_CLOSE',
            'source_execution':'CURRENT_ACQUISITION','provider_namespace':config['provider_namespace'],
            'source_policy_sha256':config['source_policy_sha256'],'archive_sha256':digest,
            'is_trading_session':True,'session_day':day,'captured_at':captured.isoformat(),
            'session_close_at':None,'published_at':None,'rows':rows})
    return {'contract':CONTRACT,'archive_sha256':digest,'archive_hex':blob.hex(),'day':day,
            'document':document,'identity_document':canonical(config['identities']),
            'parser_sha256':config['parser_sha256'],'source_policy_sha256':config['source_policy_sha256']}



def deliver_only(config,state,store,clock,review_status):
    pending=Outbox(state/'official_close',entry_limit=MAX_JOB)
    accepted=Outbox(state/'official_close.accepted')
    quarantine=Outbox(state/'official_close.quarantine',entry_limit=MAX_JOB)
    today=clock().astimezone(worker.ZONE).date().isoformat()
    for path in pending.entries():
        original=pending.read(path);job=worker.unpacked(path.name[:64],original,max_batch=MAX_JOB)
        if (job.get('contract')!=CONTRACT or job.get('parser_sha256')!=config['parser_sha256']
            or job.get('source_policy_sha256')!=config['source_policy_sha256']
            or job.get('identity_document')!=canonical(config['identities'])):
            raise worker.AcquisitionError('OFFICIAL_PENDING_POLICY_DIFFERS')
        blob=bytes.fromhex(job['archive_hex']);envelope=worker.unpacked(job['archive_sha256'],blob)
        if envelope.get('provider_namespace')!=config['provider_namespace'] or envelope.get('execution')!='CURRENT_ACQUISITION':
            raise worker.AcquisitionError('OFFICIAL_PENDING_CONTEXT_DIFFERS')
        # Preserve the original invalid candidate without rewriting its evidence
        # or retrying an archive the gateway will always reject. A later eligible
        # run must acquire a new report and undergo independent review.
        invalid_capture = any(capture.get('capture_id') != hashlib.sha256(json.dumps(
            [envelope['provider_namespace'],capture.get('sha256'),capture.get('received_at')],
            separators=(',',':')).encode()).hexdigest() for capture in envelope.get('captures',[]))
        if invalid_capture:
            runner_checkpoint.require_headroom(state,reserve_bytes=len(original),additions={'official_close.quarantine':1})
            quarantine.put(path.name[:64],original)
            if quarantine.read(quarantine.directory/path.name)!=original:
                raise worker.AcquisitionError('OFFICIAL_QUARANTINE_READBACK_FAILED')
            pending.acknowledge(path.name[:64])
            return {'status':'INVALID_CAPTURE_QUARANTINED'}
        document_sha=hashlib.sha256(job['document'].encode()).hexdigest() if job['document'] else None
        # Check a committed financial receipt even after a lost local ack or date
        # change. Only an exact server-accepted document may be called complete.
        if document_sha and store.official_complete(config['provider_namespace'],job['archive_sha256'],document_sha):
            runner_checkpoint.require_headroom(state,reserve_bytes=8192,additions={'official_close.accepted':1})
            key,raw=worker.packed({'contract':'official-close-worker-receipt/v1','day':job['day'],
                'job_sha256':path.name[:64],'slot':envelope['slot'],'accepted_at':clock().isoformat(),
                'archive_sha256':job['archive_sha256'],'document_sha256':document_sha})
            accepted.put(key,raw);pending.acknowledge(path.name[:64]);return {'status':'COMPLETE'}
        failed=job['document'] is None or job['day']!=today or (document_sha is not None and review_status(document_sha)=='FAILED')
        additions={'archive':1}
        if failed:additions['official_close.quarantine']=1
        runner_checkpoint.require_headroom(state,reserve_bytes=len(blob)+(len(original) if failed else 0),additions=additions)
        if store.save_blob(job['archive_sha256'],blob)!=job['archive_sha256']:
            raise worker.AcquisitionError('OFFICIAL_ARCHIVE_RECEIPT_DIFFERS')
        if failed:
            quarantine.put(path.name[:64],original)
            if quarantine.read(quarantine.directory/path.name)!=original:raise worker.AcquisitionError('OFFICIAL_QUARANTINE_READBACK_FAILED')
            pending.acknowledge(path.name[:64]);return {'status':'REPORT_UNAVAILABLE'}
        return {'status':'AWAITING_INDEPENDENT_REVIEW'}
    return {'status':'WAITING'}


def run(config,state,*,store=None,fetcher=fetch_report,clock=lambda:datetime.now(timezone.utc),review_status=None):
    validate(config);state=runner_checkpoint.private_directory(state)
    if review_status is None:
        from official_review_dispatch import review_status
    import receipt_history
    receipt_history.compact(state)
    store=store or worker.open_store(None,config)
    if not callable(getattr(store,'official_complete',None)):
        raise worker.AcquisitionError('OFFICIAL_RECEIPT_BACKEND_REQUIRED')
    result=deliver_only(config,state,store,clock,review_status)
    if result['status']!='WAITING':return result
    today=clock().astimezone(worker.ZONE).date().isoformat()
    accepted=Outbox(state/'official_close.accepted')
    if any(worker.unpacked(p.name[:64],accepted.read(p)).get('day')==today for p in accepted.entries()):
        return {'status':'ALREADY_COMPLETE'}
    now=clock();local=now.astimezone(worker.ZONE)
    if local.weekday()>=5 or not (17<=local.hour<19) or (local.hour==17 and local.minute<35):return {'status':'OUTSIDE_WINDOW'}
    slot=now.replace(minute=now.minute//15*15,second=0,microsecond=0).isoformat()
    runner_checkpoint.require_headroom(state,reserve_bytes=24*1024*1024,additions={'official_close':1,'archive':1,'official_close.accepted':1})
    if not store.admit(config['provider_namespace'],'quotes',slot,shadow=False,projection=False):
        raise worker.AcquisitionError('OFFICIAL_ACQUISITION_NOT_ADMITTED')
    raw,captured,status=fetcher(config,today)
    job=build(config,raw,captured,slot,status)
    key,encoded=worker.packed(job,max_batch=MAX_JOB)
    Outbox(state/'official_close',entry_limit=MAX_JOB).put(key,encoded)
    return deliver_only(config,state,store,clock,review_status)
