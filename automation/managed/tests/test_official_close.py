import unittest
from official_close import CloseError, decimal_token, parse_text, parse_pdf


def report(close='1 432,00', reference='1 432,00', identity='MA0000000001'):
    return ('Séance du 02/11/2026\nDésignation  Ouv  Clôt  Haut  Bas\n'
            f'A  B  C  D  E  F  {reference}  {identity}  EXAMPLE EQUITY  1400,00  {close}  1440,00  1390,00  T\n')


class OfficialCloseTests(unittest.TestCase):
    def test_joined_trade_price_and_date_preserves_exact_close(self):
        text = report('216,00', '216,00').replace(
            'A  B  C  D  E  F', '1000  50  SAN  C  218,00 02/11/26')
        self.assertEqual(self.parse(text)['rows'][0]['price_decimal'], '216.00')
        with self.assertRaisesRegex(CloseError, 'CONFLICT'):
            self.parse(text.replace('  216,00  MA', '  217,00  MA'))

    def parse(self, text):
        return parse_text(text, '2026-11-02', 'a' * 64)

    def test_exact_decimal_no_float_rounding(self):
        row = self.parse(report('0,12345678', '0,12345678'))['rows'][0]
        self.assertEqual(row['price_decimal'], '0.12345678')
        self.assertEqual(len(row['observation_id']), 64)
        self.assertEqual(decimal_token('1\u202f432,00'), '1432.00')

    def test_missing_is_explicit_not_reference_substitution(self):
        text = report() + report('-', '1400,00', 'MA0000000002').splitlines()[-1]
        rows = self.parse(text)['rows']
        self.assertIsNone(rows[1]['price_decimal'])
        self.assertEqual(rows[1]['availability'], 'MISSING_CLOSE')

    def test_every_close_must_match_reference(self):
        with self.assertRaisesRegex(CloseError, 'CONFLICT'):
            self.parse(report(reference='1433,00'))

    def test_duplicate_identifier_rejected(self):
        with self.assertRaisesRegex(CloseError, 'DUPLICATE'):
            self.parse(report() + report())

    def test_wrong_or_multiple_session_rejected(self):
        for text in (report().replace('02/11/2026', '30/10/2026'),
                     report() + 'Séance du 30/10/2026'):
            with self.assertRaisesRegex(CloseError, 'SESSION'):
                self.parse(text)

    def test_close_header_required(self):
        with self.assertRaisesRegex(CloseError, 'COLUMN'):
            self.parse(report().replace('Clôt', 'Dernier'))

    def test_invalid_numbers_rejected(self):
        for number in ('NaN', 'Infinity', '-1', '0', '1e3', '1.123456789', '1,2,3'):
            with self.assertRaises(CloseError):
                decimal_token(number)

    def test_unknown_clocks_remain_unknown_and_no_approval(self):
        value = self.parse(report())
        self.assertIsNone(value['published_at'])
        self.assertIsNone(value['session_close_at'])
        self.assertIn('REQUIRES_REVIEWED', value['approval'])

    def test_invalid_pdf_not_extracted(self):
        with self.assertRaisesRegex(CloseError, 'BYTES'):
            parse_pdf(b'not a PDF', '2026-11-02')


if __name__ == '__main__':
    unittest.main()
