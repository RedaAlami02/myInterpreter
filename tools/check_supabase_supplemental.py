#!/usr/bin/env python3
"""Read-only check of non-personal data coverage, REST and PHP profile reads."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import psycopg
from psycopg import sql
import requests

from stage_supabase import ROOT, connection_options, local_config
from restore_nonpersonal_data import TABLES


def check(config, access_token=None):
    report={"ok":True,"read_only":True,"tables":{},"application_private_data_included":False}
    with psycopg.connect(**connection_options(config)) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        conn.execute("SET LOCAL statement_timeout='60s'")
        if not conn.pgconn.ssl_in_use:raise ValueError('TLS required')
        for table in TABLES:
            report['tables'][table]=conn.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table))).fetchone()[0]
        fields=['description','sector','shareholders']
        report['company_profiles']={field:conn.execute(sql.SQL("SELECT count(*) FROM public.company_profiles WHERE profile->%s IS NOT NULL AND profile->>%s IS NOT NULL AND profile->%s NOT IN ('null'::jsonb,'[]'::jsonb,'\"\"'::jsonb)"),(field,field,field)).fetchone()[0] for field in fields}
        report['company_profiles']['unmatched_symbols']=[r[0] for r in conn.execute("SELECT id FROM public.company_profiles WHERE profile->>'source_status'='unmatched_symbol' ORDER BY id")]
        report['MASI']=dict(zip(['observations','days','first_utc','last_utc'],conn.execute("SELECT count(*),count(DISTINCT date::date),min(date),max(date) FROM public.data WHERE c_name='MASI'").fetchone()))
        report['archive']=dict(zip(['files','original_bytes'],conn.execute('SELECT count(*),sum(source_bytes) FROM recovery_archive.files').fetchone()))
        report['archive_categories']={r[0]:r[1] for r in conn.execute('SELECT category,count(*) FROM recovery_archive.files GROUP BY category')}
        report['database_bytes']=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        report['daily_price_reference'] = dict(zip(
            ('rows', 'symbols', 'first_day', 'last_day', 'inconsistent_ohlc_rows',
             'missing_company_days', 'missing_days_with_trade_activity'),
            conn.execute("""SELECT count(*),count(DISTINCT symbol),min(period_day),max(period_day),
                count(*) FILTER(WHERE quality->'issues' ? 'inconsistent_ohlc_range'),
                count(*) FILTER(WHERE quality->>'comparison'='no_recovered_company_day'),
                count(*) FILTER(WHERE quality->>'comparison'='no_recovered_company_day'
                    AND (quality->>'has_trade_activity_evidence')::boolean)
                FROM public.daily_price_reference""").fetchone()))
        daily_report = json.loads((ROOT/'backup_live_nonpersonal_20261024/daily_reference_restore.json').read_text())
        if report['daily_price_reference']['rows'] != daily_report['rows']:
            raise ValueError('Daily reference count differs from verified restore')
        for role in ('anon','authenticated','service_role'):
            if conn.execute("SELECT has_schema_privilege(%s,'recovery_archive','USAGE') OR has_table_privilege(%s,'recovery_archive.files','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",(role,role)).fetchone()[0]:
                raise ValueError('Archive isolation failed')
            for table in (*TABLES, 'daily_price_reference'):
                grant=conn.execute("SELECT has_table_privilege(%s,%s,'SELECT'),has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE')",(role,'public.'+table,role,'public.'+table)).fetchone()
                if grant!=(role!='anon',False):raise ValueError('Authenticated-only grants failed')
        conn.rollback()
    if access_token is None:
        denied = 0
        for table in (*TABLES, 'daily_price_reference'):
            response=requests.get(config['SUPABASE_PROJECT_URL'].rstrip('/')+'/rest/v1/'+table,
                headers={'apikey':config['SUPABASE_PUBLISHABLE_KEY']},
                params={'select':'id','limit':1},timeout=(10,30),allow_redirects=False)
            if response.status_code not in (401,403):
                raise ValueError('Anonymous supplemental access not denied')
            denied += 1
        report.update(anonymous_relations_denied=denied,authenticated_api_verified=False,
                      php_api_status='requires_in_memory_authenticated_token',archive_isolation_verified=True)
        return report
    fields=json.loads((ROOT/'migrations/supabase/supplemental_contract.json').read_text())['tables']
    api_checks={}
    for table in TABLES:
        response=requests.get(config['SUPABASE_PROJECT_URL'].rstrip('/')+'/rest/v1/'+table,
            headers={'apikey':config['SUPABASE_PUBLISHABLE_KEY'],'Authorization':'Bearer '+access_token},
            params={'select':','.join(['id',*fields[table]['fields']]),'limit':500},timeout=(10,30),allow_redirects=False)
        if response.status_code!=200 or len(response.json())!=report['tables'][table]:raise ValueError('Supplemental REST read failed')
        api_checks[table]=len(response.json())
    response=requests.get(config['SUPABASE_PROJECT_URL'].rstrip('/')+'/rest/v1/daily_price_reference',
        headers={'apikey':config['SUPABASE_PUBLISHABLE_KEY'],'Authorization':'Bearer '+access_token,'Prefer':'count=exact'},
        params={'select':'id,period_day,bar,quality','order':'period_day.asc,id.asc','limit':2},
        timeout=(10,30),allow_redirects=False)
    if (response.status_code not in (200,206) or len(response.json())!=2
            or not response.headers.get('content-range','').endswith('/'+str(daily_report['rows']))):
        raise ValueError('Daily reference REST read failed')
    for row in response.json():
        if (len(row['period_day'])!=10 or row['quality']['observation_kind']!='daily_reference'
                or 'source' in row['bar'] or 'source_file' in row['bar']):
            raise ValueError('Daily reference public projection failed')
    api_checks['daily_price_reference']=daily_report['rows']
    # Exercise the actual PHP aggregator, with only public config over stdin.
    program="""$c=json_decode(stream_get_contents(STDIN),true);putenv('MYINTERPRETER_BACKEND=supabase');putenv('SUPABASE_PROJECT_URL='.$c['url']);putenv('SUPABASE_PUBLISHABLE_KEY='.$c['key']);$_SERVER['SCRIPT_NAME']='/handlers/market_proxy.php';require 'config/config.php';require 'core/Appwrite.php';$u=sb_app()->user($c['token']);$_SESSION=['auth_backend'=>'supabase','USER_ID'=>$u['id'],'sb_auth'=>['access_token'=>$c['token'],'refresh_token'=>'unused-probe-placeholder','expires_at'=>time()+600]];require 'handlers/market_proxy.php';$p=mkt_fetch_symbol('T2S');if(empty($p['charts']['rnpg'])||empty($p['interim'])||($p['computed']['fiscal_year']??0)!==2025){exit(1);}$bars=aw_list_docs('daily_price_reference',[q_equal('symbol','ADH'),q_order_asc('period_day'),q_limit(2)]);if(count($bars)!==2||strlen($bars[0]['period_day'])!==10||!isset($bars[0]['quality']['issues'])){exit(1);}echo json_encode(['php_profile_read'=>true,'annual_charts'=>true,'interim_periods'=>true,'php_daily_reference_read'=>true]);"""
    result=subprocess.run(['php','-r',program],input=json.dumps({'url':config['SUPABASE_PROJECT_URL'],'key':config['SUPABASE_PUBLISHABLE_KEY'],'token':access_token}),
        text=True,capture_output=True,cwd=ROOT,timeout=45)
    if result.returncode:raise ValueError('PHP supplemental profile read failed')
    report.update(json.loads(result.stdout))
    report['authenticated_rest_reads']=api_checks
    report['authenticated_api_verified']=True
    report['archive_isolation_verified']=True
    report['public_mutation_grants_absent']=True
    report['generated_at_utc']=datetime.now(timezone.utc).isoformat()
    return report


if __name__=='__main__':
    try:
        report=check(local_config(ROOT/'.supabase-migration.env'))
        (ROOT/'backup_live_nonpersonal_20261024/supplemental_verification.json').write_text(json.dumps(report,default=str,indent=2)+'\n')
        print(json.dumps(report,default=str))
    except Exception as error:
        print(json.dumps({'ok':False,'error_category':type(error).__name__}))
        raise SystemExit(1)
