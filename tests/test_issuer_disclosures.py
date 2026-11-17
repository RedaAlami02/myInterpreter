from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from issuer_disclosures import merge_issuer, parse_issuer


HTML = b'''<table class="cols-1"><tbody>
<tr><td>D\xc3\xa9nomination</td><td>FIXTURE SA</td></tr>
<tr><td>Secteur d'activit\xc3\xa9</td><td>Holding</td></tr>
<tr><td>Principaux actionnaires</td><td><table>
<tr><th>D\xc3\xa9nomination</th><th>Date</th><th>Pourcentage d\xc3\xa9tenu</th></tr>
<tr><td>Public shareholder</td><td>21/05/2015</td><td>67,27%</td></tr>
</table></td></tr></tbody></table>'''


class IssuerDisclosureTests(unittest.TestCase):
    def test_nested_tables_preserve_ownership_dates_and_validate_identity(self):
        record = parse_issuer(HTML, "FIXTURE S.A")
        self.assertEqual(record['shareholders'][0]['pct'], 67.27)
        self.assertEqual(record['shareholders'][0]['as_of'], '2015-05-21')
        self.assertFalse(record['current_ownership_independently_verified'])
        with self.assertRaises(ValueError):
            parse_issuer(HTML, "DIFFERENT ISSUER")

    def test_merge_preserves_fiscal_capture_and_formula_sector(self):
        profile = {'c_name': 'FIXTURE', 'sector': 'corporate', 'shareholders': [],
                   'captured_at': '2026-10-22T10:00:00+00:00', 'field_origins': {}}
        record = parse_issuer(HTML, 'FIXTURE')
        merge_issuer(profile, record, '2026-10-24T10:00:00+00:00', 'a'*64)
        self.assertEqual(profile['sector'], 'corporate')
        self.assertEqual(profile['issuer_disclosures']['sector_label'], 'Holding')
        self.assertEqual(profile['financials_captured_at'], '2026-10-22T10:00:00+00:00')
        self.assertEqual(profile['shareholders'][0]['as_of'], '2015-05-21')


if __name__ == '__main__':
    unittest.main()
