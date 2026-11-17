import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'cloud_function/functions/dividends/src'))
from div_quality import verification_issue
from div_parser import parse_calendar


class DividendQualityTests(unittest.TestCase):
    def test_python_uses_same_period_decisions_as_php_and_flutter(self):
        cases = json.loads((ROOT/'tests/fixtures/dividend_periods.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(verification_issue(case['row']), case['issue'])

    def test_parser_retains_wrong_year_evidence_with_explicit_quarantine_marker(self):
        html = '''<table><tr><th>Émetteur</th><th>Montant (MAD)</th><th>Dividende %</th>
        <th>Détachement</th><th>Paiement</th><th>Type</th><th>Fréquence</th></tr>
        <tr><td>FIXTURE</td><td>175,00</td><td>1%</td><td>25/03/2025</td>
        <td>08/04/2025</td><td>Ordinaire</td><td>Annuel</td></tr></table>'''
        row = parse_calendar(html, 2027)[0]
        self.assertEqual(row['verification_issue'], 'payment_year_mismatch')
        self.assertEqual(row['amount'], 175)
        self.assertEqual(row['ex_date'], '2025-03-25')


if __name__ == '__main__':
    unittest.main()
