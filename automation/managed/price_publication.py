"""Durable shadow publication handoff, distinct from raw archive completion."""
from datetime import datetime, timezone
import os
import re
from pathlib import Path
import tempfile

import app_feed
import app_publish
import worker
from outbox import Outbox,separate_spools

CONTRACT = 'private-price-publication-job/v1'
RECEIPT = 'private-price-publication-commit/v1'
MAX_JOB = 24*1024*1024


def company_inputs(config,profile,*,companies_path=None,bindings_path=None,index_path=None):
    if not profile.get('application_fields_sha256'):
        if any(path is not None for path in [companies_path,bindings_path,index_path]):
            raise worker.AcquisitionError('APPLICATION_PROFILE_PIN_REQUIRED')
        return None,None,None
    if bindings_path is None:
        raise worker.AcquisitionError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
    if companies_path is not None and index_path is not None:
        raise worker.AcquisitionError('AMBIGUOUS_COMPANY_INPUTS')
    bindings=worker.decode(Path(bindings_path).read_bytes())
    if app_feed.fingerprint(bindings)!=profile['application_fields_sha256']:
        raise worker.AcquisitionError('APPLICATION_FIELDS_PIN_MISMATCH')
    context=None
    if companies_path is not None:
        companies=worker.decode(Path(companies_path).read_bytes())
    elif index_path is not None:
        # Explicit legacy compatibility. New price jobs need no enrichment lease.
        import fundamental_feed
        from projection_store import ProjectionPublisher
        index=worker.decode(Path(index_path).read_bytes())
        fundamental_feed.validate_index(index,index['provider_namespace'])
        publisher=ProjectionPublisher(os.environ.get('APP_PROJECTION_URL',''),os.environ.get('APP_PROJECTION_TOKEN',''),
            os.environ.get('APP_PROJECTION_PROJECT_REFERENCE',''))
        context=publisher.read_context(index['provider_namespace'],fundamental_feed.fingerprint(index))
        if context['contract']!='private-enrichment-context/v2':
            raise worker.AcquisitionError('PRICE_CONTEXT_REQUIRED')
        companies=context['price_companies']
    else:
        context = app_publish.open_publisher(config).read_context(config, profile)
        companies = context['price_companies']
    if not isinstance(companies,dict): raise worker.AcquisitionError('INVALID_COMPANY_INPUTS')
    return companies,bindings,context


class Publications:
    def __init__(self, config, profile, spool=None):
        self.config, self.profile = config, profile
        app_publish.approved_mapping(profile,config)
        self.pin = app_feed.fingerprint(profile)
        directory = Path(spool or os.environ.get('APP_PRICE_PUBLICATION_SPOOL_DIR') or
            Path(tempfile.gettempdir())/('private-price-publications-'+config['archive_project_reference']))
        self.pending=Outbox(directory,entry_limit=MAX_JOB)
        self.accepted=Outbox(directory.with_name(directory.name+'.accepted'))
        self.quarantine=Outbox(directory.with_name(directory.name+'.quarantine'),entry_limit=MAX_JOB)

    def available(self, store, *, other_spools=()):
        if not callable(getattr(store,'save_blob',None)):
            raise worker.AcquisitionError('EXACT_ARCHIVE_STORAGE_REQUIRED')
        self.pending._check_directory()
        self.accepted._check_directory()
        archive=getattr(store,'outbox',None)
        separate_spools(self.pending.directory,self.accepted.directory,
            archive.directory if archive is not None else None,*other_spools)
        if sum(p.stat().st_size for p in self.pending.entries())+MAX_JOB>self.pending.limit:
            raise worker.AcquisitionError('OUTBOX_CAPACITY')
        if sum(p.stat().st_size for p in self.accepted.entries())+8192>self.accepted.limit:
            raise worker.AcquisitionError('OUTBOX_CAPACITY')

    def enqueue(self, value, *, now=None, companies=None, field_bindings=None, company_context=None):
        digest,blob=worker.packed(value)
        prepared,error=None,None
        try:
            if self.profile.get('application_fields_sha256') and (companies is None or field_bindings is None):
                raise worker.AcquisitionError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
            prepared=app_publish.prepare(blob,digest,self.config,self.profile,as_of=now or datetime.now(timezone.utc),
                companies=companies,field_bindings=field_bindings)
        except Exception:
            error='PRICE_PREPARATION_FAILED'
        job={'contract':CONTRACT,'archive_sha256':digest,'archive_hex':blob.hex(),
             'profile_sha256':self.pin,'prepared':prepared,'preparation_error':error,
             'companies':companies,'field_bindings':field_bindings,'company_context':company_context}
        key,encoded=worker.packed(job,max_batch=MAX_JOB)
        self.pending.put(key,encoded)
        return digest,blob

    def checked(self,job):
        if job.get('contract')!=CONTRACT or job.get('profile_sha256')!=self.pin:
            raise worker.AcquisitionError('PUBLICATION_CONTEXT_CHANGED')
        blob=bytes.fromhex(job['archive_hex']);digest=job['archive_sha256']
        value=worker.unpacked(digest,blob)
        context=job.get('company_context')
        if context is not None and context.get('price_companies')!=job.get('companies'):
            raise worker.AcquisitionError('PRICE_CONTEXT_CHANGED')
        # Full archive/namespace/raw identity verification precedes any send.
        app_feed.verified_archive(blob,digest,self.config)
        if value.get('execution')!='CURRENT_ACQUISITION':
            raise worker.AcquisitionError('PUBLISH_REQUIRES_CURRENT_ACQUISITION')
        if job['prepared'] is not None:
            if self.profile.get('application_fields_sha256') is not None and (
                    job.get('companies') is None or job.get('field_bindings') is None
                    or job['prepared'].get('application_rows') is None):
                raise worker.AcquisitionError('COMPLETE_APPLICATION_INPUTS_REQUIRED')
            actual=app_publish.prepare(blob,digest,self.config,self.profile,
                as_of=worker.utc(job['prepared']['candidate']['as_of']),
                companies=job.get('companies'),field_bindings=job.get('field_bindings'))
            if app_feed.canonical(actual)!=app_feed.canonical(job['prepared']):
                raise worker.AcquisitionError('PUBLICATION_DOCUMENT_CHANGED')
        elif job.get('preparation_error')!='PRICE_PREPARATION_FAILED':
            raise worker.AcquisitionError('INVALID_PUBLICATION_JOB')
        return value,blob

    def flush(self,store,*,publisher=None):
        latest=None
        for path in self.pending.entries():
            from publish_store import AppPublisherStore
            if isinstance(store,worker.SQLiteStore) and (publisher is None or isinstance(publisher,AppPublisherStore)):
                raise worker.AcquisitionError('ISOLATED_PUBLISHER_REQUIRED')
            job=worker.unpacked(path.name[:64],self.pending.read(path),max_batch=MAX_JOB)
            value,blob=self.checked(job)
            # Recover a completed logical publication after an interrupted local ack.
            # Reusing its durable receipt avoids a second receipt with a new clock.
            restored=None
            for committed in self.accepted.entries():
                saved=worker.unpacked(committed.name[:64],self.accepted.read(committed))
                if saved.get('job_sha256')!=path.name[:64]:continue
                if job['prepared'] is None:raise worker.AcquisitionError('INVALID_PUBLISH_RECEIPT')
                expected={'contract':RECEIPT,'job_sha256':path.name[:64],
                    'provider_namespace':self.config['provider_namespace'],'slot':value['slot'],
                    'archive_sha256':job['archive_sha256'],'profile_sha256':self.pin,
                    'quote_sha256':app_feed.fingerprint(job['prepared']['candidate']),
                    'application_rows_sha256':app_feed.fingerprint(job['prepared']['application_rows']) if job['prepared']['application_rows'] is not None else None}
                if set(saved)!=set(expected)|{'accepted_at'} or any(saved.get(k)!=v for k,v in expected.items()):
                    raise worker.AcquisitionError('INVALID_PUBLISH_RECEIPT')
                worker.utc(saved['accepted_at'])
                restored={'status':'PUBLISHED','sha256':saved['quote_sha256'],
                    'captured_at':job['prepared']['candidate']['captured_at'],
                    **({'application_rows_sha256':saved['application_rows_sha256']} if saved['application_rows_sha256'] is not None else {})}
            if restored is not None:
                self.pending.acknowledge(path.name[:64]);latest=restored;continue
            if os.environ.get('APP_SCHEDULE_CONTRACT') == 'recurring-casablanca/v1':
                candidate = (job.get('prepared') or {}).get('candidate')
                expired = candidate is not None and (
                    datetime.now(timezone.utc) - worker.utc(candidate['captured_at'])
                ).total_seconds() >= candidate['capture_max_age_seconds']
                if expired or job.get('preparation_error') is not None:
                    # Preserve the raw archive AND the full failed/expired intent.
                    # Neither is relabeled as a successful current publication.
                    original = self.pending.read(path)
                    root = os.environ.get('APP_CHECKPOINT_ROOT')
                    if root is not None:
                        import runner_checkpoint as checkpoint
                        additions = {'quotes.quarantine': 0 if any(p.name == path.name for p in self.quarantine.entries()) else 1}
                        reserve = len(original)
                        raw_queue = getattr(store,'outbox',None)
                        if raw_queue is not None and not any(p.name == job['archive_sha256']+'.json.gz' for p in raw_queue.entries()):
                            additions['archive'] = 1
                            reserve += len(blob)
                        checkpoint.require_headroom(root,reserve_bytes=reserve,additions=additions)
                    if store.save_blob(job['archive_sha256'],blob) != job['archive_sha256']:
                        raise worker.AcquisitionError('INVALID_ARCHIVE_RECEIPT')
                    original = self.pending.read(path)
                    self.quarantine.put(path.name[:64],original)
                    if self.quarantine.read(self.quarantine.directory/path.name) != original:
                        raise worker.AcquisitionError('QUARANTINE_READBACK_FAILED')
                    self.pending.acknowledge(path.name[:64])
                    latest = {'status':'EXPIRED_OR_REJECTED_PRESERVED','archive_sha256':job['archive_sha256']}
                    continue
            worker.require_checkpoint_delivery_headroom('quotes',store,job['archive_sha256'],blob)
            if store.save_blob(job['archive_sha256'],blob)!=job['archive_sha256']:
                raise worker.AcquisitionError('INVALID_ARCHIVE_RECEIPT')
            if job['prepared'] is None:
                raise worker.AcquisitionError('PRICE_PREPARATION_FAILED')
            result=app_publish.publish_prepared(job['prepared'],self.config,publisher=publisher)
            if result['sha256']!=app_feed.fingerprint(job['prepared']['candidate']):
                raise worker.AcquisitionError('INVALID_PUBLISH_RECEIPT')
            full_rows=job['prepared']['application_rows']
            if full_rows is not None and result.get('application_rows_sha256')!=app_feed.fingerprint(full_rows):
                raise worker.AcquisitionError('INVALID_PUBLISH_RECEIPT')
            receipt={'contract':RECEIPT,'job_sha256':path.name[:64],
                'provider_namespace':self.config['provider_namespace'],'slot':value['slot'],
                'archive_sha256':job['archive_sha256'],'profile_sha256':self.pin,
                'quote_sha256':result['sha256'],'application_rows_sha256':result.get('application_rows_sha256'),
                'accepted_at':datetime.now(timezone.utc).isoformat()}
            key,encoded=worker.packed(receipt)
            self.accepted.put(key,encoded) # Durable receipt BEFORE removing the retry job.
            self.pending.acknowledge(path.name[:64])
            latest=result
        return latest

    def complete(self,slot):
        for path in self.accepted.entries():
            value=worker.unpacked(path.name[:64],self.accepted.read(path))
            if (value.get('contract')==RECEIPT and value.get('profile_sha256')==self.pin
                    and value.get('provider_namespace')==self.config['provider_namespace'] and value.get('slot')==slot
                    and (self.profile.get('application_fields_sha256') is None or
                         isinstance(value.get('application_rows_sha256'),str) and
                         re.fullmatch(r'[a-f0-9]{64}',value['application_rows_sha256']))):
                return True
        return False
