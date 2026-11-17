#!/usr/bin/env python3
"""Prepare reviewed listing changes read-only; explicit --apply requires a pinned plan.

No discovery/collection is performed. The owner supplies an original saved
archive, private recipe/bindings and a verified database CA certificate. This
does not update provider profiles or enable any job.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg

from stage_supabase import ROOT,local_config,connection_options
sys.path.insert(0,str(ROOT/'automation/managed'))
import app_feed
import listing_plan
import worker


def journal(path,value):
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def local_inputs(args):
    if args.archive.stat().st_size>worker.MAX_BATCH:raise ValueError('Archive exceeds bound')
    blob=args.archive.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=args.sha256:raise ValueError('Original archive changed')
    config=worker.decode(args.config.read_bytes());bindings=worker.decode(args.bindings.read_bytes())
    envelope,_,_,_=app_feed.verified_archive(blob,args.sha256,config)
    return blob,config,bindings,envelope


def run(args):
    output=args.output.absolute()
    if output.is_symlink() or not output.resolve().is_relative_to((ROOT/'private').resolve()):raise ValueError('Private output required')
    blob,config,bindings,envelope=local_inputs(args)
    options={**connection_options(local_config(ROOT/'.supabase-migration.env')),
             'sslmode':'verify-full','sslrootcert':str(args.ca.resolve())}
    if not args.ca.is_file():raise ValueError('Verified database CA required')
    plan=None
    if args.apply:
        if not args.plan or not args.approve:raise ValueError('A reviewed plan and explicit digest are required')
        raw=args.plan.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=args.approve:raise ValueError('Approved plan changed')
        plan=worker.decode(raw)
        if (plan.get('archive_sha256')!=args.sha256 or plan.get('provider_namespace')!=config['provider_namespace']
                or plan.get('recipe_sha256')!=app_feed.fingerprint(config['recipe'])
                or plan.get('bindings_sha256')!=app_feed.fingerprint(bindings)):
            raise ValueError('Approved input context differs')
    elif args.plan or args.approve:
        raise ValueError('Approval arguments require --apply')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    receipt={'mode':'APPLY_REVIEWED_LISTINGS' if args.apply else 'READ_ONLY_PREPARATION',
             'commit':'NOT_ATTEMPTED','source_requests':0,'profiles_changed':False,'accounts_changed':False}
    save=lambda:journal(output/'receipt.json',receipt)
    with psycopg.connect(**options) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL '+('READ COMMITTED' if args.apply else 'REPEATABLE READ READ ONLY'))
        db.execute("SET LOCAL statement_timeout='30s'; SET LOCAL lock_timeout='2s'")
        metadata=db.execute('SELECT provider,kind,slot,completed_at,compressed_bytes,state FROM app_archive.objects WHERE digest=%s',
                            (args.sha256,)).fetchone()
        if metadata!=(config['provider_namespace'],'quotes',worker.utc(envelope['slot']),
                      worker.utc(envelope['completed_at']),len(blob),'STORED'):
            raise ValueError('Current stored archive metadata differs from original local bytes')
        if plan is None:
            before=db.execute(listing_plan.catalog_fingerprint_sql()).fetchone()[0]
            companies=[{'id':v[0],'name':v[1]} for v in db.execute('SELECT id,name FROM public.company ORDER BY id')]
            mappings=[{'symbol':v[0],'name':v[1]} for v in db.execute('SELECT symbol,name FROM public.format ORDER BY id')]
            plan=listing_plan.build(blob,args.sha256,config,bindings,companies,mappings,before)
            raw=app_feed.canonical(plan).encode()
        pin=hashlib.sha256(raw).hexdigest()
        (output/'plan.private.json').write_bytes(raw)
        receipt.update(plan_sha256=pin,additions=len(plan['additions']),conflicts=len(plan['conflicts']))
        if args.apply:
            if db.execute("SELECT to_regprocedure('market_maintenance.apply_listing_plan(text,text)') IS NOT NULL").fetchone()[0] is not True:
                raise ValueError('Reviewed listing writer is not installed')
            prior=db.execute('SELECT document FROM market_maintenance.listing_receipts WHERE plan_sha256=%s',(pin,)).fetchone()
            if prior is None:
                before=db.execute(listing_plan.catalog_fingerprint_sql()).fetchone()[0]
                companies=[{'id':v[0],'name':v[1]} for v in db.execute('SELECT id,name FROM public.company ORDER BY id')]
                mappings=[{'symbol':v[0],'name':v[1]} for v in db.execute('SELECT symbol,name FROM public.format ORDER BY id')]
                if listing_plan.build(blob,args.sha256,config,bindings,companies,mappings,before)!=plan:
                    raise ValueError('Reviewed additions no longer match exact archive and catalog')
            elif prior!=(plan,):
                raise ValueError('Committed listing plan differs')
            save()
            result=db.execute('SELECT market_maintenance.apply_listing_plan(%s,%s)',(raw.decode(),pin)).fetchone()[0]
            # Preserve UNKNOWN if acknowledgement is lost; never auto-reapply a new plan.
            receipt['commit']='UNKNOWN';save();db.commit();receipt['commit']='COMMITTED'
            receipt['result']=result
        else:receipt['commit']='READ_ONLY'
    save()
    if args.apply:
        with psycopg.connect(**options) as db:
            db.execute('SET TRANSACTION READ ONLY')
            actual=db.execute('SELECT document,receipt FROM market_maintenance.listing_receipts WHERE plan_sha256=%s',(pin,)).fetchone()
            if actual is None or actual!=(plan,receipt['result']):raise ValueError('Fresh listing receipt differs')
            for table in ['app_archive.control','app_feed.control','app_projection.control']:
                if db.execute('SELECT enabled FROM '+table).fetchall()!=[(False,)]:raise ValueError('Collection state changed')
        receipt['fresh_readback_verified']=True;save()
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','config','bindings','ca','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--approve')
    args=parser.parse_args(argv);previous=os.umask(0o077)
    try:print(json.dumps(run(args)));return 0
    except Exception as error:
        print(json.dumps({'ok':False,'category':type(error).__name__,'details_printed':False}));return 1
    finally:os.umask(previous)


if __name__=='__main__':raise SystemExit(main())
