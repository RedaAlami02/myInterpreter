#!/usr/bin/env python3
"""Restore known market archives and comprehensive supplemental market data.

No users, portfolios, trades, function variables, keys, or personal collections
are selected. Raw source/archive bytes remain in an admin-only schema; sanitized
market/profile/reference snapshots get public SELECT-only tables. Existing
Appwrite recovery tables are never modified by this importer.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from stage_supabase import ROOT, connection_options, local_config, sha256
from issuer_disclosures import merge_issuer, parse_issuer

MARKER = "myInterpreter nonpersonal archive v1"
LIMIT = 350_000_000
TABLES = ("company_profiles","market_snapshots","market_reference","market_orderbooks","dividend_source_snapshots")


def sanitized_diagnostics(rows, user_ids, secret_values):
    retained=[];personal_omitted=0;credentials_redacted=0
    for row in rows:
        # Permissions contain legacy ownership identifiers; logs do not need them.
        record={key:value for key,value in row.items() if key!='$permissions'}
        text=json.dumps(record,ensure_ascii=False)
        if (any(value and value in text for value in user_ids)
                or re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text)
                or re.search(r'"(?:user_id|userid|password|refresh_token)"\s*:',text,re.I)):
            personal_omitted+=1
            continue
        redacted=False
        def clean(value):
            nonlocal redacted
            if isinstance(value,str):
                result=value
                for secret in secret_values:
                    if secret and secret in result:
                        result=result.replace(secret,'[credential omitted]')
                        redacted=True
                result,count=re.subn(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}',
                                     '[credential omitted]',result)
                redacted=redacted or count>0
                return result
            if isinstance(value,list):return [clean(item) for item in value]
            if isinstance(value,dict):return {key:clean(item) for key,item in value.items()}
            return value
        retained.append(clean(record))
        credentials_redacted+=redacted
    return retained,{'records_retained':len(retained),'personal_records_omitted':personal_omitted,
                     'credential_records_redacted':credentials_redacted}


def reject_personal_or_secrets(value):
    denied = {"user_id","userid","password","access_token","refresh_token","authorization",
              "api_key","apikey","secret_key","aw_cookie","portfolio"}
    if isinstance(value,dict):
        if any(key.lower() in denied for key in value):
            raise ValueError("Personal or credential fields are not accepted")
        for item in value.values():
            reject_personal_or_secrets(item)
    elif isinstance(value,list):
        for item in value:
            reject_personal_or_secrets(item)


def artifact(root, entry, category):
    path = root/entry["path"]
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Artifact escapes its verified recovery directory")
    if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
        raise ValueError("Artifact failed hash or size verification")
    key = hashlib.sha256((category+"\0"+entry["path"]+"\0"+entry["sha256"]).encode()).hexdigest()
    return {"archive_key":key,"category":category,"original_path":entry["path"],
            "source_sha256":entry["sha256"],"source_bytes":entry["bytes"],"path":path}


def read_capture(root):
    manifest = json.loads((root/"manifest.json").read_text())
    if manifest.get("personal_data_included") is not False or manifest.get("database_writes") is not False:
        raise ValueError("Unexpected capture classification")
    files=[];profiles=[];markets=[]
    baseline = {row["name"]:row for row in json.loads((ROOT/"backup_live_recovery_20261022/baseline/company.json").read_text())}
    for entry in manifest["files"]:
        if entry["path"] != "market_snapshot.json" and not entry["path"].startswith(("profiles/","prior_profiles/")):
            raise ValueError("Unknown capture artifact")
        file = artifact(root,entry,"public_source")
        payload = json.loads(file["path"].read_text())
        reject_personal_or_secrets(payload)
        files.append(file)
        if entry["path"].startswith('prior_profiles/'):
            continue
        if entry["path"] == "market_snapshot.json":
            markets.append({"id":entry["sha256"],"captured_at":payload["retrieved_at_utc"],"snapshot":payload})
        else:
            profile = payload["profile"]
            old = baseline[profile["c_name"]]
            origins = {}
            for field in ("description","sector","ext_name","shareholders"):
                if not profile.get(field) and old.get(field):
                    value = old[field]
                    profile[field] = json.loads(value) if field=="shareholders" and isinstance(value,str) else value
                    origins[field] = "saved_Appwrite_baseline"
                elif profile.get(field):
                    origins[field] = "captured_public_source"
            profile["field_origins"] = origins
            # Do not blend missing new fiscal-year calculations with old annual
            # figures. Original company scalars remain in public.company.
            profiles.append(profile)
    issuer_root = root/'issuer_gaps'
    if (issuer_root/'manifest.json').exists():
        issuer_manifest = json.loads((issuer_root/'manifest.json').read_text())
        by_symbol = {profile['symbol']:profile for profile in profiles}
        seen = set()
        for entry in issuer_manifest['files']:
            symbol = entry['symbol']
            if symbol in seen or symbol not in by_symbol:
                raise ValueError('Duplicate or unknown official issuer')
            seen.add(symbol)
            file = artifact(issuer_root, entry, 'official_issuer_record')
            # Include the directory in archive identities and paths.
            archived_entry = dict(entry, path='issuer_gaps/'+entry['path'])
            files.append(artifact(root, archived_entry, 'official_issuer_record'))
            disclosure = parse_issuer(file['path'].read_bytes(), by_symbol[symbol]['c_name'])
            merge_issuer(by_symbol[symbol], disclosure, entry.get('captured_at', issuer_manifest['captured_at']), entry['sha256'])
    reviewed = subprocess.run(["php",str(ROOT/"tools/export_market_reference.php")],
        input=json.dumps({"profiles":profiles}),text=True,capture_output=True,timeout=30)
    if reviewed.returncode:
        raise ValueError("Public reference/review export failed")
    result = json.loads(reviewed.stdout)
    reject_personal_or_secrets(result)
    rows = [{"id":profile["symbol"],"c_name":profile["c_name"],
             "captured_at":profile["captured_at"],"profile":profile} for profile in result["profiles"]]
    return files,rows,markets,result["reference"]


def prepare(capture):
    archive_root = ROOT/"backup_live_20261022_101401"
    manifest = json.loads((archive_root/"manifest.json").read_text())
    by_path = {entry["path"]:entry for entry in manifest["files"]}
    downloaded = json.loads((archive_root/"object_download_report.json").read_text())["objects"]
    files=[];latest={};orderbook_records=0
    for entry in downloaded:
        if entry["kind"] != "storage_file":
            continue  # Function variables and deployment sources are excluded.
        if entry["status"] != "downloaded" or not entry["storage_signature_verified"]:
            raise ValueError("Storage verification is incomplete")
        file = artifact(archive_root,by_path[entry["path"]],"market_storage")
        files.append(file)
        with gzip.open(file["path"],"rt") as stream:
            for line in stream:
                row=json.loads(line)
                reject_personal_or_secrets(row)
                if row.get("schema_version") != "orderbook-v1":
                    raise ValueError("Unknown market archive schema")
                captured = datetime.fromisoformat(row["received_at"].replace("Z","+00:00"))
                if captured.tzinfo is None:
                    raise ValueError("Archive capture timestamp needs timezone")
                key=hashlib.sha256((row["source"]+"\0"+row["symbol"]).encode()).hexdigest()
                public_row={k:v for k,v in row.items() if k not in {"source","collector_id"}}
                candidate={"id":key,"symbol":row["symbol"],"captured_at":captured.isoformat(),"snapshot":public_row}
                if key not in latest or captured > datetime.fromisoformat(latest[key]["captured_at"]):
                    latest[key]=candidate
                orderbook_records+=1
    # Preserve original object metadata too, without function settings/keys.
    for path,entry in by_path.items():
        if path.startswith("storage/orderbook-history/") and path.endswith(".json"):
            files.append(artifact(archive_root,entry,"market_storage_metadata"))
    source_files,profiles,markets,reference=read_capture(capture)
    files.extend(source_files)
    calendars=[]
    prior=ROOT/'backup_live_public_20261022'
    prior_manifest=json.loads((prior/'manifest.json').read_text())
    for entry in prior_manifest['files']:
        file=artifact(prior,entry,'previous_public_source')
        files.append(file)
        payload=json.loads(file['path'].read_text())
        reject_personal_or_secrets(payload)
        if entry['path']=='market_snapshot.json':
            markets.append({'id':entry['sha256'],'captured_at':payload['retrieved_at_utc'],'snapshot':payload})
        elif entry['path'].startswith('dividends/') and not entry['path'].endswith('_raw.json'):
            calendars.append({'id':entry['sha256'],'payment_year':payload['payment_year'],
                              'captured_at':payload['retrieved_at_utc'],'calendar':payload})
    recovery=ROOT/"backup_live_recovery_20261022"
    recovery_manifest=json.loads((recovery/"manifest.json").read_text())
    entry=next(e for e in recovery_manifest["files"] if e["path"]=="independent_daily_history.parquet")
    files.append(artifact(recovery,entry,"independent_daily_history"))
    config=local_config(ROOT/'.supabase-migration.env')
    secrets=[config.get('SUPABASE_SECRET_KEY',''),config.get('SUPABASE_DATABASE_URL',''),
             connection_options(config).get('password','')]
    for filename in ('.appwrite-ops-key','.appwrite-orderbook-key'):
        path=ROOT/filename
        if path.is_file():secrets.append(path.read_text().strip())
    users=set()
    for name in ('achats','ventes','portefeuille','benefits'):
        for row in json.loads((recovery/'baseline'/(name+'.json')).read_text()):
            if row.get('user_id'):users.add(row['user_id'])
    diagnostics={};diagnostic_counts={}
    for name in ('errors','error_log'):
        path=recovery/'baseline'/(name+'.json')
        records,counts=sanitized_diagnostics(json.loads(path.read_text()),users,secrets)
        diagnostics[name]={'records':records,'original_sha256':sha256(path),**counts}
        diagnostic_counts[name]=counts
    diagnostic_path=capture/'nonpersonal_diagnostics.json'
    diagnostic_path.write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n')
    files.append(artifact(capture,{'path':diagnostic_path.name,'bytes':diagnostic_path.stat().st_size,
        'sha256':sha256(diagnostic_path)},'nonpersonal_diagnostics'))
    rows={"company_profiles":profiles,"market_snapshots":markets,
          "market_reference":[{"id":"sector_and_reviewed_filings","captured_at":datetime.now(timezone.utc).isoformat(),"reference":reference}],
          "market_orderbooks":list(latest.values()),"dividend_source_snapshots":calendars}
    return files,rows,{"archive_files":len(files),"archive_bytes":sum(f["source_bytes"] for f in files),
        "original_storage_files":sum(f["category"]=="market_storage" for f in files),
        "orderbook_records_preserved":orderbook_records,"tables":{name:len(value) for name,value in rows.items()},
        "diagnostics":diagnostic_counts,
        "personal_data_included":False,"existing_recovery_tables_modified":False}


def apply(config,files,rows):
    fields={"company_profiles":("id","c_name","captured_at","profile"),
            "market_snapshots":("id","captured_at","snapshot"),
            "market_reference":("id","captured_at","reference"),
            "market_orderbooks":("id","symbol","captured_at","snapshot"),
            "dividend_source_snapshots":("id","payment_year","captured_at","calendar")}
    with psycopg.connect(**connection_options(config)) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS required")
        connection.execute("SET LOCAL statement_timeout='300s'")
        connection.execute("SET LOCAL lock_timeout='10s'")
        connection.execute("SELECT pg_advisory_xact_lock(182736451,4)")
        before=connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        if before>LIMIT:
            raise ValueError("Database exceeds recovery size target")
        schema=connection.execute("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='recovery_archive'").fetchone()
        if schema is not None and schema!=(MARKER,):
            raise ValueError("Refusing unrelated archive schema")
        for table in ["recovery_archive.files",*("public."+t for t in TABLES)]:
            existing=connection.execute("SELECT to_regclass(%s),obj_description(to_regclass(%s),'pg_class')",(table,table)).fetchone()
            if existing[0] is not None and existing[1]!=MARKER:
                raise ValueError("Refusing unrelated table")
        connection.execute((ROOT/"migrations/supabase/004_nonpersonal_archive.sql").read_text(),prepare=False)
        existing_keys={row[0] for row in connection.execute("SELECT archive_key FROM recovery_archive.files")}
        missing=[file for file in files if file["archive_key"] not in existing_keys]
        added=len(missing)
        with connection.cursor() as cursor:
            with cursor.copy("COPY recovery_archive.files(archive_key,category,original_path,source_sha256,source_bytes,content) FROM STDIN") as copy:
                for file in missing:
                    content=file["path"].read_bytes()
                    if hashlib.sha256(content).hexdigest()!=file["source_sha256"]:
                        raise ValueError("Archive changed during restoration")
                    copy.write_row((file["archive_key"],file["category"],file["original_path"],file["source_sha256"],file["source_bytes"],content))
        expected={file["archive_key"]:file for file in files}
        with connection.cursor(name="archive_verify") as cursor:
            cursor.itersize=100
            cursor.execute("SELECT archive_key,category,original_path,source_sha256,source_bytes,content FROM recovery_archive.files WHERE archive_key=ANY(%s)",(list(expected),))
            verified=0
            for key,category,path,digest,size,content in cursor:
                file=expected.pop(key,None)
                if file is None:
                    continue  # Older capture versions remain preserved.
                if (category,path,digest,size)!=(file["category"],file["original_path"],file["source_sha256"],file["source_bytes"]) or hashlib.sha256(content).hexdigest()!=digest:
                    raise ValueError("Restored archive differs from original")
                verified+=1
        if expected:
            raise ValueError("Archive restoration incomplete")
        for table,table_rows in rows.items():
            columns=fields[table]
            for row in table_rows:
                payload=[Jsonb(row[c]) if isinstance(row[c],dict) else row[c] for c in columns]
                update=sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in columns if c!='id')
                connection.execute(sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) ON CONFLICT(id) DO UPDATE SET {} WHERE EXCLUDED.captured_at>=public.{}.captured_at").format(
                    sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),
                    sql.SQL(',').join(sql.Placeholder() for _ in columns),update,sql.Identifier(table)),payload)
                saved=connection.execute(sql.SQL("SELECT {} FROM public.{} WHERE id=%s").format(
                    sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table)),(row['id'],)).fetchone()
                for c,value in zip(columns,saved):
                    target=row[c]
                    if c=='captured_at':
                        target=datetime.fromisoformat(target)
                    if value!=target:
                        raise ValueError("Supplemental read-back mismatch")
        for role in ('anon','authenticated','service_role'):
            if connection.execute("SELECT has_schema_privilege(%s,'recovery_archive','USAGE') OR has_table_privilege(%s,'recovery_archive.files','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",(role,role)).fetchone()[0]:
                raise ValueError("Archive must remain admin-only")
            for table in TABLES:
                grants=connection.execute("SELECT has_table_privilege(%s,%s,'SELECT'),has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE')",(role,'public.'+table,role,'public.'+table)).fetchone()
                if grants!=(True,False):
                    raise ValueError("Unexpected supplemental grants")
        after=connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        if after>LIMIT:
            raise ValueError("Restoration exceeds recovery size target")
        connection.execute("NOTIFY pgrst,'reload schema'")
    return {"archive_files_added":added,"archive_files_byte_verified":verified,"database_bytes_before":before,
            "database_bytes_after":after,"archive_access_admin_only":True,"public_supplemental_read_only":True}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,default=ROOT/'backup_live_nonpersonal_20261024')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        files,rows,report=prepare(args.capture)
        if args.apply:
            report['target']=apply(local_config(ROOT/'.supabase-migration.env'),files,rows)
        report['mode']='applied' if args.apply else 'local_validation'
        (args.capture/'restoration_report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    except Exception as error:
        print(json.dumps({'ok':False,'error_category':type(error).__name__}),flush=True)
        raise SystemExit(1)
