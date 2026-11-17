"""Bounded sanitized session reads using fictional source bars only."""
import os,json,unittest
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import test_combined_deployment_sql as baseline

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated PostgreSQL required')
class RecentSessionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options=conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not options.get('host','').startswith('/tmp/'):raise ValueError('Isolated database required')
        cls.db=psycopg.connect(**options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0]:raise ValueError('Fresh database required')
        baseline.baseline(cls.db)
        cls.db.execute((ROOT/'migrations/supabase/024_recent_market_sessions.sql').read_text());cls.db.commit()

    @classmethod
    def tearDownClass(cls):cls.db.rollback();cls.db.close()
    def setUp(self):
        self.db.execute('SAVEPOINT case_start')
        self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('request.jwt.claim.role','authenticated',true)",(baseline.OWNER,))
    def tearDown(self):self.db.execute('RESET ROLE;ROLLBACK TO SAVEPOINT case_start;RELEASE SAVEPOINT case_start')
    def read(self,symbol='AAA',limit=5):return self.db.execute('SELECT public.read_recent_market_sessions(%s,%s)',(symbol,limit)).fetchone()[0]
    def daily(self,day='2026-10-20',name='Alpha'):
        self.db.execute("INSERT INTO public.daily_price_reference VALUES(%s,%s,'AAA',%s,10,%s,'{}',%s)",
            ('daily-'+day+name,name,day,Jsonb({'open':9,'high':11,'low':8,'quantity_traded':2,'volume_mad':1000}),'a'*64))
    def history(self,delta=False):
        manifest={'contract':'private-source-history-v1','bindings':{'open_field':'field_a','high_field':'field_b','low_field':'field_c','provider_url':'private.invalid'}}
        if delta:manifest={'contract':'private-source-history-delta-v2','full_source_manifest':manifest}
        self.db.execute('INSERT INTO market_history_v1.batches VALUES(%s,%s,clock_timestamp())',('b'*64,Jsonb(manifest)))
        self.db.execute("INSERT INTO market_history_v1.captures VALUES(%s,'AAA','2026-10-21T18:00Z',%s,%s,%s,'x','y','z')",('b'*64,'c'*64,'d'*64,'e'*64))
        self.db.execute("INSERT INTO market_history_v1.observations(batch_id,symbol,source_ordinal,observation_id,period_day,source_daily_label,close_text,bar,quality_warnings) VALUES(%s,'AAA',0,%s,'2026-10-21','native-day','12',%s,'{}')",('b'*64,'f'*64,Jsonb({'field_a':11,'field_b':13,'field_c':10,'native_volume':1200,'private_endpoint':'private.invalid'})))

    def test_daily_reference_uses_shares_never_monetary_volume(self):
        self.daily();row=self.read()['candidates'][0]
        self.assertEqual((row['price'],row['quantity'],row['open']),('10','2','9'))
        self.assertNotIn('volume_mad',json.dumps(row))

    def test_private_history_is_sanitized_and_missing_quantity_stays_null(self):
        self.history();self.db.execute('SET LOCAL ROLE authenticated')
        row=self.read()['candidates'][0]
        self.assertEqual((row['price'],row['open'],row['high'],row['low']),('12','11','13','10'))
        self.assertIsNone(row['quantity']);text=json.dumps(row)
        self.assertNotIn('private.invalid',text);self.assertNotIn('field_a',text)

    def test_current_delta_manifest_keeps_real_ohlc_and_unknown_contract_is_not_guessed(self):
        self.history(delta=True)
        self.assertEqual(self.read()['candidates'][0]['open'],'11')
        self.db.execute("UPDATE market_history_v1.batches SET manifest=jsonb_set(manifest,'{contract}','\"unknown\"')")
        self.assertEqual(self.read()['candidates'],[])

    def test_future_capture_does_not_crowd_out_older_daily_sessions_or_expose_native_issue(self):
        self.history();self.daily('2026-10-20')
        self.db.execute("UPDATE market_history_v1.captures SET completed_at='2099-01-01'")
        self.assertEqual(self.read(limit=1)['candidates'][0]['day'],'2026-10-20')
        self.db.execute("UPDATE public.daily_price_reference SET quality=%s",(Jsonb({'issues':['private.invalid']}),))
        self.assertEqual(self.read()['candidates'][0]['issues'],['SOURCE_QUALITY_UNCLASSIFIED'])

    def test_newest_distinct_actual_days_ignore_future_and_wrong_company(self):
        for d in ['17','18','19','20','21','22']:self.daily('2026-10-'+d)
        self.daily('2099-01-01');self.daily('2026-10-23','Wrong issuer')
        result=self.read()['candidates']
        self.assertEqual([r['day'] for r in result],['2026-10-22','2026-10-21','2026-10-20','2026-10-19','2026-10-18'])

    def test_anonymous_invalid_symbol_and_excess_limit_are_denied(self):
        with self.assertRaises(psycopg.Error),self.db.transaction():
            self.db.execute('SET LOCAL ROLE anon');self.read()
        for symbol,limit in [('bad symbol',5),('AAA',0),('AAA',21)]:
            with self.assertRaises(psycopg.Error),self.db.transaction():self.read(symbol,limit)

    def test_native_numeric_parser_never_returns_nonfinite_or_unbounded_values(self):
        for value in [True,'NaN','Infinity','1e999','1,2',{},None]:
            self.assertIsNone(self.db.execute('SELECT market_history_v1.session_number(%s)',(Jsonb(value),)).fetchone()[0])
