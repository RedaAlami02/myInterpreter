"""Full saved-archive price refresh without network, persistence or live ledgers."""

import copy
from datetime import timedelta
import unittest

from test_app_feed import archive, config, mapping
from test_market_frame import body, CAPTURED
import price_refresh
from fixture_price import companies


def build(data=None, **options):
    digest, blob = archive(data=data)
    return price_refresh.build(blob, digest, config(), mapping(),
                               options.pop('companies', companies()),
                               as_of=options.pop('as_of', CAPTURED), **options)


class PriceRefreshTests(unittest.TestCase):
    def test_explicit_new_availability_cannot_attach_current_fields_to_old_quotes(self):
        values=companies()
        values['a']['available_at']=(CAPTURED+timedelta(minutes=1)).isoformat()
        result=build(companies=values,as_of=CAPTURED+timedelta(hours=1))
        self.assertIn({'asset_key':'company:a','reason':'FUTURE_FUNDAMENTALS'},result['excluded'])

    def test_replaying_later_cannot_put_newer_fundamentals_on_an_older_price_row(self):
        values = companies()
        values['a']['date'] = (CAPTURED + timedelta(hours=1)).isoformat()
        values['b']['$updatedAt'] = (CAPTURED + timedelta(minutes=10)).isoformat()
        result = build(companies=values, as_of=CAPTURED + timedelta(hours=2))
        self.assertEqual([item['asset_key'] for item in result['rows']], ['index:MAIN'])
        self.assertTrue(all(item['reason'] == 'FUTURE_FUNDAMENTALS' for item in result['excluded']))

    def test_saved_price_requires_company_inputs_already_available_at_its_old_date(self):
        data = body()
        data['quotes'].pop()
        data['catalog'][1]['p'] = None
        saved = {'id': 'saved-id', 'date': (CAPTURED - timedelta(days=20)).isoformat(),
                 'pa': 20, 'c_name': 'Company B', 'symbol': 'B'}
        result = build(data, last_known=[saved])
        self.assertIn({'asset_key': 'company:b', 'reason': 'FUTURE_FUNDAMENTALS'}, result['excluded'])
        values = companies()
        values['b'].pop('date')
        result = build(companies=values)
        self.assertIn({'asset_key': 'company:b', 'reason': 'UNKNOWN_FUNDAMENTAL_AVAILABILITY'}, result['excluded'])

    def test_long_raw_chart_reaches_original_trimming_before_general_text_limits(self):
        data = body()
        chart = ';'.join(str(index) for index in range(200)) + '|R'
        self.assertGreater(len(chart), 500)
        data['quotes'][0]['chart'] = chart
        binding = {'quotes': {'data_chart': {'path': ['chart'], 'type': 'text', 'optional': True}}}
        result = build(data, field_bindings=binding)
        from test_price_ratio_parity import chart_scope
        self.assertEqual(result['rows'][0]['row']['data_chart'], chart_scope['fit_chart'](chart))
        data['quotes'][0]['chart'] = 'x' * (price_refresh.MAX_CHART_CHARS + 1)
        with self.assertRaises(ValueError):
            build(data, field_bindings=binding)

    def test_legacy_derived_fields_require_explicit_profile_and_preserve_zero_change(self):
        data = body()
        data['quotes'][0]['ref'] = '11'
        data['quotes'].pop()
        data['catalog'][1]['change'] = '0'
        bindings = {'quotes': {'cours_ref': {'path': ['ref'], 'type': 'decimal'}},
                    'instruments': {'variation_v': {'path': ['change'], 'type': 'decimal'}}}
        direct = build(data, field_bindings=bindings)
        self.assertNotIn('variation_v', direct['rows'][0]['row'])
        self.assertNotIn('cours_ref', direct['rows'][1]['row'])
        bindings['calculation_rules'] = 'legacy_getprice/v1'
        result = build(data, field_bindings=bindings)
        self.assertEqual(result['rows'][0]['row']['variation_v'], -0.5)
        self.assertEqual(result['rows'][1]['row']['cours_ref'], 21.25)
        self.assertEqual(result['rows'][1]['row']['variation_v'], 0)
        bindings['calculation_rules'] = 'unknown'
        with self.assertRaises(ValueError):
            build(data, field_bindings=bindings)

    def test_verified_archive_reaches_full_stock_and_index_rows_with_original_rules(self):
        data = body()
        data['quotes'][0].update(capital='2000000', volume='0', quantity='0', chart='1;2;3|R')
        data['indices'][0]['volume'] = '12000'
        bindings = {'quotes': {
            field: {'path': [raw], 'type': kind, 'optional': True}
            for field, raw, kind in [('market_cap', 'capital', 'decimal'),
                ('volume', 'volume', 'decimal'), ('qty_traded', 'quantity', 'decimal'),
                ('data_chart', 'chart', 'text')]},
            'indices': {'volume': {'path': ['volume'], 'type': 'decimal'}}}
        before = copy.deepcopy((data, bindings))
        result = build(data, field_bindings=bindings)
        self.assertEqual(len(result['rows']), 3)
        stock, second, index = [item['row'] for item in result['rows']]
        self.assertEqual((stock['pa'], stock['per'], stock['cb'], stock['pb']), (10.5, 2, 2000000, 200))
        self.assertEqual((stock['volume'], stock['qty_traded'], stock['data_chart']), (0, 0, '1;2;3|R'))
        self.assertNotIn('volume', second)
        self.assertNotIn('per', index)
        self.assertNotIn('symbol', index)
        self.assertEqual(index['volume'], 12000)
        self.assertEqual(result['mode'], 'SHADOW_ONLY')
        self.assertFalse(result['portfolio_valuation_eligible'])
        self.assertFalse(result['prediction_eligible'])
        self.assertEqual((data, bindings), before)

    def test_reference_and_saved_fallback_keep_their_different_dates_and_provenance(self):
        data = body()
        data['quotes'].pop()
        result = build(data)
        reference = result['rows'][1]
        self.assertEqual(reference['provenance']['price_basis'], 'INSTRUMENT_REFERENCE')
        self.assertIsNone(reference['provenance']['source_event_at'])
        self.assertEqual(reference['row']['date'], CAPTURED.isoformat())
        self.assertNotIn('volume', reference['row'])
        data['catalog'][1]['p'] = None
        saved_at = (CAPTURED - timedelta(days=5)).isoformat()
        saved = {'id': 'real-saved-id', 'date': saved_at, 'pa': 19.75, 'c_name': 'Company B', 'symbol': 'B'}
        result = build(data, last_known=[saved])
        recovered = result['rows'][1]
        self.assertEqual(recovered['row']['date'], saved_at)
        self.assertEqual(recovered['provenance']['original_document_ids'], ['real-saved-id'])
        self.assertIsNone(recovered['provenance']['captured_at'])
        self.assertNotIn('volume', recovered['row'])
        self.assertEqual(result['acquisition_completeness'], 'INCOMPLETE')

    def test_missing_index_and_conflicting_quotes_do_not_create_rows(self):
        data = body()
        data['indices'] = []
        data['quotes'].append(dict(data['quotes'][0], p='99,00'))
        result = build(data)
        self.assertEqual([row['asset_key'] for row in result['rows']], ['company:b'])
        self.assertEqual(len(result['excluded']), 2)

    def test_wrong_company_identity_and_future_fundamentals_are_excluded(self):
        values = companies()
        values['a']['name'] = 'Another company'
        values['b']['date'] = (CAPTURED + timedelta(seconds=1)).isoformat()
        result = build(companies=values)
        self.assertEqual([item['asset_key'] for item in result['rows']], ['index:MAIN'])
        self.assertEqual({item['reason'] for item in result['excluded']},
                         {'COMPANY_IDENTITY_UNAVAILABLE', 'FUTURE_FUNDAMENTALS'})
        self.assertEqual(result['enrichment_jobs'], [])

    def test_private_field_bindings_cannot_override_price_time_or_identity(self):
        for field in ('pa', 'date', 'c_name', 'symbol', 'prediction_eligible'):
            with self.assertRaises(ValueError):
                build(field_bindings={'quotes': {field: {'path': ['p'], 'type': 'decimal'}}})
        with self.assertRaises(ValueError):
            build(field_bindings={'quotes': {'volume': {'path': ['v'], 'type': 'decimal', 'scope': 'document'}}})

    def test_quantity_is_exact_integer_and_missing_required_fields_fail(self):
        data = body()
        data['quotes'][0]['q'] = '9007199254740993'
        data['quotes'][1]['q'] = '0'
        binding = {'quotes': {'qty_traded': {'path': ['q'], 'type': 'decimal'}}}
        self.assertEqual(build(data, field_bindings=binding)['rows'][0]['row']['qty_traded'], 9007199254740993)
        for value in ('1.5', '-1', str(2**63)):
            data['quotes'][0]['q'] = value
            with self.assertRaises(ValueError):
                build(data, field_bindings=binding)
        with self.assertRaises(ValueError):
            build(field_bindings=binding)

    def test_equal_price_references_with_different_market_fields_stay_conflicted(self):
        data = body()
        data['quotes'].pop()
        data['catalog'][1]['v'] = 1
        data['catalog'].append(dict(data['catalog'][1], v=2))
        result = build(data, field_bindings={'instruments': {
            'volume': {'path': ['v'], 'type': 'decimal', 'optional': True}}})
        self.assertNotIn('company:b', [item['asset_key'] for item in result['rows']])
        self.assertIn({'asset_key': 'company:b', 'reason': 'CONFLICTING_MARKET_FIELDS'}, result['excluded'])

    def test_bad_archive_hash_fails_before_any_rows_are_built(self):
        digest, blob = archive()
        with self.assertRaises(ValueError):
            price_refresh.build(blob+b'changed', digest, config(), mapping(), companies(), as_of=CAPTURED)


if __name__ == '__main__':
    unittest.main()
