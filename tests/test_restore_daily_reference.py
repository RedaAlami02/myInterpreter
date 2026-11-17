from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from restore_daily_reference import build_rows


class DailyReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference = {'symbol': 'FIX', 'date': datetime(2026, 10, 20),
                          'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 103.0,
                          'quantity_traded': None, 'volume_mad': 0.0,
                          'transactions': None, 'status': None,
                          'source': 'private source', 'source_file': 'private path'}
        self.formats = [{'symbol': 'FIX', 'name': 'FIXTURE'}]
        self.observation = {'id': 'original', 'c_name': 'FIXTURE',
                            'date': datetime(2026, 10, 20, 10, tzinfo=timezone.utc),
                            'pa': Decimal('102')}

    def build(self, reference=None, observations=None):
        return build_rows(reference or [self.reference], self.formats,
                          observations or [], 'a'*64)

    def test_date_only_and_null_activity_survive_without_provider_or_fake_timestamp(self):
        rows, report = self.build()
        row = rows[0]
        self.assertEqual(row['period_day'].isoformat(), '2026-10-20')
        self.assertIsNone(row['bar']['quantity_traded'])
        self.assertNotIn('source', row['bar'])
        self.assertNotIn('source_file', row['bar'])
        self.assertFalse(row['quality']['has_trade_activity_evidence'])
        self.assertEqual(report['missing_day_candidates']['rows'], 1)

    def test_inconsistent_ohlc_is_retained_but_never_marked_usable(self):
        original = dict(self.reference, high=101)
        rows, report = self.build([original])
        self.assertEqual(rows[0]['bar']['high'], 101)
        self.assertEqual(rows[0]['close'], Decimal('103'))
        self.assertFalse(rows[0]['quality']['usable_ohlc_range'])
        self.assertEqual(report['quality_issue_counts']['inconsistent_ohlc_range'], 1)

    def test_source_differences_do_not_overwrite_recovered_prices(self):
        rows, _ = self.build(observations=[self.observation])
        self.assertEqual(rows[0]['quality']['comparison'], 'different_from_latest_recovered_price')
        self.assertEqual(rows[0]['quality']['recovered_price'], '102')
        self.assertEqual(self.observation['pa'], Decimal('102'))
        self.assertFalse(rows[0]['quality']['independently_verified_close'])

    def test_duplicate_identity_nonfinite_price_and_intraday_period_are_rejected(self):
        for records in [[self.reference, self.reference],
                        [dict(self.reference, close=float('nan'))],
                        [dict(self.reference, date=datetime(2026, 10, 20, 12))]]:
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    self.build(records)


if __name__ == '__main__':
    unittest.main()
