from pathlib import Path
import test_subject_archive_sql as subject
import test_manual_trial_sql as legacy


class EnrichmentContextSQLTests(subject.SubjectArchiveSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.execute((Path(__file__).resolve().parents[1]/'migrations/supabase/018_enrichment_context.sql').read_text())
        cls.db.commit()

    def context(self,index='a'*64):
        return self.db.execute('SELECT public.read_enrichment_context(%s,%s)',(legacy.PROVIDER,index)).fetchone()[0]

    def prepare_context(self):
        self.enabled()
        self.issue(kinds=['fundamentals'],seconds=900,capabilities=['archive','projections'])
        self.db.execute("UPDATE app_projection.control SET enabled=true,provider_namespace=%s,dividend_index_sha256=repeat('b',64),fundamental_index_sha256=repeat('a',64)",(legacy.PROVIDER,))

    def test_context_is_fresh_minimal_and_leaves_every_original_record_unchanged(self):
        self.prepare_context()
        before=legacy.baseline.snapshot(self.db)
        self.db.execute('SET LOCAL ROLE service_role')
        value=self.context()
        self.db.execute('RESET ROLE')
        self.assertEqual(set(value),{'contract','provider_namespace','index_sha256','observed_at','companies','price_companies'})
        self.assertEqual(value['contract'],'private-enrichment-context/v2')
        self.assertEqual(set(value['companies']['Alpha']),{'bpa','sector','fiscal_year'})
        self.assertEqual(legacy.baseline.snapshot(self.db),before)

    def test_new_financial_availability_is_separate_from_original_company_date(self):
        self.prepare_context()
        self.subject_stored('a'*64)
        self.db.execute("INSERT INTO app_projection.accepted_rows VALUES(%s,'fundamentals',encode(sha256(convert_to(jsonb_build_array('Alpha')::text,'UTF8')),'hex'),repeat('a',64),clock_timestamp(),repeat('b',64))",(legacy.PROVIDER,))
        value=self.context()['price_companies']['company-fixture']
        self.assertTrue(value['date'].startswith('2000-01-03'))
        self.assertGreater(value['available_at'],value['date'])
        self.assertEqual(self.db.execute('SELECT date::date::text FROM public.company WHERE id=\'company-fixture\'').fetchone()[0],'2000-01-03')

    def test_context_requires_current_matching_pin_and_no_application_role_can_call_it(self):
        self.prepare_context()
        self.denied('SELECT public.read_enrichment_context(%s,%s)',(legacy.PROVIDER,'f'*64))
        for role in ('anon','authenticated'):
            self.db.execute('SET LOCAL ROLE '+role)
            self.denied('SELECT public.read_enrichment_context(%s,%s)',(legacy.PROVIDER,'a'*64))
            self.db.execute('RESET ROLE')
        self.db.execute('UPDATE app_projection.control SET enabled=false')
        self.denied('SELECT public.read_enrichment_context(%s,%s)',(legacy.PROVIDER,'a'*64))
