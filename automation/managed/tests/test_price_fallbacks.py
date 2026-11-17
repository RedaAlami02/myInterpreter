"""Legacy display fallback parity; quote certification remains unchanged."""
from datetime import timedelta
import unittest

from test_app_feed import archive, config, mapping
from test_market_frame import body, CAPTURED
import app_feed


class PriceFallbackTests(unittest.TestCase):
    def view(self, data=None, last_known=(), as_of=CAPTURED):
        digest, blob = archive(data=data)
        return app_feed.build_display_prices(blob, digest, config(), mapping(),
            as_of=as_of, last_known=last_known)

    def missing(self):
        value = body()
        value['quotes'].pop()
        return value

    def record(self, **overrides):
        result = {'$id': 'original-id', 'c_name': 'Company B', 'symbol': 'B',
            'pa': '19.75', 'date': (CAPTURED-timedelta(days=1)).isoformat()}
        result.update(overrides)
        return result

    def test_quote_takes_precedence_over_instrument_and_saved_prices(self):
        data = body()
        data['catalog'][1]['p'] = '100,00'
        row = self.view(data, [self.record()])['rows'][1]
        self.assertEqual((row['price_decimal'], row['price_basis']), ('21.25', 'OBSERVED_QUOTE'))

    def test_missing_quote_uses_instrument_price_without_inventing_trade_day(self):
        result = self.view(self.missing(), [self.record()])
        row = result['rows'][1]
        self.assertEqual((row['price_decimal'], row['price_basis']), ('21.25', 'INSTRUMENT_REFERENCE'))
        self.assertIsNone(row['source_event_at'])
        self.assertIsNone(row['source_reported_day'])
        self.assertEqual(row['captured_at'], CAPTURED.isoformat())
        self.assertFalse(row['fresh_quote_available'])
        self.assertFalse(row['prediction_eligible'])
        self.assertFalse(row['portfolio_valuation_eligible'])
        self.assertEqual(result['acquisition_completeness'], 'INCOMPLETE')

    def test_missing_instrument_price_uses_original_saved_date_and_identity(self):
        data = self.missing()
        data['catalog'][1]['p'] = None
        record = self.record()
        row = self.view(data, [record])['rows'][1]
        self.assertEqual((row['price_decimal'], row['price_basis']), ('19.75', 'RECOVERED_LAST_KNOWN'))
        self.assertEqual(row['original_document_ids'], ['original-id'])
        self.assertEqual(row['original_recorded_at'], record['date'])
        self.assertIsNone(row['captured_at'])
        self.assertIsNone(row['source_event_at'])

    def test_future_saved_record_and_wrong_symbol_cannot_replace_valid_history(self):
        data = self.missing()
        data['catalog'][1]['p'] = '0'
        row = self.view(data, [self.record(date=(CAPTURED+timedelta(seconds=1)).isoformat(), pa=999),
            self.record(symbol='OTHER', pa=888), self.record()])['rows'][1]
        self.assertEqual(row['price_decimal'], '19.75')

    def test_conflicting_current_quotes_are_not_hidden_with_a_reference(self):
        data = body()
        data['quotes'].append(dict(data['quotes'][1], p='99,00'))
        row = self.view(data, [self.record()])['rows'][1]
        self.assertEqual(row['quote_status'], 'CONFLICTING_QUOTES')
        self.assertIsNone(row['price_decimal'])

    def test_conflicting_instrument_prices_are_not_hidden_with_saved_history(self):
        data = self.missing()
        data['catalog'].append(dict(data['catalog'][1], p='99,00'))
        row = self.view(data, [self.record()])['rows'][1]
        self.assertEqual(row['price_basis'], 'CONFLICTING_INSTRUMENT_PRICES')
        self.assertIsNone(row['price_decimal'])

    def test_equal_time_saved_conflict_is_explicit(self):
        data = self.missing()
        data['catalog'][1]['p'] = None
        row = self.view(data, [self.record(), self.record(pa='99.00', **{'$id': 'other-id'})])['rows'][1]
        self.assertEqual(row['price_basis'], 'CONFLICTING_SAVED_PRICES')
        self.assertIsNone(row['price_decimal'])

    def test_index_never_uses_a_stock_or_saved_company_fallback(self):
        data = body()
        data['indices'] = []
        row = self.view(data, [self.record(c_name='Main index', symbol='MAIN')])['rows'][2]
        self.assertIsNone(row['price_decimal'])
        self.assertEqual(row['price_basis'], 'UNAVAILABLE')

    def test_old_quote_retains_its_actual_capture_and_stale_status(self):
        row = self.view(as_of=CAPTURED+timedelta(days=1))['rows'][0]
        self.assertEqual(row['price_decimal'], '10.50')
        self.assertEqual(row['quote_status'], 'STALE_CAPTURE_DATE')
        self.assertEqual(row['captured_at'], CAPTURED.isoformat())
        self.assertFalse(row['fresh_quote_available'])

    def test_invalid_or_extreme_saved_prices_remain_unavailable(self):
        data = self.missing()
        data['catalog'][1]['p'] = None
        for price in [True, 0, -1, 'NaN', 'Infinity', '1e-100000000', '1e100000000']:
            with self.subTest(price=str(price)):
                self.assertIsNone(self.view(data, [self.record(pa=price)])['rows'][1]['price_decimal'])

    def test_accepted_quote_candidate_is_not_changed_by_display_calculation(self):
        data = self.missing()
        digest, blob = archive(data=data)
        before = app_feed.build(blob, digest, config(), mapping(), as_of=CAPTURED)
        self.view(data)
        self.assertEqual(app_feed.build(blob, digest, config(), mapping(), as_of=CAPTURED), before)
        self.assertIsNone(before['rows'][1]['display_price_decimal'])

    def test_tampered_archive_cannot_supply_fallback_prices(self):
        digest, blob = archive(data=self.missing())
        with self.assertRaises(app_feed.FrameError):
            app_feed.build_display_prices(blob+b'changed', digest, config(), mapping(), as_of=CAPTURED)

    def test_v2_attaches_reference_without_promoting_missing_quote(self):
        digest, blob = archive(data=self.missing())
        original = app_feed.build(blob, digest, config(), mapping(), as_of=CAPTURED)
        candidate = app_feed.build_with_references(blob, digest, config(), mapping(), as_of=CAPTURED)
        self.assertEqual(candidate['contract'], 'app-market-candidate/v2')
        self.assertIsNone(candidate['rows'][1]['display_price_decimal'])
        self.assertEqual(candidate['rows'][1]['reference_price']['price_decimal'], '21.25')
        self.assertIsNone(candidate['rows'][1]['reference_price']['reported_day'])
        for before, after in zip(original['rows'], candidate['rows']):
            self.assertEqual(before, {k:v for k,v in after.items() if k not in ('reference_price','reference_conflict')})

    def test_v2_preserves_instrument_conflict_for_client_fallback_rules(self):
        data=self.missing()
        data['catalog'].append(dict(data['catalog'][1],p='99,00'))
        digest,blob=archive(data=data)
        value=app_feed.build_with_references(blob,digest,config(),mapping(),as_of=CAPTURED)
        self.assertTrue(value['rows'][1]['reference_conflict'])
        self.assertIsNone(value['rows'][1]['reference_price'])


if __name__ == '__main__':
    unittest.main()
