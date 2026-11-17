from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from archive_earlier_backups import public_sections


class EarlierArchiveTests(unittest.TestCase):
    def test_mixed_backup_excludes_personal_sections_and_ownership_permissions(self):
        source = {'data': [{'$id': 'market', '$permissions': ['fixture-owner'], 'c_name': 'FIX', 'pa': 100}],
                  'achats': [{'user_id': 'fixture-owner', 'prix_achat': 99}],
                  'utilisateur': [{'password': 'fixture-password'}]}
        result = public_sections(source)
        self.assertEqual(result, {'data': [{'$id': 'market', 'c_name': 'FIX', 'pa': 100}]})
        self.assertIn('$permissions', source['data'][0])

    def test_unexpected_credentials_inside_public_section_abort_the_extract(self):
        with self.assertRaises(ValueError):
            public_sections({'data': [{'authorization': 'fixture-secret'}]})


if __name__ == '__main__':
    unittest.main()
