"""Owner-only listing transactions, using synthetic /tmp data only."""
import copy
import hashlib
import os
from pathlib import Path
import sys
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'automation/managed'))
sys.path.insert(0,str(ROOT/'automation/managed/tests'))
import app_feed
import listing_plan
from test_app_feed import archive,config
from test_market_frame import body,CAPTURED
import test_combined_deployment_sql as baseline


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated database not configured')
class ReviewedListingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options=conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not options.get('host','').startswith('/tmp/'):raise RuntimeError('Only /tmp PostgreSQL permitted')
        cls.db=psycopg.connect(**options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0] is not None:raise RuntimeError('Fresh database required')
        baseline.baseline(cls.db)
        for name in ['009_private_object_archive','010_shadow_market_feed','013_projection_publication','020_reviewed_listing_updates']:
            cls.db.execute((ROOT/f'migrations/supabase/{name}.sql').read_text())
        cls.db.execute("INSERT INTO app_archive.providers(namespace) VALUES('feed_0123456789abcdef')")
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):cls.db.rollback();cls.db.close()
    def setUp(self):self.db.execute("SAVEPOINT listing_case; SET LOCAL statement_timeout='5s'")
    def tearDown(self):self.db.execute('RESET ROLE; ROLLBACK TO SAVEPOINT listing_case; RELEASE SAVEPOINT listing_case')

    def prepare(self, rows=None, execution='CURRENT_ACQUISITION'):
        data=body();data['catalog']=rows or [
            {'key':'AAA','symbol':'AAA','name':'Alpha','p':'10,50'},
            {'key':'NEW','symbol':'NEW','name':'Nouvelle Société','p':'20,00'}]
        cfg=config();digest,blob=archive(data,cfg,execution=execution)
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at) VALUES(%s,%s,'quotes',%s,%s,'INCOMPLETE',%s,%s,'STORED',clock_timestamp()) ON CONFLICT DO NOTHING",
            (digest,cfg['provider_namespace'],CAPTURED,CAPTURED,len(blob),'sha256/'+digest[:2]+'/'+digest+'.json.gz'))
        fingerprint=self.db.execute(listing_plan.catalog_fingerprint_sql()).fetchone()[0]
        self.assertEqual(fingerprint,self.db.execute('SELECT market_maintenance.catalog_fingerprint()').fetchone()[0])
        return listing_plan.build(blob,digest,cfg,{'contract':'private-listing-bindings/v1','symbol_path':['symbol'],'name_path':['name']},
            [{'id':row[0],'name':row[1]} for row in self.db.execute('SELECT id,name FROM public.company ORDER BY id')],
            [{'symbol':row[0],'name':row[1]} for row in self.db.execute('SELECT symbol,name FROM public.format ORDER BY id')],fingerprint)

    def apply(self,plan):
        document=app_feed.canonical(plan)
        return self.db.execute('SELECT market_maintenance.apply_listing_plan(%s,%s)',
            (document,hashlib.sha256(document.encode()).hexdigest())).fetchone()[0]

    def rejected(self,plan):
        with self.assertRaises(psycopg.Error),self.db.transaction():self.apply(plan)

    def test_addition_preserves_originals_and_has_no_invented_fundamentals_or_dates(self):
        before=baseline.snapshot(self.db)
        plan=self.prepare();result=self.apply(plan)
        self.assertEqual(result['status'],'ADDED_PENDING_PROVIDER_REPIN')
        self.assertEqual((result['companies_added'],result['formats_added']),(1,1))
        row=self.db.execute("SELECT date,bpa,cp FROM public.company WHERE name='Nouvelle Société'").fetchone()
        self.assertEqual(row,(None,None,None))
        after=baseline.snapshot(self.db)
        for table,rows in before.items():
            for row in rows:self.assertIn(row,after[table])
        for table in ['data','latest_prices','benefits','portefeuille','achats','ventes','dividends']:
            self.assertEqual(after[table],before[table])
        self.assertIsNone(self.db.execute('SELECT mapping_sha256 FROM app_feed.control').fetchone()[0])

    def test_exact_retry_is_idempotent_after_catalog_changes(self):
        plan=self.prepare();first=self.apply(plan)
        self.db.execute("UPDATE public.company SET bpa=3 WHERE name='Alpha'")
        self.assertEqual(self.apply(plan),first)
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_maintenance.listing_receipts').fetchone()[0],1)

    def test_existing_company_receives_only_missing_mapping(self):
        self.db.execute("INSERT INTO public.company(id,name,bpa,date) VALUES('original-unmapped','Nouvelle Société',4,'2000-01-03T12:00Z')")
        plan=self.prepare();result=self.apply(plan)
        self.assertEqual(result['companies_added'],0)
        self.assertEqual(self.db.execute("SELECT id,bpa,date::text FROM public.company WHERE name='Nouvelle Société'").fetchone(),
                         ('original-unmapped',4,'2000-01-03 12:00:00+00'))

    def test_ordinary_roles_have_no_read_or_execution_access(self):
        plan=self.prepare()
        for role in ['anon','authenticated','service_role']:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():
                self.db.execute('SET LOCAL ROLE '+role);self.apply(plan)
            self.db.execute('RESET ROLE')
            self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,'market_maintenance.listing_receipts','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0])

    def test_changed_catalog_and_legacy_replay_fail_closed(self):
        plan=self.prepare();self.db.execute("UPDATE public.company SET bpa=99 WHERE name='Alpha'")
        self.rejected(plan)
        self.rejected(self.prepare(execution='RECORDED_REPLAY'))

    def test_enabled_collection_and_unstored_or_wrong_provider_archives_fail(self):
        plan=self.prepare()
        for query in ["UPDATE app_feed.control SET enabled=true,provider_namespace='feed_0123456789abcdef',mapping_sha256=repeat('a',64),recipe_sha256=repeat('a',64)",
                      "UPDATE app_archive.objects SET state='RESERVED',verified_at=NULL",
                      "UPDATE app_archive.objects SET kind='depth'"]:
            with self.db.transaction(force_rollback=True):
                self.db.execute(query);self.rejected(plan)

    def test_conflicting_catalog_requires_review(self):
        plan=self.prepare([{'key':'X','symbol':'NEW','name':'One','p':'10'},
                           {'key':'Y','symbol':'NEW','name':'Two','p':'20'}])
        self.assertTrue(plan['conflicts']);self.rejected(plan)

    def test_late_failure_rolls_back_all_additions(self):
        plan=self.prepare([{'key':'X','symbol':'ONE','name':'One','p':'10'},
                           {'key':'Y','symbol':'TWO','name':'Two','p':'20'}])
        plan['additions'][1]['format_id']='listing-format-'+'0'*64
        self.rejected(plan)
        self.assertEqual(self.db.execute("SELECT count(*) FROM public.company WHERE name IN ('One','Two')").fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_maintenance.listing_receipts').fetchone()[0],0)

    def test_bad_values_evidence_and_source_identity_cannot_be_approved(self):
        plan=self.prepare()
        for key,value in [('name',None),('symbol',True),('company_id','original-tick'),('create_company','yes'),('evidence',[])]:
            changed=copy.deepcopy(plan);changed['additions'][0][key]=value;self.rejected(changed)
        changed=copy.deepcopy(plan);changed['additions'][0]['evidence'][0]['observation_id']='bad';self.rejected(changed)
        changed=copy.deepcopy(plan);changed['captured_at']='2026-10-28T00:00:00Z';self.rejected(changed)


if __name__=='__main__':unittest.main()
