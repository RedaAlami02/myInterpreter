"""Isolated display-only reference acceptance. No genuine financial records."""
import hashlib,os,unittest
from pathlib import Path
import psycopg

class VerifiedCloseDisplayTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=psycopg.connect(os.environ['APP_TEST_DATABASE'])
  cls.db.execute('CREATE SCHEMA IF NOT EXISTS auth;CREATE SCHEMA app_feed;CREATE SCHEMA portfolio_private')
  cls.db.execute("CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$")
  cls.db.execute('CREATE TABLE public.latest_prices(id text,c_name text,pa numeric,date timestamptz,origin_collection text)')
  cls.db.execute('CREATE TABLE portfolio_private.official_close_batches(sha256 text,session_day date,document jsonb,reviewed_at timestamptz)')
  cls.db.execute("INSERT INTO public.latest_prices VALUES('original','SGTM',580,'2026-10-21T09:29:37Z','data'),('other','Other',10,'2026-10-21T09:29:37Z','data')")
  cls.db.execute((Path(__file__).resolve().parents[1]/'migrations/supabase/029_verified_close_display.sql').read_text());cls.db.commit()
 @classmethod
 def tearDownClass(cls):cls.db.close()
 def setUp(self):
  self.db.execute("SET LOCAL request.jwt.claim.sub='11111111-1111-4111-8111-111111111111'")
 def tearDown(self):self.db.rollback()
 def seed(self):
  raw=b'%PDF synthetic isolated evidence';sha=hashlib.sha256(raw).hexdigest()
  self.db.execute("INSERT INTO app_feed.recovered_close_reports(raw_sha256,raw_pdf,session_day,captured_at,verified_at,parser_sha256,policy_sha256,identity_sha256,rows) VALUES(%s,%s,'2026-11-03','2026-11-03T19:23:21Z',clock_timestamp(),repeat('a',64),repeat('b',64),repeat('c',64),'[{\"company_id\":\"fixture\",\"c_name\":\"SGTM\",\"price_decimal\":\"524.00\"}]')",(sha,raw))
 def rows(self):return {r[1]:r for r in self.db.execute('SELECT * FROM public.read_latest_price_references_v1()').fetchall()}
 def test_verified_close_overlays_old_reference_without_rewriting_original(self):
  self.seed();r=self.rows();self.assertEqual(r['SGTM'][2],524);self.assertEqual(r['Other'][2],10)
  self.assertEqual(self.db.execute("SELECT pa FROM public.latest_prices WHERE id='original'").fetchone()[0],580)
 def test_unknown_caller_rejected(self):
  self.db.execute("SET LOCAL request.jwt.claim.sub=''")
  with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():self.rows()
 def test_private_evidence_and_rpc_acl(self):
  self.assertFalse(self.db.execute("SELECT has_table_privilege('authenticated','app_feed.recovered_close_reports','SELECT')").fetchone()[0])
  self.assertFalse(self.db.execute("SELECT has_function_privilege('anon','public.read_latest_price_references_v1()','EXECUTE')").fetchone()[0])
  self.assertFalse(self.db.execute("SELECT has_function_privilege('service_role','public.read_latest_price_references_v1()','EXECUTE')").fetchone()[0])
  self.assertTrue(self.db.execute("SELECT has_function_privilege('authenticated','public.read_latest_price_references_v1()','EXECUTE')").fetchone()[0])
 def test_future_verified_time_is_not_displayed(self):
  self.seed();self.db.execute("UPDATE app_feed.recovered_close_reports SET verified_at=clock_timestamp()+interval '1 day'")
  self.assertEqual(self.rows()['SGTM'][2],580)
 def test_raw_integrity_required(self):
  self.seed()
  with self.assertRaises(psycopg.errors.CheckViolation),self.db.transaction():self.db.execute("UPDATE app_feed.recovered_close_reports SET raw_pdf=convert_to('%PDF altered','UTF8')")
 def test_future_accepted_batch_automatically_updates_reference(self):
  self.seed();self.db.execute("INSERT INTO portfolio_private.official_close_batches VALUES(repeat('d',64),'2026-11-03','{\"captured_at\":\"2026-11-03T19:24:00Z\",\"rows\":[{\"company_id\":\"fixture\",\"c_name\":\"SGTM\",\"price_decimal\":\"525\"}]}',clock_timestamp())")
  self.assertEqual(self.rows()['SGTM'][2],525)
 def test_malformed_or_negative_price_cannot_become_a_display_quote(self):
  self.seed();self.db.execute("UPDATE app_feed.recovered_close_reports SET rows='[{\"company_id\":\"fixture\",\"c_name\":\"SGTM\",\"price_decimal\":\"NaN\"}]'")
  self.assertEqual(self.rows()['SGTM'][2],580)

if __name__=='__main__':unittest.main()
