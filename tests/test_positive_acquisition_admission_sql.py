"""Generic positive admission retains all expiring lease and quota constraints."""
from pathlib import Path
from datetime import timedelta
import os
import unittest
import test_manual_trial_sql as previous


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated PostgreSQL required')
class PositiveAcquisitionAdmissionTests(unittest.TestCase):
    setUp=previous.ManualTrialSQLTests.setUp
    tearDown=previous.ManualTrialSQLTests.tearDown
    enabled=previous.ManualTrialSQLTests.enabled
    issue=previous.ManualTrialSQLTests.issue
    reserve=previous.ManualTrialSQLTests.reserve
    stored=previous.ManualTrialSQLTests.stored
    @classmethod
    def setUpClass(cls):
        previous.ManualTrialSQLTests.setUpClass.__func__(cls)
        for name in ['015_display_price_fallback','016_shadow_application_rows']:
            cls.db.execute((Path(__file__).resolve().parents[1]/('migrations/supabase/'+name+'.sql')).read_text())
        cls.functions_before=cls.db.execute("SELECT oid,pg_get_functiondef(oid),proacl::text FROM pg_proc WHERE pronamespace IN (SELECT oid FROM pg_namespace WHERE nspname IN ('public','app_trial','app_trial_legacy','app_feed')) ORDER BY oid").fetchall()
        cls.db.execute((Path(__file__).resolve().parents[1]/'migrations/supabase/022_positive_acquisition_admission.sql').read_text())
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):cls.db.rollback();cls.db.close()

    def test_admission_install_preserves_every_preexisting_function_body_oid_and_acl(self):
        for oid,definition,acl in self.functions_before:
            self.assertEqual(self.db.execute('SELECT pg_get_functiondef(oid),proacl::text FROM pg_proc WHERE oid=%s',(oid,)).fetchone(),(definition,acl))

    def admitted(self,kind='quotes',provider=previous.PROVIDER,shadow=False,projection=False,slot=None):
        slot=slot or self.db.execute("SELECT date_trunc('hour',clock_timestamp())").fetchone()[0]
        return self.db.execute('SELECT public.market_archive_acquisition_admission(%s,%s,%s,%s,%s)',(provider,kind,slot,shadow,projection)).fetchone()[0]

    def test_admission_default_and_expired_or_short_lease_are_false(self):
        self.assertFalse(self.admitted())
        self.enabled();lease=self.issue(seconds=60)
        self.assertFalse(self.admitted())
        self.db.execute('SELECT app_trial.revoke(%s)',(lease,))
        self.issue(seconds=600)
        self.assertTrue(self.admitted())

    def test_kind_provider_and_public_bucket_are_not_silently_substituted(self):
        self.enabled();self.issue(seconds=600)
        self.assertFalse(self.admitted('depth'))
        self.assertFalse(self.admitted(provider='feed_ffffffffffffffff'))
        self.db.execute('UPDATE storage.buckets SET public=true')
        self.assertFalse(self.admitted())

    def test_required_publication_capability_is_checked_before_acquisition(self):
        self.enabled();self.issue(seconds=600,kinds=['quotes','dividends'])
        self.assertFalse(self.admitted(shadow=True))
        self.assertFalse(self.admitted(kind='dividends',projection=True))

    def test_complete_slot_and_capacity_have_no_new_admission(self):
        self.enabled();self.issue(seconds=600)
        self.assertTrue(self.admitted())
        self.stored('a'*64,'quotes')
        self.assertFalse(self.admitted())

    def test_future_and_stale_slot_are_rejected(self):
        self.enabled();self.issue(seconds=600)
        now=self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        self.assertFalse(self.admitted(slot=now+timedelta(minutes=1)))
        self.assertFalse(self.admitted(slot=now-timedelta(hours=27)))

    def test_ordinary_roles_cannot_admit_acquisition(self):
        for role in ['anon','authenticated']:
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute('SET LOCAL ROLE '+role);self.admitted()

    def test_full_row_quote_needs_projection_capability_and_application_control(self):
        self.enabled()
        lease=self.issue(seconds=600,capabilities=['archive','shadow_feed'])
        self.db.execute('UPDATE app_feed.control SET enabled=true,provider_namespace=%s,mapping_sha256=%s,recipe_sha256=%s',
                        (previous.PROVIDER,'a'*64,'b'*64))
        self.db.execute('UPDATE app_feed.application_control SET enabled=true,fields_sha256=%s',('c'*64,))
        self.assertFalse(self.admitted(shadow=True,projection=True))
        self.db.execute('SELECT app_trial.revoke(%s)',(lease,))
        self.issue(seconds=600,capabilities=['archive','shadow_feed','projections'])
        self.assertTrue(self.admitted(shadow=True,projection=True))
        self.db.execute('UPDATE app_feed.application_control SET enabled=false')
        self.assertFalse(self.admitted(shadow=True,projection=True))
