import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import profile_refresh as refresh
import fundamental_feed
from test_fundamental_collect import config, fetcher


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.document = {'symbol': 'AAA', 'c_name': 'EXAMPLE', 'fields': {
            'fiscal_year': 2024, 'revenue': 0, 'net_profit': -10,
            'description': 'New text', 'sector': None}}
        self.evidence = {'captured_at': '2026-11-16T11:00:00Z',
                         'reported_facts': [], 'estimated_facts': [{}], 'issues': []}
        self.baseline = {'name': 'EXAMPLE', 'fiscal_year': 2025,
                         'revenue': '0.00', 'net_profit': None, 'description': 'Old text'}

    def test_changes_keep_zero_losses_period_and_review_authority(self):
        report = refresh.compare(self.document, self.evidence, self.baseline, primary_reviewed=True)
        self.assertEqual(report['period_comparison'], 'OLDER')
        changes = {row['field']: row for row in report['changes']}
        self.assertNotIn('revenue', changes)
        self.assertNotIn('sector', changes)
        self.assertEqual(changes['net_profit']['candidate'], -10)
        self.assertEqual(changes['net_profit']['decision'], 'PRIMARY_REVIEW_PROTECTED')
        self.assertEqual(changes['description']['decision'], 'BIOGRAPHY_REVIEW_REQUIRED')
        self.assertFalse(report['publication_eligible'])
        self.assertIsNone(report['source_published_at'])
        self.assertEqual(report['financial_coverage'], 'UNAVAILABLE')

    def test_unreviewed_changed_financials_still_require_review(self):
        report = refresh.compare(self.document, self.evidence, self.baseline)
        self.assertTrue(any(row['decision'] == 'FINANCIAL_REVIEW_REQUIRED' for row in report['changes']))
        with self.assertRaises(ValueError):
            refresh.compare(self.document, self.evidence, {'name': 'OTHER'})
        with self.assertRaises(ValueError):
            refresh.compare(self.document, self.evidence, self.baseline, primary_reviewed='false')

    def test_semantically_identical_shareholder_json_does_not_propose_change(self):
        document = copy.deepcopy(self.document)
        document['fields'] = {'shareholders': '[{"name":"Holder","pct":25}]'}
        baseline = {'name': 'EXAMPLE', 'shareholders': '[ {"pct":25.0, "name":"Holder"} ]'}
        self.assertEqual(refresh.compare(document, self.evidence, baseline)['changes'], [])

    def test_batch_failure_is_independent_and_persistence_failure_aborts(self):
        saved = []
        with patch.object(fundamental_feed, 'validate_index', return_value={'AAA': 'A', 'BBB': 'B'}), \
             patch.object(refresh, 'capture', side_effect=[ValueError('private URL'), {'report': {'symbol': 'BBB', 'status': 'CAPTURED_FOR_REVIEW'}}]):
            report = refresh.capture_batch({'provider_namespace': 'fixture'}, {}, {'AAA': {'name': 'A'}, 'BBB': {'name': 'B'}},
                                           on_result=lambda s, r: saved.append(s))
        self.assertEqual(saved, ['AAA', 'BBB'])
        self.assertEqual(report['reports'][0]['status'], 'CAPTURE_FAILED')
        self.assertNotIn('private URL', json.dumps(report))
        with patch.object(fundamental_feed, 'validate_index', return_value={'AAA': 'A'}), \
             patch.object(refresh, 'capture', return_value={'report': {}}):
            def fail(*args):
                raise OSError('disk full')
            with self.assertRaises(OSError):
                refresh.capture_batch({'provider_namespace': 'fixture'}, {}, {'AAA': {'name': 'A'}}, on_result=fail)

    def test_batch_cache_is_registry_only_and_never_survives_a_new_refresh(self):
        calls = []
        def fetch(recipe, deadline, maximum):
            calls.append(recipe['kind'])
            return b'{}', 'original timestamp'
        def capture(config, index, symbol, baseline, *, fetcher, **kwargs):
            for kind in ['symlinks', 'rnpg', 'desc']:
                self.assertEqual(fetcher({'kind': kind}, 1, 100)[1], 'original timestamp')
            return {'report': {'symbol': symbol}}
        for _ in range(2):
            with patch.object(fundamental_feed, 'validate_index', return_value={'AAA': 'A', 'BBB': 'B'}), \
                 patch.object(refresh, 'capture', side_effect=capture):
                result = refresh.capture_batch({'provider_namespace': 'fixture'}, {}, {'AAA': {'name': 'A'}, 'BBB': {'name': 'B'}}, fetcher=fetch)
            self.assertEqual(result['network_requests'], 5)
            self.assertEqual(result['registry_reuses'], 1)
        self.assertEqual(calls.count('symlinks'), 2)
        self.assertEqual(calls.count('rnpg'), 4)
        self.assertEqual(calls.count('desc'), 4)

    def test_http_status_and_raw_capture_survive_a_partial_source_failure(self):
        fetch, _ = fetcher(failures={'fp'})
        index = {'contract':'private-fundamental-index/v1',
                 'provider_namespace':config()['provider_namespace'], 'symbols':{'AAA':'EXAMPLE'}}
        result = refresh.capture(config(),index,'AAA',{'name':'EXAMPLE'},fetcher=fetch)
        self.assertIn('archive',result)
        self.assertEqual(result['report']['status'],'PARTIAL_CAPTURE')
        self.assertEqual(result['report']['source_errors'],[{'kind':'fp','code':'HTTP_FAILURE','http_status':500}])
        self.assertFalse(result['report']['publication_eligible'])

    def test_parse_failure_retains_raw_archive_and_sanitizes_source_error(self):
        fetch, _ = fetcher(failures={'fp'})
        index = {'contract':'private-fundamental-index/v1', 'provider_namespace':config()['provider_namespace'],
                 'symbols':{'AAA':'EXAMPLE'}}
        with patch.object(refresh.fundamental_feed,'validate_index',return_value={'AAA':'EXAMPLE'}), \
             patch.object(refresh.fundamental_collect,'acquire',return_value={
                 'captures':[{}], 'errors':[], 'fixture':True}), \
             patch.object(refresh.financial_evidence,'build',side_effect=ValueError('private response')):
            result = refresh.capture(config(),index,'AAA',{'name':'EXAMPLE'},fetcher=fetch)
        self.assertIn('archive',result)
        self.assertEqual(result['report']['status'],'CANDIDATE_VALIDATION_FAILED')
        self.assertNotIn('private response',json.dumps(result['report']))

    def test_bad_identity_or_oversized_batch_makes_no_requests(self):
        def no_fetch(*args):
            self.fail('Unexpected request')
        for baseline in [{}, {str(i): {'name': 'A'} for i in range(6)}]:
            with self.assertRaises(ValueError):
                refresh.capture_batch({'provider_namespace': 'fixture'}, {}, baseline, fetcher=no_fetch)
        with patch.object(fundamental_feed, 'validate_index', return_value={'AAA': 'A'}):
            with self.assertRaises(ValueError):
                refresh.capture_batch({'provider_namespace': 'fixture'}, {}, {'AAA': {'name': 'OTHER'}}, fetcher=no_fetch)


if __name__ == '__main__':
    unittest.main()
