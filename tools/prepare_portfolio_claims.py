#!/usr/bin/env python3
"""Pin both original portfolios to owner-approved emails without creating users.

Default is read-only preparation. --register writes disabled private bindings
only, never account rows or portfolio data. Values and identities are not printed.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
import os
from pathlib import Path
import re

import psycopg
from psycopg.types.json import Jsonb
from stage_supabase import ROOT, local_config, connection_options, records, verify
from verify_supabase_staging import compare_payloads
import restore_saved_portfolios as saved


def owners(grouped, approved):
    if (not isinstance(approved,dict) or set(approved)!={'contract','larger_email','smaller_email'}
            or approved['contract']!='private-portfolio-owner-bindings/v1'):
        raise ValueError('Invalid private owner configuration')
    emails=[approved[key].strip().lower() for key in ('larger_email','smaller_email')]
    if len(set(emails))!=2 or any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v) or len(v)>254 for v in emails):
        raise ValueError('Two distinct valid emails required')
    totals=defaultdict(Decimal);counts=defaultdict(int)
    for collection,rows in grouped.items():
        for row in rows:
            counts[row['user_id']]+=1
            if collection=='portefeuille': totals[row['user_id']]+=Decimal(str(row['total_cost']))
    if len(totals)!=2 or len(counts)!=2:
        raise ValueError('Exactly two preserved owners required')
    ranked=sorted(totals,key=totals.get,reverse=True)
    if totals[ranked[0]]==totals[ranked[1]] or counts[ranked[0]]<=counts[ranked[1]]:
        raise ValueError('Saved portfolio size is ambiguous')
    return dict(zip(ranked,emails))


def plans(db, selected, mapping):
    result=[]
    datasets=[{'dataset_id':d.identifier,'collection':d.collection,'dataset_sha256':d.expected_hash} for d in sorted(selected,key=lambda d:d.identifier)]
    for owner,email in mapping.items():
        rows=db.execute("""SELECT jsonb_agg(jsonb_build_object('dataset_id',d.dataset_id,
            'document_id',d.document_id,'collection',s.source_metadata->>'collection',
            'dataset_sha256',s.source_sha256,
            'payload_sha256',encode(sha256(convert_to(d.payload::text,'UTF8')),'hex'))
            ORDER BY d.dataset_id,d.document_id)
            FROM migration_stage.documents d JOIN migration_stage.datasets s USING(dataset_id)
            WHERE d.dataset_id=ANY(%s) AND d.payload->>'user_id'=%s""",
            ([d.identifier for d in selected],owner)).fetchone()[0]
        if not rows: raise ValueError('Verified saved owner has no staged data')
        plan={'email':email,'legacy_owner':owner,'source_datasets':datasets,'source_rows':rows}
        pin=db.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(Jsonb(plan),)).fetchone()[0]
        result.append({**plan,'plan_sha256':pin})
    return result


def register(db, prepared):
    if db.execute('SELECT enabled FROM portfolio_private.recovery_control').fetchall()!=[(False,)]:
        raise ValueError('Recovery must be disabled while registering bindings')
    for plan in prepared:
        db.execute('''INSERT INTO portfolio_private.recovery_bindings(email,legacy_owner,source_datasets,source_rows,plan_sha256)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING''',
            (plan['email'],plan['legacy_owner'],Jsonb(plan['source_datasets']),Jsonb(plan['source_rows']),plan['plan_sha256']))
        row=db.execute('SELECT legacy_owner,source_datasets,source_rows,plan_sha256,enabled FROM portfolio_private.recovery_bindings WHERE email=%s FOR UPDATE',(plan['email'],)).fetchone()
        if row!=(plan['legacy_owner'],plan['source_datasets'],plan['source_rows'],plan['plan_sha256'],False):
            raise ValueError('Binding already differs; explicit review required')


def verify_sources(db,selected,counts,*,lock=False):
    suffix=' FOR SHARE' if lock else ''
    for dataset,count in zip(selected,counts):
        metadata=db.execute('SELECT source_sha256,source_bytes,row_count FROM migration_stage.datasets WHERE dataset_id=%s'+suffix,(dataset.identifier,)).fetchone()
        if metadata!=(dataset.expected_hash,dataset.expected_bytes,count):
            raise ValueError('Original source metadata differs')
        rows=db.execute('SELECT document_id,payload FROM migration_stage.documents WHERE dataset_id=%s'+suffix,(dataset.identifier,))
        if compare_payloads(dataset,rows)!=count: raise ValueError('Original source payload differs')
        verify(dataset)


def run(approval,output,*,apply=False):
    destination=Path(output).absolute()
    if not destination.resolve().is_relative_to((ROOT/'private').resolve()) or destination.is_symlink():
        raise ValueError('Outputs must remain private')
    approved=json.loads(Path(approval).read_text())
    selected,counts,summary=saved.prepare(ROOT/'backup_live_recovery_20261022')
    mapping=owners({d.collection:list(records(d)) for d in selected},approved)
    cfg=local_config(ROOT/'.supabase-migration.env')
    verification=saved.restore(cfg,selected,counts,False)
    destination.mkdir(mode=0o700,parents=True,exist_ok=False)
    receipt={'mode':'REGISTER_DISABLED_BINDINGS' if apply else 'READ_ONLY_PREPARATION',
             'owners':2,'original_records':summary['records'],'all_staged_payloads_verified':True,
             'auth_accounts_created':False,'financial_tables_changed':False,'commit':'NOT_ATTEMPTED'}
    def save():
        temp=destination/'receipt.tmp'
        with temp.open('w') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,destination/'receipt.json')
    with psycopg.connect(**connection_options(cfg)) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'+('' if apply else ' READ ONLY'))
        db.execute("SET LOCAL statement_timeout='30s'; SET LOCAL lock_timeout='2s'")
        if not db.pgconn.ssl_in_use: raise ValueError('TLS required')
        # Lock before the first snapshot SELECT. A repeatable-read snapshot
        # taken earlier could hide a concurrent activation committed while
        # this transaction waits for the control lock.
        if apply:
            db.execute('LOCK TABLE portfolio_private.recovery_control,portfolio_private.recovery_bindings IN SHARE ROW EXCLUSIVE MODE')
        verify_sources(db,selected,counts,lock=apply)
        prepared=plans(db,selected,mapping)
        (destination/'plans.private.json').write_text(json.dumps({'contract':'private-portfolio-recovery-plans/v1','plans':prepared},indent=2)+'\n')
        if apply:
            register(db,prepared)
            receipt['commit']='UNKNOWN';save()
            db.commit();receipt['commit']='COMMITTED'
        else: receipt['commit']='READ_ONLY'
    save()
    if apply:
        with psycopg.connect(**connection_options(cfg)) as db:
            db.execute('SET TRANSACTION READ ONLY')
            if db.execute('SELECT enabled FROM portfolio_private.recovery_control').fetchall()!=[(False,)]:
                raise ValueError('Recovery control changed during registration')
            for plan in prepared:
                actual=db.execute('SELECT legacy_owner,source_datasets,source_rows,plan_sha256,enabled FROM portfolio_private.recovery_bindings WHERE email=%s',(plan['email'],)).fetchone()
                if actual!=(plan['legacy_owner'],plan['source_datasets'],plan['source_rows'],plan['plan_sha256'],False):
                    raise ValueError('Fresh binding verification failed')
        receipt['fresh_readback_verified']=True;save()
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owners',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--register',action='store_true')
    args=parser.parse_args(argv)
    os.umask(0o077)
    try:
        print(json.dumps(run(args.owners,args.output,apply=args.register)))
        return 0
    except Exception as error:
        print(json.dumps({'ok':False,'error_category':type(error).__name__,'identities_printed':False}))
        return 1


if __name__=='__main__': raise SystemExit(main())
