"""Confirmed-email recovery on fresh synthetic /tmp PostgreSQL only."""
import json
import os
from pathlib import Path
import unittest
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import test_combined_deployment_sql as baseline

ROOT=Path(__file__).resolve().parents[1]
TARGET='33333333-3333-4333-8333-333333333333'
OTHER='44444444-4444-4444-8444-444444444444'
COLLECTIONS=('achats','ventes','portefeuille','benefits')


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated database not configured')
class SavedPortfolioClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options=conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not options.get('host','').startswith('/tmp/'):
            raise RuntimeError('Only isolated /tmp PostgreSQL permitted')
        cls.db=psycopg.connect(**options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0] is not None:
            raise RuntimeError('Fresh synthetic database required')
        baseline.baseline(cls.db)
        cls.db.execute("ALTER TABLE auth.users ADD COLUMN email text,ADD COLUMN email_confirmed_at timestamptz")
        cls.db.execute("CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS $$ SELECT coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$")
        cls.db.execute("INSERT INTO auth.users VALUES(%s,'one@example.invalid',clock_timestamp()),(%s,'two@example.invalid',clock_timestamp())",(TARGET,OTHER))
        for path in ('001_staging.sql','019_saved_portfolio_claims.sql'):
            if path.startswith('001'):
                path=next((ROOT/'migrations/supabase').glob('001*')).name
            cls.db.execute((ROOT/'migrations/supabase'/path).read_text())
        for i,collection in enumerate(COLLECTIONS,1):
            dataset=str(i)*64
            cls.db.execute('INSERT INTO migration_stage.datasets(dataset_id,dataset_name,source_kind,source_sha256,source_bytes,row_count,source_metadata) VALUES(%s,%s,\'fixture\',%s,10,2,%s)',
                (dataset,collection,'a'*64,Jsonb({'collection':collection})))
            for owner in ('one','two'):
                payload={'$id':owner+'-'+collection,'$collectionId':collection,'user_id':owner,'c_name':'Alpha',
                    'date':'2025-01-01T00:15:00+01:00','number':2,'prix_achat':10,'prix_vente':12,
                    'quantity':7,'total_cost':99,'value':-7.5}
                cls.db.execute('INSERT INTO migration_stage.documents VALUES(%s,%s,%s)',(dataset,payload['$id'],Jsonb(payload)))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls): cls.db.rollback();cls.db.close()

    def setUp(self): self.db.execute("SAVEPOINT case_start; SET LOCAL statement_timeout='5s'")
    def tearDown(self): self.db.execute('ROLLBACK TO SAVEPOINT case_start; RESET ROLE; RELEASE SAVEPOINT case_start')

    def binding(self,owner='one',email='one@example.invalid'):
        rows=self.db.execute("SELECT jsonb_agg(jsonb_build_object('dataset_id',d.dataset_id,'document_id',d.document_id,'collection',s.source_metadata->>'collection','dataset_sha256',s.source_sha256,'payload_sha256',encode(sha256(convert_to(d.payload::text,'UTF8')),'hex')) ORDER BY d.dataset_id,d.document_id) FROM migration_stage.documents d JOIN migration_stage.datasets s USING(dataset_id) WHERE payload->>'user_id'=%s",(owner,)).fetchone()[0]
        datasets=self.db.execute("SELECT jsonb_agg(jsonb_build_object('dataset_id',dataset_id,'collection',source_metadata->>'collection','dataset_sha256',source_sha256) ORDER BY dataset_id) FROM migration_stage.datasets").fetchone()[0]
        pins={'email':email,'legacy_owner':owner,'source_datasets':datasets,'source_rows':rows}
        plan=self.db.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(Jsonb(pins),)).fetchone()[0]
        return self.db.execute('INSERT INTO portfolio_private.recovery_bindings(email,legacy_owner,source_datasets,source_rows,plan_sha256,enabled) VALUES(%s,%s,%s,%s,%s,true) RETURNING id',
            (email,owner,Jsonb(datasets),Jsonb(rows),plan)).fetchone()[0]

    def enabled(self): self.db.execute('UPDATE portfolio_private.recovery_control SET enabled=true')
    def claim(self,target=TARGET,method='password'):
        self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('request.jwt.claim.role','authenticated',true)",(target,))
        self.db.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps({'amr':[{'method':method}]}),))
        self.db.execute('SET LOCAL ROLE authenticated')
        try: return self.db.execute('SELECT public.claim_saved_portfolio()').fetchone()[0]
        finally:
            if self.db.info.transaction_status != psycopg.pq.TransactionStatus.INERROR:
                self.db.execute('RESET ROLE')

    def counts(self,target=TARGET):
        return [self.db.execute('SELECT count(*) FROM public.'+name+' WHERE user_id=%s',(target,)).fetchone()[0] for name in COLLECTIONS]

    def test_disabled_recovery_has_no_side_effect(self):
        self.binding();self.assertEqual(self.claim(),{'status':'DISABLED'});self.assertEqual(self.counts(),[0]*4)

    def test_matching_confirmed_email_recovers_original_snapshots_and_provenance(self):
        self.binding();self.enabled();before=baseline.snapshot(self.db)
        receipt=self.claim()
        self.assertEqual(receipt['status'],'CLAIMED');self.assertEqual(self.counts(),[1]*4)
        self.assertEqual(self.db.execute('SELECT quantity,total_cost FROM public.portefeuille WHERE user_id=%s',(TARGET,)).fetchone(),(7,99))
        self.assertEqual(self.db.execute('SELECT value,date::text FROM public.benefits WHERE user_id=%s',(TARGET,)).fetchone(),(-7.5,'2025-01-01'))
        self.assertEqual(self.db.execute('SELECT original_payload->>\'date\' FROM portfolio_private.recovery_provenance WHERE collection=\'benefits\'').fetchone()[0],'2025-01-01T00:15:00+01:00')
        self.assertEqual(self.db.execute('SELECT count(*) FROM migration_stage.documents').fetchone()[0],8)

    def test_unverified_or_different_email_cannot_claim(self):
        self.binding();self.enabled()
        self.db.execute('UPDATE auth.users SET email_confirmed_at=NULL WHERE id=%s',(TARGET,))
        self.assertEqual(self.claim()['status'],'NOT_AVAILABLE')
        self.assertEqual(self.claim(OTHER)['status'],'NOT_AVAILABLE');self.assertEqual(self.counts(),[0]*4)

    def test_two_independent_owners_claim_their_own_records(self):
        self.binding();self.binding('two','two@example.invalid');self.enabled()
        self.assertEqual(self.claim()['status'],'CLAIMED');self.assertEqual(self.claim(OTHER)['status'],'CLAIMED')
        self.assertEqual(self.counts(OTHER),[1]*4)
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.recovery_receipts').fetchone()[0],2)

    def test_first_recovery_requires_password_login_not_an_email_or_recovery_token(self):
        self.binding();self.enabled()
        for method in ('recovery','otp','email/signup'):
            self.assertEqual(self.claim(method=method),{'status':'PASSWORD_REQUIRED'})
            self.assertEqual(self.counts(),[0]*4)
        self.assertEqual(self.claim()['status'],'CLAIMED')

    def test_empty_source_collection_is_preserved_as_empty_not_invented(self):
        self.db.execute("DELETE FROM migration_stage.documents WHERE payload->>'user_id'='one' AND payload->>'$collectionId' IN ('ventes','benefits')")
        self.binding();self.enabled()
        value=self.claim()
        self.assertEqual(value['status'],'CLAIMED')
        self.assertEqual(self.counts(),[1,0,1,0])
        self.assertEqual(value['counts'],{'achats':1,'ventes':0,'portefeuille':1,'benefits':0})

    def test_exact_retry_is_idempotent_even_after_new_legitimate_trades(self):
        self.binding();self.enabled();first=self.claim()
        self.db.execute("INSERT INTO public.achats VALUES(gen_random_uuid(),%s,'Alpha',1,11,clock_timestamp())",(TARGET,))
        self.assertEqual(self.claim(),first);self.assertEqual(self.counts(),[2,1,1,1])

    def test_existing_target_account_is_never_overwritten_or_merged(self):
        self.binding();self.enabled()
        self.db.execute("INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES(%s,'Alpha',3,30)",(TARGET,))
        self.assertEqual(self.claim()['status'],'REVIEW_REQUIRED');self.assertEqual(self.counts(),[0,0,1,0])

    def test_changed_source_aborts_without_partial_financial_writes(self):
        self.binding();self.enabled()
        self.db.execute("UPDATE migration_stage.documents SET payload=jsonb_set(payload,'{value}','999') WHERE payload->>'user_id'='one' AND payload->>'$collectionId'='benefits'")
        with self.assertRaises(psycopg.errors.InvalidParameterValue),self.db.transaction(): self.claim()
        self.assertEqual(self.counts(),[0]*4)
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.recovery_provenance').fetchone()[0],0)

    def test_bad_late_source_value_rolls_back_all_earlier_rows(self):
        self.db.execute("UPDATE migration_stage.documents SET payload=jsonb_set(payload,'{value}','\"bad\"') WHERE payload->>'user_id'='one' AND payload->>'$collectionId'='benefits'")
        self.binding();self.enabled()
        with self.assertRaises(psycopg.errors.InvalidTextRepresentation),self.db.transaction(): self.claim()
        self.assertEqual(self.counts(),[0]*4)

    def test_naive_original_timestamp_is_refused(self):
        self.db.execute("UPDATE migration_stage.documents SET payload=jsonb_set(payload,'{date}','\"2025-01-01T00:15:00\"') WHERE payload->>'user_id'='one' AND payload->>'$collectionId'='achats'")
        self.binding();self.enabled()
        with self.assertRaises(psycopg.errors.InvalidParameterValue),self.db.transaction(): self.claim()
        self.assertEqual(self.counts(),[0]*4)

    def test_bindings_and_source_data_are_inaccessible_to_all_application_roles(self):
        for role in ('anon','authenticated','service_role'):
            for table in ('recovery_control','recovery_bindings','recovery_receipts','recovery_provenance'):
                self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",(role,'portfolio_private.'+table)).fetchone()[0])
            self.assertEqual(self.db.execute("SELECT has_function_privilege(%s,'public.claim_saved_portfolio()','EXECUTE')",(role,)).fetchone()[0],role=='authenticated')
