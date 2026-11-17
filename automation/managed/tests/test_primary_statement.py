import unittest
import primary_statement as primary

TEXT='EXAMPLE Group\nConsolidated annual income\nEn KMAD  2023  2024  2025\nRevenue  1 000  2 000  3 125,50\n'
BINDINGS={'revenue':{'label':'Revenue','scope':'CONSOLIDATED'}}
class PrimaryStatementTests(unittest.TestCase):
 def extract(self,text=TEXT):
  return primary.extract(text,'a'*64,'EXAMPLE Group',0,'Consolidated annual income',BINDINGS,[2023,2024,2025])
 def test_units_year_columns_and_decimal_conversion_remain_explicit(self):
  facts=self.extract();self.assertEqual(facts[-1]['value_mad_decimal'],'3125500.00')
  self.assertEqual(facts[-1]['source_year'],2025);self.assertEqual(facts[-1]['source_unit'],'KMAD')
  self.assertFalse(facts[-1]['publication_eligible'])
 def test_changed_units_scope_identity_or_columns_are_rejected(self):
  for text in [TEXT.replace('KMAD','MMAD'),TEXT.replace('EXAMPLE Group','OTHER'),TEXT.replace('2025','2026'),TEXT.replace('Consolidated annual income','Parent only')]:
   with self.assertRaises(ValueError):self.extract(text)
 def test_duplicate_rows_or_ambiguous_figures_fail_closed(self):
  for text in [TEXT+'Revenue  1  2  3\n',TEXT.replace('3 125,50','3.125,50')]:
   with self.assertRaises(ValueError):self.extract(text)
