import unittest
from datetime import datetime,timezone
from health_check import issues
NOW=datetime(2026,11,4,12,tzinfo=timezone.utc)
def snapshot():
    return dict(database_bytes=220000000,guard_bytes=350000000,warning_bytes=20000000,
        market_due=True,close_due=False,depth_age_seconds=30,quotes_age_seconds=500,
        depth_complete=True,quotes_complete=True,official_batches=0,valuation_receipts=0,
        portfolio_owners=0,measured_at=NOW.isoformat())
class HealthTests(unittest.TestCase):
    def check(self,s,run=None):return issues(s,run or {'status':'completed','conclusion':'success'},NOW)
    def test_healthy(self):self.assertEqual(self.check(snapshot()),[])
    def test_storage_warns_before_guard(self):
        s=snapshot();s['database_bytes']=330000001
        self.assertEqual(self.check(s),['STORAGE_HEADROOM_LOW'])
    def test_missing_and_incomplete_are_distinct(self):
        s=snapshot();s.update(depth_age_seconds=None,quotes_complete=False)
        self.assertEqual(self.check(s),['DEPTH_MISSING_OR_STALE','QUOTES_COVERAGE_INCOMPLETE'])
    def test_close_requires_real_batch_and_receipts_for_holdings(self):
        s=snapshot();s.update(market_due=False,close_due=True,portfolio_owners=1)
        self.assertEqual(self.check(s),['OFFICIAL_CLOSE_UNVERIFIED'])
        s['official_batches']=1
        self.assertEqual(self.check(s),['PORTFOLIO_VALUATIONS_UNVERIFIED'])
        s['valuation_receipts']=1
        self.assertEqual(self.check(s),[])
    def test_no_holdings_do_not_require_valuation(self):
        s=snapshot();s.update(close_due=True,official_batches=1)
        self.assertEqual(self.check(s),[])
    def test_completed_failure_is_not_hidden(self):
        self.assertEqual(self.check(snapshot(),{'status':'completed','conclusion':'failure'}),['COLLECTION_RUN_FAILED'])
    def test_stale_or_unbounded_input_rejected(self):
        s=snapshot();s['measured_at']='2026-11-03T12:00:00+00:00'
        with self.assertRaises(ValueError):self.check(s)
        s=snapshot();s['database_bytes']=True
        with self.assertRaises(ValueError):self.check(s)
