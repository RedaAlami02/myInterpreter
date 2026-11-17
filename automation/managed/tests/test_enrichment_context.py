from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projection_store
import worker
from fixture_projection import Session, Response, TOKEN, URL

PROVIDER='feed_0123456789abcdef'
NOW=datetime(2026,10,30,12,tzinfo=timezone.utc)


def context(**overrides):
    return {'contract':'private-enrichment-context/v1','provider_namespace':PROVIDER,
            'index_sha256':'a'*64,'observed_at':NOW.isoformat(),
            'companies':{'Alpha':{'bpa':1.25,'sector':None,'fiscal_year':2025}},**overrides}


class ContextTests(unittest.TestCase):
    def test_v2_price_context_retains_separate_original_and_available_dates(self):
        row={'name':'Alpha','bpa':1.25,'tc5':10,'roe':15,'na':100,'cp':50,'net_profit':2,
             'date':(NOW-timedelta(days=10)).isoformat(),'available_at':(NOW-timedelta(days=1)).isoformat()}
        value=context(contract='private-enrichment-context/v2',price_companies={'company-a':row})
        publisher,_=self.publisher(value)
        self.assertEqual(publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW),value)
        for update in [{'date':(NOW+timedelta(days=1)).isoformat()},{'user_id':'private'}, {'na':True}]:
            publisher,_=self.publisher(context(contract='private-enrichment-context/v2',price_companies={'company-a':{**row,**update}}))
            with self.assertRaises(worker.AcquisitionError):
                publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW)
    def publisher(self,value):
        session=Session(Response(200,json.dumps(value).encode()))
        return projection_store.ProjectionPublisher(URL,TOKEN,'a'*20,session=session),session

    def test_context_is_bound_to_exact_index_and_contains_only_rotation_fields(self):
        value=context()
        publisher,session=self.publisher(value)
        self.assertEqual(publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW),value)
        request=json.loads(session.calls[0][1]['data'])
        self.assertEqual(request,{'operation':'read_enrichment_context','provider_namespace':PROVIDER,'index_sha256':'a'*64})
        self.assertFalse(session.calls[0][1]['allow_redirects'])

    def test_wrong_context_private_extras_future_stale_and_bad_fields_are_rejected(self):
        for value in [context(index_sha256='b'*64),context(provider_namespace='feed_ffffffffffffffff'),
                context(observed_at=(NOW-timedelta(minutes=11)).isoformat()),
                context(observed_at=(NOW+timedelta(minutes=1)).isoformat()),context(users=[]),
                context(companies={'Alpha':{'bpa':True,'sector':None,'fiscal_year':2025}}),
                context(companies={'Alpha':{'bpa':1,'sector':None,'fiscal_year':True}}),
                context(companies={'Alpha':{'bpa':1,'sector':None,'fiscal_year':2025,'email':'fixture@example.invalid'}})]:
            publisher,_=self.publisher(value)
            with self.assertRaisesRegex(worker.AcquisitionError,'INVALID_ENRICHMENT_CONTEXT'):
                publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW)

    def test_context_can_exceed_small_write_receipt_limit_but_is_bounded(self):
        value=context(companies={str(i):{'bpa':None,'sector':None,'fiscal_year':None} for i in range(150)})
        publisher,_=self.publisher(value)
        self.assertEqual(len(publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW)['companies']),150)
        publisher,_=self.publisher(context(companies={'x':'x'*524288}))
        with self.assertRaises(worker.AcquisitionError):
            publisher.read_context(PROVIDER,'a'*64,clock=lambda:NOW)
