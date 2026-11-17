"""Independent official-report verifier for a separate protected runner job.

The attestation key and financial caller token MUST exist only in the review
job's protected environment, never in collector repository secrets/checkpoints.
Candidate prices are independently rederived from a fresh approved TLS download.
"""
from datetime import datetime,timezone
import hashlib,hmac,json,os,re
from pathlib import Path

import official_close
import official_close_collect as collect
import runner_checkpoint
import worker


def verify(config,job,*,fetcher=collect.fetch_report,clock=lambda:datetime.now(timezone.utc)):
    collect.validate(config)
    if job.get('contract')!=collect.CONTRACT or job.get('source_policy_sha256')!=config['source_policy_sha256'] or job.get('parser_sha256')!=config['parser_sha256'] or job.get('identity_document')!=collect.canonical(config['identities']):
        raise worker.AcquisitionError('OFFICIAL_REVIEW_POLICY_DIFFERS')
    if not isinstance(job.get('document'),str):raise worker.AcquisitionError('OFFICIAL_REVIEW_DOCUMENT_REQUIRED')
    doc=json.loads(job['document']);now=clock();day=now.astimezone(worker.ZONE).date().isoformat()
    if doc.get('session_day')!=day or doc.get('source_policy_sha256')!=config['source_policy_sha256'] or doc.get('provider_namespace')!=config['provider_namespace']:
        raise worker.AcquisitionError('OFFICIAL_REVIEW_SESSION_DIFFERS')
    archive=bytes.fromhex(job['archive_hex']);envelope=worker.unpacked(job['archive_sha256'],archive)
    if envelope.get('execution')!='CURRENT_ACQUISITION' or envelope.get('provider_namespace')!=config['provider_namespace'] or len(envelope.get('captures',[]))!=1:
        raise worker.AcquisitionError('OFFICIAL_REVIEW_ARCHIVE_DIFFERS')
    capture=envelope['captures'][0];original=bytes.fromhex(capture['raw_hex'])
    if hashlib.sha256(original).hexdigest()!=capture['sha256'] or capture['received_at']!=doc.get('captured_at'):
        raise worker.AcquisitionError('OFFICIAL_REVIEW_RAW_DIFFERS')
    # This download uses the review environment's own approved endpoint/roots.
    # No endpoint, identity binding or price from the producer is trusted here.
    current,received,status=fetcher(config,day)
    if status!=200 or current!=original:raise worker.AcquisitionError('OFFICIAL_SOURCE_REPORT_CHANGED')
    parsed=official_close.parse_pdf(current,day)
    prices={row['isin']:row for row in parsed['rows']};expected=[]
    for binding in config['identities']:
        row=prices.get(binding['isin'])
        if row is not None and row['price_decimal'] is not None:
            expected.append({k:binding[k] for k in ['company_id','c_name','symbol']}|{
                'price_decimal':row['price_decimal'],'observation_id':row['observation_id'],'raw_sha256':parsed['raw_sha256']})
    if doc.get('rows')!=expected or envelope.get('official_report')!=parsed:
        raise worker.AcquisitionError('OFFICIAL_REVIEW_PRICE_DIFFERS')
    if doc.get('archive_sha256')!=job['archive_sha256'] or worker.utc(doc['captured_at'])>received or received>clock():
        raise worker.AcquisitionError('OFFICIAL_REVIEW_CHRONOLOGY_DIFFERS')
    return {'document_sha256':hashlib.sha256(job['document'].encode()).hexdigest(),
            'raw_sha256':parsed['raw_sha256'],'identity_sha256':hashlib.sha256(job['identity_document'].encode()).hexdigest(),
            'parser_sha256':config['parser_sha256'],'source_policy_sha256':config['source_policy_sha256'],
            'verified_at':clock().isoformat()}


def attested_body(config,job,key,commit,*,fetcher=collect.fetch_report,clock=lambda:datetime.now(timezone.utc)):
    if not re.fullmatch('[a-f0-9]{64}',key) or not re.fullmatch('[a-f0-9]{40}',commit):
        raise worker.AcquisitionError('OFFICIAL_REVIEW_CREDENTIAL_REQUIRED')
    proof={'contract':'official-close-attestation/v1','worker_commit':commit,**verify(config,job,fetcher=fetcher,clock=clock)}
    document=collect.canonical(proof)
    return {'p_document':job['document'],'p_sha256':proof['document_sha256'],
            'p_parser_sha256':config['parser_sha256'],'p_identity_document':job['identity_document'],
            'attestation_document':document,'attestation_hmac':hmac.new(key.encode(),document.encode(),hashlib.sha256).hexdigest()}


def require_review_commit(reply,expected):
    if (not isinstance(reply,dict) or reply.get('status')!='READY'
            or reply.get('worker_commit')!=expected):
        raise worker.AcquisitionError('OFFICIAL_REVIEW_DEPLOYMENT_MISMATCH')


def main():
    import argparse,requests
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True);args=parser.parse_args()
    try:
        if os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
            raise worker.AcquisitionError('OFFICIAL_REVIEW_RUN_REQUIRED')
        config=worker.decode(os.environ['APP_OFFICIAL_REVIEW_CONFIG'])
        if os.environ.get('GITHUB_REPOSITORY')!=config['worker_repository']:
            raise worker.AcquisitionError('OFFICIAL_REVIEW_REPOSITORY_DIFFERS')
        state=runner_checkpoint.private_directory(args.state)
        spool=runner_checkpoint.queue(state,'official_close');processed=0
        for path in spool.entries():
            job=worker.unpacked(path.name[:64],spool.read(path),max_batch=collect.MAX_JOB)
            if job.get('document') is None:continue
            url=os.environ['APP_OFFICIAL_CLOSE_URL'];token=os.environ['APP_OFFICIAL_CLOSE_TOKEN']
            if url!=f"https://{config['archive_project_reference']}.supabase.co/functions/v1/private-official-close-publisher" or not re.fullmatch('official_close_[a-f0-9]{64}',token):
                raise worker.AcquisitionError('OFFICIAL_REVIEW_DESTINATION_DIFFERS')
            http=requests.Session();http.trust_env=False
            with http.get(url,headers={'Authorization':'Bearer '+token},timeout=(8,15),allow_redirects=False,stream=True) as r:
                raw=r.raw.read(1025,decode_content=True)
                if r.status_code!=200 or len(raw)>1024:
                    raise worker.AcquisitionError('OFFICIAL_REVIEW_PREFLIGHT_UNAVAILABLE')
                require_review_commit(json.loads(raw),os.environ['GITHUB_SHA'])
            body=attested_body(config,job,os.environ['APP_OFFICIAL_ATTESTATION_KEY'],os.environ['GITHUB_SHA'])
            with http.post(url,json=body,headers={'Authorization':'Bearer '+token},timeout=(8,25),allow_redirects=False,stream=True) as r:
                # HTTP content encoding is transport metadata. Bound the
                # decoded receipt, including when the gateway gzip-compresses it.
                raw=r.raw.read(4097, decode_content=True)
                if r.status_code!=200 or len(raw)>4096:raise worker.AcquisitionError('OFFICIAL_REVIEW_PUBLICATION_REJECTED')
                reply=json.loads(raw)
                if reply.get('status')!='ACCEPTED' or reply.get('sha256')!=body['p_sha256']:raise worker.AcquisitionError('OFFICIAL_REVIEW_RECEIPT_DIFFERS')
            processed+=1
        print(json.dumps({'status':'VERIFIED' if processed else 'NO_CANDIDATE','reports':processed}));return 0
    except Exception as error:
        print(json.dumps({'status':'FAILED','code':str(error) if isinstance(error,worker.AcquisitionError) else 'OFFICIAL_REVIEW_FAILED'}));return 1


if __name__=='__main__':
    raise SystemExit(main())
