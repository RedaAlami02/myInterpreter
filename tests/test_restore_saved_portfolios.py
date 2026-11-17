import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from restore_saved_portfolios import summarize


class SavedPortfolioTests(unittest.TestCase):
    def fixture(self):
        return {
            'achats': [{'user_id': 'fixture-owner-a', 'c_name': 'FIX', 'date': '2026-01-09T00:00:00Z',
                        'number': 10, 'prix_achat': 12.5}],
            'ventes': [{'user_id': 'fixture-owner-a', 'c_name': 'FIX', 'date': '2026-04-23T00:00:00Z',
                        'number': 2, 'prix_vente': 15}],
            'portefeuille': [{'user_id': 'fixture-owner-a', 'c_name': 'FIX', 'quantity': 8, 'total_cost': 100},
                             {'user_id': 'fixture-owner-b', 'c_name': 'MISSING', 'quantity': 3, 'total_cost': 24}],
            'benefits': [{'user_id': 'fixture-owner-b', 'date': '2026-09-02T00:00:00Z', 'value': -17.5}],
        }

    def test_two_owners_and_incomplete_ledger_remain_separate_without_changing_payloads(self):
        data = self.fixture()
        before = copy.deepcopy(data)
        result = summarize(data)
        self.assertEqual(result['saved_owners'], 2)
        self.assertEqual(result['records'], 5)
        self.assertEqual(result['owners'][0]['holding_quantity_disagreements'], 0)
        self.assertEqual(result['owners'][1]['holdings_without_saved_trade_history'], 1)
        self.assertEqual(data, before)
        self.assertNotIn('fixture-owner-a', str(result))
        self.assertNotIn('-17.5', str(result))

    def test_missing_owner_nonfinite_value_and_duplicate_snapshot_fail(self):
        cases = []
        data = self.fixture(); data['achats'][0]['user_id'] = ''; cases.append(data)
        data = self.fixture(); data['benefits'][0]['value'] = float('nan'); cases.append(data)
        data = self.fixture(); data['benefits'].append(dict(data['benefits'][0])); cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    summarize(data)


if __name__ == '__main__':
    unittest.main()
