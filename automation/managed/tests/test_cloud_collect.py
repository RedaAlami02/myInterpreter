import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cloud_collect
from worker import AcquisitionError


class CloudCollectionTests(unittest.TestCase):
    def test_official_archive_outbox_is_inside_durable_checkpoint(self):
        import official_close_collect
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'APP_OFFICIAL_CLOSE_CONFIG':'{}'},clear=True):
            def run(config,state):
                self.assertEqual(os.environ['APP_ARCHIVE_SPOOL_DIR'],str(state/'archive'))
                return {'status':'AWAITING_INDEPENDENT_REVIEW'}
            with patch.object(official_close_collect,'run',side_effect=run):
                self.assertEqual(cloud_collect.run('official_close',Path(folder)),0)

    def test_quotes_use_actual_four_queue_layout_and_private_config_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secrets = {key: '{}' for key in ('APP_MARKET_CONFIG','APP_PUBLISH_PROFILE',
                       'APP_COMPANY_INDEX','APP_APPLICATION_BINDINGS','APP_ENRICHMENT_CONFIG')}
            def collector(args):
                self.assertEqual(args[0], 'quotes')
                self.assertEqual(args[args.index('--publication-spool')+1], str(root/'quotes'))
                self.assertEqual(args[args.index('--enrichment-spool')+1], str(root/'enrichment'))
                self.assertNotIn('--company-index',args)
                config = Path(args[args.index('--config')+1])
                self.assertTrue(config.exists())
                self.assertFalse(config.is_relative_to(root))
                self.config = config
                return 2
            with patch.dict(os.environ, secrets), patch('run_collection.main', side_effect=collector):
                self.assertEqual(cloud_collect.run('quotes', root), 2)
            self.assertFalse(self.config.exists())

    def test_quotes_without_optional_enrichment_need_no_fundamental_index(self):
        secrets={key:'{}' for key in ('APP_MARKET_CONFIG','APP_PUBLISH_PROFILE','APP_APPLICATION_BINDINGS')}
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,secrets,clear=True),patch('run_collection.main',return_value=0) as collect:
            self.assertEqual(cloud_collect.run('quotes',Path(folder)),0)
            self.assertNotIn('--company-index',collect.call_args.args[0])

    def test_each_raw_collector_has_its_own_recipe_and_failure_is_preserved(self):
        for kind, env in [('depth','APP_DEPTH_CONFIG'),('dividends','APP_DIVIDEND_CONFIG')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                with patch.dict(os.environ, {env: 'recipe-for-'+kind,'APP_DIVIDEND_INDEX':'{}'}), patch('run_collection.main') as collect:
                    def check(args):
                        self.assertEqual(Path(args[2]).read_text(), 'recipe-for-'+kind)
                        return 2
                    collect.side_effect = check
                    self.assertEqual(cloud_collect.run(kind, Path(temporary), symbol='AAA' if kind=='fundamentals' else None), 2)

    def test_dividends_require_index_and_durable_publication_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.dict(os.environ,{'APP_DIVIDEND_CONFIG':'{}'},clear=True),patch('run_collection.main') as collect:
                with self.assertRaises(AcquisitionError):cloud_collect.run('dividends',root)
                collect.assert_not_called()
            with patch.dict(os.environ,{'APP_DIVIDEND_CONFIG':'{}','APP_DIVIDEND_INDEX':'{}'}),patch('run_collection.main',return_value=0) as collect:
                self.assertEqual(cloud_collect.run('dividends',root),0)
                args=collect.call_args.args[0]
                self.assertIn('--publish-index',args)
                self.assertEqual(args[args.index('--publication-spool')+1],str(root/'dividends'))

    def test_fundamentals_use_existing_projection_coordinator_not_raw_only_cli(self):
        import enrichment_jobs
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'APP_FUNDAMENTAL_CONFIG':'{}','APP_FUNDAMENTAL_INDEX':'{}'}),patch.object(enrichment_jobs,'execute',return_value={'status':'COMPLETE'}) as execute,patch('run_collection.main') as raw:
            root=Path(temporary)
            self.assertEqual(cloud_collect.run('fundamentals',root,symbol='AAA'),0)
            self.assertEqual(execute.call_args.kwargs,{'max_jobs':1,'only_symbol':'AAA'})
            self.assertEqual(execute.call_args.args[2],root/'enrichment')
            raw.assert_not_called()

    def test_incomplete_publication_configuration_stops_before_collection(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {'APP_MARKET_CONFIG':'{}'}, clear=True), patch('run_collection.main') as collect:
                with self.assertRaises(AcquisitionError): cloud_collect.run('quotes', Path(temporary))
                collect.assert_not_called()


if __name__ == '__main__': unittest.main()
