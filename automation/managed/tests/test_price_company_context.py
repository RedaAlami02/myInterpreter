"""Price context uses its own publication credentials; no other provider is needed."""
from datetime import timedelta
import copy,json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app_feed,app_publish,price_publication,publish_store,worker
from test_app_publish import config,profile,Response,Session,URL,TOKEN,CAPTURED
from fixture_price import companies


def inputs():
    cfg=config();pins={**profile(cfg),'application_fields_sha256':app_feed.fingerprint({})}
    rows={k:{**v,'available_at':v['date']} for k,v in companies().items()}
    return cfg,pins,{'contract':'private-price-company-context/v1',
        'provider_namespace':cfg['provider_namespace'],'mapping_sha256':pins['mapping_sha256'],
        'recipe_sha256':pins['recipe_sha256'],'application_fields_sha256':pins['application_fields_sha256'],
        'observed_at':CAPTURED.isoformat(),'price_companies':rows}

class PriceCompanyContextTests(unittest.TestCase):
    def client(self,value):
        session=Session(Response(200,json.dumps(value).encode()))
        return publish_store.AppPublisherStore(URL,TOKEN,'a'*20,session=session),session
    def test_request_uses_all_price_pins_and_preserves_actual_availability(self):
        cfg,pins,value=inputs();client,http=self.client(value)
        self.assertEqual(client.read_context(cfg,pins,clock=lambda:CAPTURED),value)
        request=json.loads(http.calls[0][1]['data'])
        self.assertEqual(request['operation'],'read_price_company_context')
        self.assertEqual(json.loads(request['mapping_document']),pins['mapping'])
        self.assertEqual(request['recipe_sha256'],pins['recipe_sha256'])
        self.assertEqual(request['application_fields_sha256'],pins['application_fields_sha256'])
        self.assertEqual(http.calls[0][1]['headers']['Authorization'],'Bearer '+TOKEN)
        self.assertFalse(http.calls[0][1]['allow_redirects'])
        self.assertLess(worker.utc(value['price_companies']['a']['available_at']),CAPTURED)
    def test_changed_pins_private_extras_missing_id_or_bad_time_are_rejected(self):
        cfg,pins,value=inputs()
        cases=[{**value,'provider_namespace':'feed_'+'f'*16},{**value,'mapping_sha256':'f'*64},
               {**value,'recipe_sha256':'f'*64},{**value,'application_fields_sha256':'f'*64},
               {**value,'observed_at':(CAPTURED-timedelta(minutes=11)).isoformat()},
               {**value,'observed_at':(CAPTURED+timedelta(minutes=1)).isoformat()},
               {**value,'users':[]},{**value,'price_companies':{}}]
        for bad in cases:
            with self.subTest(bad=bad.keys()):
                client,_=self.client(bad)
                with self.assertRaisesRegex(worker.AcquisitionError,'INVALID_PRICE_COMPANY_CONTEXT'):
                    client.read_context(cfg,pins,clock=lambda:CAPTURED)
    def test_company_fields_must_be_exact_typed_and_not_future(self):
        cfg,pins,value=inputs()
        for change in [{'name':'Other'},{'email':'fixture@example.invalid'},{'bpa':True},
                       {'na':1e16},{'date':CAPTURED+timedelta(days=1)},
                       {'available_at':None},{'available_at':'2000-01-01T00:00:00Z'}]:
            bad=copy.deepcopy(value)
            bad['price_companies']['a'].update({k:v.isoformat() if hasattr(v,'isoformat') else v for k,v in change.items()})
            client,_=self.client(bad)
            with self.subTest(change=change),self.assertRaises(worker.AcquisitionError):
                client.read_context(cfg,pins,clock=lambda:CAPTURED)
    def test_response_limit_is_distinct_from_small_write_receipts(self):
        cfg,pins,value=inputs()
        client,_=self.client({**value,'private':'x'*524288})
        with self.assertRaises(worker.AcquisitionError):client.read_context(cfg,pins,clock=lambda:CAPTURED)
    def test_default_company_input_path_needs_no_fundamental_configuration(self):
        cfg,pins,value=inputs()
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'fields.json';file.write_text('{}')
            with patch.object(app_publish,'open_publisher') as opened,patch('projection_store.ProjectionPublisher') as legacy:
                opened.return_value.read_context.return_value=value
                result=price_publication.company_inputs(cfg,pins,bindings_path=file)
                self.assertEqual(result,(value['price_companies'],{},value))
                opened.return_value.read_context.assert_called_once_with(cfg,pins)
                legacy.assert_not_called()
    def test_context_failure_never_silently_falls_back(self):
        cfg,pins,_=inputs()
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'fields.json';file.write_text('{}')
            with patch.object(app_publish,'open_publisher') as opened,patch('projection_store.ProjectionPublisher') as legacy:
                opened.return_value.read_context.side_effect=worker.AcquisitionError('PRICE_CONTEXT_DISABLED')
                with self.assertRaisesRegex(worker.AcquisitionError,'PRICE_CONTEXT_DISABLED'):
                    price_publication.company_inputs(cfg,pins,bindings_path=file)
                legacy.assert_not_called()

if __name__=='__main__':unittest.main()
