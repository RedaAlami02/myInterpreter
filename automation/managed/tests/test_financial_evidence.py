import json
import unittest
from decimal import Decimal
from unittest.mock import patch
import financial_evidence as evidence

class FinancialEvidenceTests(unittest.TestCase):
    def test_decimal_facts_preserve_zero_losses_and_exact_precision(self):
        self.assertEqual(evidence.exact_number(Decimal('0.123456789012345678')), '0.123456789012345678')
        self.assertEqual(evidence.exact_number(0), '0')
        self.assertEqual(evidence.exact_number('-12.50'), '-12.50')
        for value in [True,None,'NaN','1,23','1 234',float('inf')]:
            self.assertIsNone(evidence.exact_number(value))

    def candidate(self, raw, kind="ca"):
        archive={'symbol':'EXA','completed_at':'2026-11-15T12:00:00Z',
            'targets':[{'kind':kind,'request_index':0}],
            'captures':[{'request_index':0,'raw_hex':raw.hex(),'sha256':'a'*64,
                         'capture_id':'b'*64,'received_at':'2026-11-15T11:59:00Z'}]}
        with patch.object(evidence.fundamental_feed,'verified_archive',return_value=(archive,{})), patch.object(evidence.fundamental_feed,'validate_index',return_value={'EXA':'EXAMPLE'}):
            return evidence.build(b'archive','c'*64,{'provider_namespace':'fixture'}, {})

    def test_forecasts_and_source_periods_stay_separate_without_unit_guesses(self):
        value=self.candidate(b'{"data":{"2024":0,"2025p":12.34567890123456789,"2023":-5}}')
        self.assertEqual([f['source_year'] for f in value['reported_facts']],[2023,2024])
        self.assertEqual(value['estimated_facts'][0]['value_decimal'],'12.34567890123456789')
        self.assertFalse(value['publication_eligible'])
        self.assertFalse(value['financial_authority_verified'])
        for fact in value['reported_facts']+value['estimated_facts']:
            self.assertIsNone(fact['unit']);self.assertIsNone(fact['scope'])
            self.assertFalse(fact['publication_eligible'])
            self.assertEqual(fact['received_at'],'2026-11-15T11:59:00Z')

    def test_conflicting_duplicate_year_keys_are_not_silently_overwritten(self):
        value=self.candidate(b'{"data":{"2024":1,"2024":2}}')
        self.assertEqual(value['reported_facts'],[])
        self.assertEqual(value['issues'][0]['code'],'INVALID_OR_DUPLICATE_FINANCIAL_JSON')

    def test_per_share_endpoint_preserves_older_banking_values_as_separate_facts(self):
        value=self.candidate(b'{"financialData":{"beneficeParAction":{"2023":34.9,"2024":null,"2025p":40},"dividendeParAction":{"2023":16.5}}}',kind='financial')
        reported={f['metric']:f for f in value['reported_facts']}
        self.assertEqual(reported['reported_eps']['source_year'],2023)
        self.assertEqual(reported['reported_eps']['value_decimal'],'34.9')
        self.assertEqual(reported['reported_eps']['value_path'],['financialData','beneficeParAction','2023'])
        self.assertEqual(value['estimated_facts'][0]['source_year'],2025)
        self.assertFalse(value['publication_eligible'])
        self.assertIsNone(reported['reported_eps']['unit'])

    def test_duplicate_per_share_years_fail_closed_and_unknown_years_are_excluded(self):
        value=self.candidate(b'{"financialData":{"beneficeParAction":{"2023":1,"2023":2}}}',kind='financial')
        self.assertEqual(value['reported_facts'],[])
        self.assertEqual(value['issues'][0]['code'],'INVALID_OR_DUPLICATE_FINANCIAL_JSON')
        value=self.candidate(b'{"data":{"1999":12,"2101":13,"2024":0}}')
        self.assertEqual(len(value['reported_facts']),1)
        self.assertEqual(value['reported_facts'][0]['source_year'],2024)
