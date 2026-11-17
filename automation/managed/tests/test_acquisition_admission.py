"""Off/expired/missing admission and completed slots never contact a source."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import worker,market_collect,depth_collect,dividend_collect

PROVIDER='feed_0123456789abcdef'
SLOT='2026-10-30T18:00:00+00:00'


class AcquisitionAdmissionTests(unittest.TestCase):
    def test_nontrue_and_missing_admission_fail_closed(self):
        for value in [False,None,1,'true']:
            with self.subTest(value=value),self.assertRaisesRegex(worker.AcquisitionError,'NOT_ADMITTED'):
                worker.require_acquisition_admission(SimpleNamespace(admit=lambda *a,**k:value),PROVIDER,'quotes',SLOT)
        with self.assertRaises(worker.AcquisitionError):
            worker.require_acquisition_admission(SimpleNamespace(),PROVIDER,'quotes',SLOT)

    def test_each_collector_checks_completion_and_positive_admission_before_fetch(self):
        for module,kind,validator in [(market_collect,'quotes','validate'),(depth_collect,'depth','validate'),(dividend_collect,'dividends','config_check')]:
            for complete,admitted in [(False,False),(True,False)]:
                with self.subTest(kind=kind,complete=complete),tempfile.TemporaryDirectory() as temporary:
                    path=Path(temporary)/'config.json';path.write_text(json.dumps({'provider_namespace':PROVIDER,'recipe':{}}))
                    store=SimpleNamespace(complete=Mock(return_value=complete),admit=Mock(return_value=admitted))
                    with patch.object(module,validator),patch.object(worker,'open_store',return_value=store),patch.object(worker,'scheduled_slot',return_value=SLOT),patch.object(worker,'fetch') as fetch,patch.object(module,'acquire',create=True) as acquire,contextlib.redirect_stdout(io.StringIO()):
                        result=module.main(['--config',str(path)])
                    self.assertEqual(result,0 if complete else 1)
                    fetch.assert_not_called();acquire.assert_not_called()
                    if complete:store.admit.assert_not_called()
                    else:store.admit.assert_called_once()

    def test_full_row_quote_requires_both_publication_capabilities_before_fetch(self):
        import price_publication
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'config.json';path.write_text(json.dumps({'provider_namespace':PROVIDER,'recipe':{}}))
            profile=Path(temporary)/'profile.json';profile.write_text('{}')
            store=SimpleNamespace(complete=Mock(return_value=False),admit=Mock(return_value=False))
            publication=Mock();publication.profile={'application_fields_sha256':'a'*64}
            with patch.object(market_collect,'validate'),patch.object(worker,'open_store',return_value=store),patch.object(worker,'scheduled_slot',return_value=SLOT),patch.object(price_publication,'Publications',return_value=publication),patch.object(price_publication,'company_inputs',return_value=(None,None,None)),patch.object(worker,'fetch') as fetch,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(market_collect.main(['--config',str(path),'--publish-profile',str(profile)]),1)
            fetch.assert_not_called()
            store.admit.assert_called_once_with(PROVIDER,'quotes',SLOT,shadow=True,projection=True)


if __name__=='__main__':unittest.main()
