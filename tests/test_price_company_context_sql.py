"""Additive price-company inputs; fresh isolated synthetic PostgreSQL only."""
import copy,json
from pathlib import Path
import test_enrichment_context_sql as previous
import test_manual_trial_sql as legacy
import app_feed

ROOT=Path(__file__).resolve().parents[1]

class PriceCompanyContextSQLTests(previous.EnrichmentContextSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old_functions=cls.db.execute("SELECT oid,pg_get_functiondef(oid),proacl::text FROM pg_proc WHERE pronamespace IN (SELECT oid FROM pg_namespace WHERE nspname IN ('public','app_trial','app_trial_legacy','app_feed','app_projection'))").fetchall()
        cls.db.execute((ROOT/'migrations/supabase/025_price_company_context.sql').read_text());cls.db.commit()

    def price_prepare(self,capabilities=None,kinds=None):
        self.enabled();self.price_lease=self.issue(capabilities=capabilities or ['archive','shadow_feed','projections'],kinds=kinds or ['quotes'],seconds=600)
        self.price_mapping={'contract':'private-app-mapping/v1','provider_namespace':legacy.PROVIDER,
            'stocks':[{'asset_key':'company:company-fixture','company_id':'company-fixture','c_name':'Alpha','symbol':'AAA','source_identity':'A'}],
            'indices':[{'asset_key':'index:MASI','company_id':None,'c_name':'MASI','symbol':'MASI','source_identity':'INDEX'}]}
        self.set_price_mapping(self.price_mapping)
        self.db.execute('UPDATE app_feed.control SET enabled=true,provider_namespace=%s,recipe_sha256=repeat(\'b\',64)',(legacy.PROVIDER,))
        self.db.execute("UPDATE app_feed.application_control SET enabled=true,fields_sha256=repeat('c',64)")

    def set_price_mapping(self,mapping):
        self.price_document=app_feed.canonical(mapping);self.price_sha=app_feed.fingerprint(mapping)
        self.db.execute('UPDATE app_feed.control SET mapping_sha256=%s',(self.price_sha,))

    def price_request(self,**overrides):
        params={'provider':legacy.PROVIDER,'mapping_document':self.price_document,'mapping_sha256':self.price_sha,'recipe_sha256':'b'*64,'fields_sha256':'c'*64,**overrides}
        return self.db.execute('SELECT public.read_price_company_context(%s,%s,%s,%s,%s)',tuple(params.values())).fetchone()[0]

    def test_price_context_succeeds_with_same_quote_lease_and_fundamental_service_off(self):
        self.price_prepare();before=legacy.baseline.snapshot(self.db)
        self.assertFalse(self.db.execute('SELECT enabled FROM app_projection.control').fetchone()[0])
        self.db.execute('SET LOCAL ROLE service_role');value=self.price_request();self.db.execute('RESET ROLE')
        self.assertEqual(value['contract'],'private-price-company-context/v1')
        self.assertEqual(set(value['price_companies']),{'company-fixture'})
        row=value['price_companies']['company-fixture']
        self.assertEqual(set(row),{'name','bpa','tc5','roe','na','cp','net_profit','date','available_at'})
        self.assertEqual(row['date'],row['available_at']);self.assertTrue(row['date'].startswith('2000-01-03'))
        self.assertEqual(legacy.baseline.snapshot(self.db),before)
        self.assertNotIn('user_id',json.dumps(value))

    def test_price_context_retains_prior_fundamental_availability_without_enabling_provider(self):
        self.price_prepare()
        provider='feed_'+'f'*16
        self.db.execute('INSERT INTO app_archive.providers VALUES(%s,false)',(provider,))
        digest='d'*64
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at) VALUES(%s,%s,'fundamentals',clock_timestamp()-interval '2 hours',clock_timestamp()-interval '1 hour','COMPLETE',100,%s,'STORED',clock_timestamp())",(digest,provider,'sha256/dd/'+digest+'.json.gz'))
        self.db.execute("INSERT INTO app_projection.accepted_rows VALUES(%s,'fundamentals',encode(sha256(convert_to(jsonb_build_array('Alpha')::text,'UTF8')),'hex'),%s,clock_timestamp()-interval '1 hour',repeat('a',64))",(provider,digest))
        row=self.price_request()['price_companies']['company-fixture']
        self.assertTrue(row['date'].startswith('2000-01-03'));self.assertGreater(row['available_at'],row['date'])
        self.assertFalse(self.db.execute('SELECT enabled FROM app_archive.providers WHERE namespace=%s',(provider,)).fetchone()[0])

    def test_price_context_rejects_wrong_pins_missing_caps_kinds_and_expiry(self):
        self.price_prepare()
        for change in [{'mapping_sha256':'f'*64},{'recipe_sha256':'f'*64},{'fields_sha256':'f'*64},{'provider':'feed_'+'f'*16}]:
            with self.subTest(change=change),self.assertRaises(Exception),self.db.transaction():self.price_request(**change)
        for caps in [['archive'],['archive','shadow_feed'],['archive','projections']]:
            self.db.execute('UPDATE app_trial.leases SET capabilities=%s WHERE id=%s',(caps,self.price_lease))
            with self.assertRaises(Exception),self.db.transaction():self.price_request()
        self.db.execute('UPDATE app_trial.leases SET capabilities=%s,kinds=%s WHERE id=%s',(['archive','shadow_feed','projections'],['fundamentals'],self.price_lease))
        with self.assertRaises(Exception),self.db.transaction():self.price_request()
        self.db.execute('UPDATE app_trial.leases SET kinds=%s,revoked_at=clock_timestamp() WHERE id=%s',(['quotes'],self.price_lease))
        with self.assertRaises(Exception),self.db.transaction():self.price_request()

    def test_price_context_rejects_disabled_controls_and_ambiguous_current_mapping(self):
        self.price_prepare()
        for table in ['app_feed.control','app_feed.application_control','app_archive.control']:
            self.db.execute('UPDATE '+table+' SET enabled=false')
            with self.assertRaises(Exception),self.db.transaction():self.price_request()
            self.db.execute('UPDATE '+table+' SET enabled=true')
        self.db.execute("INSERT INTO public.format VALUES('duplicate-symbol','Other','AAA')")
        with self.assertRaises(Exception),self.db.transaction():self.price_request()

    def test_price_context_rejects_approved_but_incorrect_identity_document(self):
        self.price_prepare()
        for change in [{'c_name':'Other'},{'symbol':'WRONG'},{'company_id':'missing','asset_key':'company:missing'}]:
            bad=copy.deepcopy(self.price_mapping);bad['stocks'][0].update(change);self.set_price_mapping(bad)
            with self.assertRaises(Exception),self.db.transaction():self.price_request()

    def test_price_context_is_service_only_and_old_contracts_unchanged(self):
        signature='public.read_price_company_context(text,text,text,text,text)'
        for role in ['anon','authenticated','service_role']:
            self.assertEqual(self.db.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')",(role,signature)).fetchone()[0],role=='service_role')
        for oid,body,acl in self.old_functions:
            self.assertEqual(self.db.execute('SELECT pg_get_functiondef(%s),proacl::text FROM pg_proc WHERE oid=%s',(oid,oid)).fetchone(),(body,acl))
