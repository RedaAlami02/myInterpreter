"""Full display rows on the existing feed; synthetic /tmp storage only."""
import copy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path

import test_display_price_sql as display
import test_manual_trial_sql as legacy
import app_feed
import price_refresh

ROOT = Path(__file__).resolve().parents[1]


class ApplicationRowsSQLTests(display.DisplayPriceSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.execute((ROOT/'migrations/supabase/016_shadow_application_rows.sql').read_text())
        cls.db.commit()

    def full(self, capabilities=None):
        self.enabled()
        trial = self.issue(capabilities=capabilities or ['archive', 'shadow_feed', 'projections'])
        quote = self.v2()
        self.publish(quote)
        companies = {row[0]['id']: {**row[0], '$updatedAt': (self.now-timedelta(days=1)).isoformat()}
                     for row in self.db.execute('SELECT to_jsonb(co) FROM public.company co')}
        document = price_refresh.publication(self.fixture_blob, quote['archive_sha256'], self.cfg,
            self.identities, companies, quote, as_of=self.now, field_bindings={})
        self.db.execute('UPDATE app_feed.application_control SET enabled=true,fields_sha256=%s',
                        (app_feed.fingerprint({}),))
        return trial, document

    def write_rows(self, document):
        text = app_feed.canonical(document)
        return self.db.execute('SELECT public.publish_shadow_application_rows(%s,%s)',
            (text, hashlib.sha256(text.encode()).hexdigest())).fetchone()[0]

    def read_rows(self):
        self.db.execute("SELECT set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true)")
        self.db.execute('SET LOCAL ROLE authenticated')
        result = self.db.execute('SELECT public.read_shadow_application_feed()').fetchone()[0]
        self.db.execute('RESET ROLE')
        return result

    def test_full_rows_publish_and_reach_authenticated_preview_without_original_writes(self):
        trial, document = self.full()
        before = legacy.baseline.snapshot(self.db)
        self.db.execute('SET LOCAL ROLE service_role')
        self.assertEqual(self.write_rows(document), app_feed.fingerprint(document))
        self.db.execute('RESET ROLE')
        result = self.read_rows()
        self.assertEqual(result['contract'], 'app-market-preview/v3')
        self.assertEqual(result['status'], 'AVAILABLE')
        self.assertEqual(len(result['rows']), 3)
        ref = next(row for row in result['rows'] if row['reference_price'] is not None)
        self.assertEqual(ref['application_fields']['pa'], 21.25)
        self.assertIsNone(ref['price_decimal'])
        self.assertFalse(ref['portfolio_valuation_eligible'])
        self.assertEqual(legacy.baseline.snapshot(self.db), before)
        self.assertNotIn('observation_id', json.dumps(result))
        self.assertNotIn('provider_namespace', json.dumps(result))
        for row in result['rows']:
            self.assertIsNotNone(row['application_fields'])
        if os.environ.get('APP_ROWS_FIXTURE'):
            path = Path(os.environ['APP_ROWS_FIXTURE'])
            if not path.resolve().is_relative_to((ROOT/'private').resolve()):
                raise RuntimeError('Fixture must remain private')
            path.write_text(json.dumps(result, default=str)+'\n')

    def test_application_storage_and_role_boundaries_are_private(self):
        for role in ('anon', 'authenticated', 'service_role'):
            for table in ('application_latest', 'application_control'):
                self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",
                    (role, 'app_feed.'+table)).fetchone()[0])
            self.assertEqual(self.db.execute("SELECT has_function_privilege(%s,'public.publish_shadow_application_rows(text,text)','EXECUTE')", (role,)).fetchone()[0], role=='service_role')
            self.assertEqual(self.db.execute("SELECT has_function_privilege(%s,'public.read_shadow_application_feed()','EXECUTE')", (role,)).fetchone()[0], role=='authenticated')

    def test_old_shadow_only_lease_cannot_publish_full_rows(self):
        _, document = self.full(capabilities=['archive', 'shadow_feed'])
        with self.assertRaises(legacy.psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.write_rows(document)

    def test_disabled_application_control_blocks_writer_and_reader(self):
        _, document = self.full()
        self.db.execute('UPDATE app_feed.application_control SET enabled=false')
        with self.assertRaises(legacy.psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.write_rows(document)
        self.assertEqual(self.read_rows()['rows'], [])

    def test_missing_control_and_null_pin_cannot_enable_publication(self):
        _, document = self.full()
        self.db.execute('DELETE FROM app_feed.application_control')
        document.pop('application_fields_sha256')
        with self.assertRaises(legacy.psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.write_rows(document)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_feed.application_latest').fetchone()[0], 0)

    def test_wrong_quote_head_archive_field_pin_and_eligibility_roll_back(self):
        _, document = self.full()
        for key, value in [('quote_payload_sha256','0'*64), ('archive_sha256','0'*64),
                           ('application_fields_sha256','0'*64), ('prediction_eligible',True),
                           ('as_of',None)]:
            changed = copy.deepcopy(document); changed[key] = value
            with self.subTest(field=key), self.assertRaises(legacy.psycopg.Error), self.db.transaction():
                self.write_rows(changed)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_feed.application_latest').fetchone()[0], 0)

    def test_forged_price_date_identity_and_reference_event_are_rejected(self):
        _, document = self.full()
        reference = next(i for i, row in enumerate(document['rows']) if row['provenance']['price_basis']=='INSTRUMENT_REFERENCE')
        edits = [('row','pa',999), ('row','date',(self.now+timedelta(seconds=1)).isoformat()),
                 ('row','c_name','Another company'), ('row','secret',1),
                 ('provenance','source_event_at',self.now.isoformat()),
                 ('provenance','fundamentals_available_at',(self.now+timedelta(seconds=1)).isoformat())]
        for section,key,value in edits:
            changed=copy.deepcopy(document); changed['rows'][reference][section][key]=value
            with self.subTest(field=key), self.assertRaises(legacy.psycopg.Error), self.db.transaction():
                self.write_rows(changed)

    def test_exact_retry_does_not_change_stored_rows_and_conflict_is_explicit(self):
        _, document = self.full()
        self.write_rows(document)
        before = self.db.execute('SELECT to_jsonb(t) FROM app_feed.application_latest t').fetchone()[0]
        self.write_rows(document)
        self.assertEqual(self.db.execute('SELECT to_jsonb(t) FROM app_feed.application_latest t').fetchone()[0], before)
        changed = copy.deepcopy(document); changed['rows'][0]['row']['volume'] = 1
        with self.assertRaises(legacy.psycopg.Error), self.db.transaction():
            self.write_rows(changed)

    def test_revocation_removes_application_fields_from_view(self):
        trial, document = self.full()
        self.write_rows(document)
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.assertEqual(self.read_rows()['rows'], [])

    def test_capacity_guard_rolls_back_and_retry_after_interruption_succeeds(self):
        _, document = self.full()
        self.db.execute('UPDATE app_feed.application_control SET max_database_bytes=0')
        with self.assertRaises(legacy.psycopg.Error), self.db.transaction():
            self.write_rows(document)
        self.db.execute('UPDATE app_feed.application_control SET max_database_bytes=350000000')
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.write_rows(document)
                raise RuntimeError('Synthetic interruption')
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_feed.application_latest').fetchone()[0], 0)
        self.write_rows(document)
        self.assertEqual(self.read_rows()['status'], 'AVAILABLE')
