from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from legacy_sql_reader import public_tables


class LegacySqlReaderTests(unittest.TestCase):
    def test_literal_precision_escaping_null_and_implicit_columns(self):
        text = """-- Source header
        CREATE TABLE `format` (`NAME` text, `SYMBOL` text) ENGINE=InnoDB;
        INSERT INTO `format` VALUES ('O''Brien; (A)', 'FIX');
        INSERT INTO `data` (`PA`, `C_NAME`, `PB`) VALUES (1.234567890123456789e2,'A\\'B',NULL);
        """
        rows = public_tables(text)
        self.assertEqual(rows['format'], [{'name': "O'Brien; (A)", 'symbol': 'FIX'}])
        self.assertEqual(rows['data'][0]['pa'], Decimal('123.4567890123456789'))
        self.assertEqual(rows['data'][0]['c_name'], "A'B")
        self.assertIsNone(rows['data'][0]['pb'])

    def test_private_literals_cannot_inject_public_insert_records(self):
        text = '''INSERT INTO utilisateur (password) VALUES ('INSERT INTO data (PA) VALUES (999);');
        /* INSERT INTO company (NAME) VALUES ('hidden'); */
        INSERT INTO data (PA) VALUES (100);'''
        self.assertEqual(public_tables(text)['data'], [{'pa': Decimal('100')}])
        self.assertEqual(public_tables(text)['company'], [])

    def test_expressions_duplicate_columns_and_truncation_are_rejected(self):
        for text in ["INSERT INTO data (PA) VALUES (SLEEP(1));",
                     "INSERT INTO data (PA,PA) VALUES (1,2);",
                     "INSERT INTO data (PA) VALUES (1)"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                public_tables(text)


if __name__ == '__main__':
    unittest.main()
