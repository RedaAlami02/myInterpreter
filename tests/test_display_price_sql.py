"""Versioned display fallbacks on isolated SQL; inherited v1 behavior regressions."""
import json
from pathlib import Path

import test_manual_trial_sql as legacy
import test_shadow_market_feed_sql as feed


class DisplayPriceSQLTests(legacy.ManualTrialSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.execute((Path(__file__).resolve().parents[1] /
                        'migrations/supabase/015_display_price_fallback.sql').read_text())
        cls.db.commit()

    def test_install_preserves_original_values_and_legacy_bodies_oids(self):
        # SQL015 deliberately upgrades only these two private bodies. SQL014's
        # original exact-body test still runs unchanged in its own database.
        self.assertEqual(legacy.baseline.snapshot(self.db), self.before)
        upgraded = ('publish_shadow_market_candidate', 'read_shadow_market_feed')
        for signature, old in self.legacy.items():
            oid, body = self.db.execute('SELECT oid,prosrc FROM pg_proc WHERE oid=to_regprocedure(%s)',
                ('app_trial_legacy.' + signature,)).fetchone()
            self.assertEqual(oid, old[0])
            if signature.startswith(upgraded):
                self.assertNotEqual(body, old[1])
            else:
                self.assertEqual(body, old[1])

    def v2(self):
        original = self.prepared(partial=True)
        data = feed.body()
        for row in data['quotes'] + data['indices']:
            row['time'] = self.now.astimezone(feed.worker.ZONE).strftime('%d/%m/%Y %H:%M:%S')
        data['quotes'].pop()
        slot = self.now.replace(minute=self.now.minute//15*15, second=0, microsecond=0)
        envelope = feed.market_collect.envelope(self.cfg, json.dumps(data).encode(), self.now,
            slot.isoformat(), execution='CURRENT_ACQUISITION')
        envelope['completed_at'] = self.now.isoformat()
        digest, blob = feed.worker.packed(envelope)
        self.fixture_blob = blob
        self.assertEqual(digest, original['archive_sha256'])
        return feed.app_feed.build_with_references(blob, digest, self.cfg, self.identities, as_of=self.now)

    def test_v2_reference_reaches_authenticated_reader_without_becoming_a_quote(self):
        self.enabled()
        trial = self.issue()
        candidate = self.v2()
        self.publish(candidate)
        result = self.read()
        self.assertEqual(result['contract'], 'app-market-preview/v2')
        row = next(r for r in result['rows'] if r['status'] == 'MISSING_QUOTE')
        self.assertIsNone(row['price_decimal'])
        self.assertEqual(row['reference_price']['price_decimal'], '21.25')
        self.assertIsNone(row['reference_price']['reported_day'])
        self.assertFalse(row['reference_price']['portfolio_valuation_eligible'])
        deadline = self.db.execute('SELECT expires_at FROM app_trial.leases WHERE id=%s', (trial,)).fetchone()[0]
        self.assertLessEqual(feed.worker.utc(row['reference_price']['expires_at']), deadline)
        self.assertNotIn('observation_id', json.dumps(result))

    def test_v2_exact_retry_does_not_change_stored_body_hash_or_timestamp(self):
        self.enabled()
        self.issue()
        candidate = self.v2()
        self.publish(candidate)
        before = self.db.execute('SELECT to_jsonb(t) FROM app_feed.latest t').fetchone()[0]
        self.publish(candidate)
        self.assertEqual(self.db.execute('SELECT to_jsonb(t) FROM app_feed.latest t').fetchone()[0], before)

    def test_v2_invented_trade_date_rolls_back_publication(self):
        self.enabled()
        self.issue()
        candidate = self.v2()
        row = next(r for r in candidate['rows'] if r['reference_price'] is not None)
        row['reference_price']['reported_day'] = candidate['market_date']
        with self.assertRaises(legacy.psycopg.Error), self.db.transaction():
            self.publish(candidate)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_feed.latest').fetchone()[0], 0)

    def test_revoked_v2_reference_is_no_longer_visible(self):
        self.enabled()
        trial = self.issue()
        self.publish(self.v2())
        self.assertEqual(self.read()['status'], 'AVAILABLE')
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.assertEqual(self.read()['rows'], [])

    def test_reference_helpers_are_private(self):
        for role in ('anon','authenticated','service_role'):
            for signature in ('app_feed.validate_reference_candidate(jsonb)',
                              'app_feed.reference_for_preview(jsonb,jsonb,timestamptz)'):
                self.assertFalse(self.db.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')", (role,signature)).fetchone()[0])
