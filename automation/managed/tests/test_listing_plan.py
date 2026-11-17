import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import listing_plan
import worker
from test_app_feed import archive,config
from test_market_frame import body

BINDINGS={'contract':'private-listing-bindings/v1','symbol_path':['symbol'],'name_path':['name']}


class ListingPlanTests(unittest.TestCase):
    def build(self, data=None, companies=None, mappings=None, bindings=None, execution='CURRENT_ACQUISITION'):
        selected=data or body()
        for row in selected['catalog']:
            row.setdefault('symbol',row['key']);row.setdefault('name','Company '+row['key'])
        digest,blob=archive(selected,execution=execution)
        before=hashlib.sha256(blob).hexdigest()
        result=listing_plan.build(blob,digest,config(),bindings or BINDINGS,
            companies or [{'id':'a','name':'Company A'}],mappings or [{'symbol':'A','name':'Company A'}],'a'*64)
        self.assertEqual(hashlib.sha256(blob).hexdigest(),before)
        return result

    def test_unknown_catalog_stock_preserves_original_observation_references(self):
        plan=self.build()
        self.assertEqual(len(plan['additions']),1)
        row=plan['additions'][0]
        self.assertEqual((row['name'],row['symbol']),('Company B','B'))
        self.assertTrue(row['create_company'])
        self.assertEqual(row['evidence'][0]['raw_row_index'],1)
        self.assertEqual(len(row['evidence'][0]['observation_id']),64)
        self.assertFalse(plan['portfolio_valuation_eligible'])
        self.assertFalse(plan['prediction_eligible'])

    def test_missing_or_ambiguous_fields_are_not_guessed(self):
        for bindings in [{**BINDINGS,'name_path':['missing']}, {**BINDINGS,'symbol_path':[]},
                         {**BINDINGS,'extra':'native'}]:
            with self.subTest(bindings=bindings),self.assertRaises((ValueError,worker.AcquisitionError)):self.build(bindings=bindings)

    def test_duplicate_existing_company_names_require_review(self):
        with self.assertRaisesRegex(worker.AcquisitionError,'AMBIGUOUS_EXISTING_COMPANY'):
            self.build(companies=[{'id':'a','name':'Company A'},{'id':'b','name':'Company A'}])

    def test_existing_mapping_conflict_is_preserved_in_plan(self):
        plan=self.build(mappings=[{'symbol':'A','name':'Different Company'}])
        self.assertIn({'symbol':'A','reason':'EXISTING_MAPPING_DIFFERS'},plan['conflicts'])

    def test_recorded_replay_remains_explicit_and_cannot_become_current(self):
        self.assertEqual(self.build(execution='RECORDED_REPLAY')['source_execution'],'RECORDED_REPLAY')

    def test_oversized_listing_batch_needs_separate_review(self):
        data=body();data['catalog']=[{'key':str(i),'p':'10'} for i in range(26)]
        with self.assertRaisesRegex(worker.AcquisitionError,'BATCH_REQUIRES_REVIEW'):self.build(data=data)


if __name__=='__main__':unittest.main()
