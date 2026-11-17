import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from supplemental_company import number,parse_statistics

ISIN='MA0000000001'
TIME='2026-11-16T11:25:00Z'
HTML='''<table><tr><td>Société</td><td>EXAMPLE SA</td></tr>
<tr><td>ISIN</td><td>MA0000000001</td></tr><tr><td>Secteur</td><td>Industry</td></tr>
<tr><td>Capitalisation boursière</td><td>104 878 800</td></tr>
<tr><td>Nombre d'actions</td><td>52 650 000</td></tr>
<tr><td>Actions en circulation (flottant)</td><td>5 265 000</td></tr></table>
<table><tr><th>Année</th><th>Date détachement</th><th>Date paiement</th><th>Montant Brut</th><th>Montant Net</th></tr>
<tr><td>2018</td><td>18/09/2018</td><td>27/09/2018</td><td>1</td><td>0,85</td></tr></table>'''

class StatisticsTests(unittest.TestCase):
    def parse(self,html=HTML):return parse_statistics(html.encode(),ISIN,TIME)
    def test_exact_values_keep_historical_dates_and_unknown_currency(self):
        r=self.parse()
        self.assertEqual(r['identity']['shares'],'52650000')
        self.assertEqual(r['dividends'][0]['net_decimal'],'0.85')
        self.assertEqual(r['dividends'][0]['pay_date'],'2018-09-27')
        self.assertIsNone(r['source_as_of']);self.assertIsNone(r['market_cap_currency'])
        self.assertFalse(r['publication_eligible']);self.assertFalse(r['annual_financial_statements_available'])
    def test_wrong_identity_and_ambiguous_identity_are_rejected(self):
        for html in [HTML.replace(ISIN,'MA0000000002'),HTML+HTML]:
            with self.assertRaises(ValueError):self.parse(html)
    def test_layout_change_and_duplicate_fields_are_rejected(self):
        for html in [HTML.replace('Nombre d\'actions','Unknown label'),HTML.replace('<td>ISIN</td>','<td>Société</td>')]:
            with self.assertRaises(ValueError):self.parse(html)
    def test_numbers_do_not_accept_nan_boolean_and_ambiguous_formats(self):
        for value in ['NaN','Infinity','1.234,56',True,None,'1e6']:
            with self.assertRaises(ValueError):number(value)
        self.assertEqual(number('1 234,50'),'1234.50')
    def test_invalid_dates_negative_dividends_and_fractional_shares_are_rejected(self):
        for html in [HTML.replace('27/09/2018','31/02/2018'),HTML.replace('0,85','-0,85'),HTML.replace('52 650 000','52,5')]:
            with self.assertRaises(ValueError):self.parse(html)
    def test_naive_capture_time_is_rejected(self):
        with self.assertRaises(ValueError):parse_statistics(HTML.encode(),ISIN,'2026-11-16T11:25:00')

if __name__=='__main__':unittest.main()
