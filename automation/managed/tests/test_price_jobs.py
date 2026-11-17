"""Compare original enrichment dispatch decisions without importing its SDK."""

import ast
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import price_jobs

ROOT = Path(__file__).resolve().parents[3]
source = ast.parse((ROOT / 'cloud_function/functions/getprice/src/main.py').read_text())
main = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
dispatch = next(node for node in main.body if isinstance(node, ast.Try)
                and any(isinstance(item, ast.Assign) and any(isinstance(target, ast.Name)
                        and target.id == 'name_to_symbol' for target in item.targets) for item in node.body))
legacy_code = compile(ast.Module(body=[dispatch], type_ignores=[]), 'legacy-enrichment', 'exec')


def legacy_jobs(companies, mappings, moment):
    jobs = []
    scope = {'companies': companies, 'symbol_to_name': mappings,
             'datetime': SimpleNamespace(now=lambda zone: moment.astimezone(zone)),
             'timezone': timezone, 'ENRICH_MAX_PER_RUN': 5, 'REFRESH_PER_HOUR': 5,
             'trigger_onboard': lambda fn, fn_id, symbol, name, ctx: jobs.append((name, symbol)),
             'context': SimpleNamespace(log=lambda *_: None), 'functions': None, 'onboard_fn': 'test'}
    exec(legacy_code, scope)
    return jobs


class PriceJobTests(unittest.TestCase):
    def test_dispatch_matches_legacy_caps_completion_markers_refresh_order_and_hour(self):
        companies = {f'Company {index}': {'bpa': 0, 'fiscal_year': 2020 + index % 5}
                     for index in range(12)}
        companies['Company 0']['sector'] = 'Completed without earnings'
        companies['Company 1']['bpa'] = -2
        companies['Company 2']['fiscal_year'] = None
        mappings = {str(index): name for index, name in enumerate(companies)}
        mappings.pop('11')  # Unmapped companies never trigger enrichment.
        for minute in (0, 14, 15, 30, 59):
            moment = datetime(2026, 10, 29, 12, minute, tzinfo=timezone.utc)
            actual = price_jobs.enrichment_jobs(companies, mappings, moment)
            self.assertEqual([(job['name'], job['symbol']) for job in actual],
                             legacy_jobs(companies, mappings, moment))
            self.assertLessEqual(sum(job['reason'] == 'INITIAL' for job in actual), 5)
            self.assertLessEqual(sum(job['reason'] == 'REFRESH' for job in actual), 5)
            self.assertEqual(len({job['name'] for job in actual}), len(actual))

    def test_dispatch_uses_utc_hour_and_does_not_mutate_inputs(self):
        companies, mappings = {'A': {'bpa': 1}}, {'AAA': 'A'}
        before = copy.deepcopy((companies, mappings))
        moment = datetime(2026, 10, 29, 12, 14, tzinfo=timezone(timedelta(minutes=30)))
        self.assertEqual(price_jobs.enrichment_jobs(companies, mappings, moment), [])
        self.assertEqual((companies, mappings), before)

    def test_dispatch_rejects_naive_time_ambiguous_symbols_and_unbounded_limits(self):
        with self.assertRaises(ValueError):
            price_jobs.enrichment_jobs({}, {}, datetime(2026, 10, 29))
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            price_jobs.enrichment_jobs({'A': {}}, {'A': 'A', 'B': 'A'}, now)
        for limit in (True, -1, 6):
            with self.assertRaises(ValueError):
                price_jobs.enrichment_jobs({}, {}, now, initial_limit=limit)
        self.assertEqual(price_jobs.enrichment_jobs({'A': {}}, {'AAA': 'A'}, now,
                                                   initial_limit=0, refresh_limit=0), [])

    def test_listing_preserves_existing_records_and_reuses_existing_bare_company(self):
        mappings, companies = {'AAA': 'A'}, {'A': {'bpa': 2}, 'B': {'name': 'B'}}
        before = copy.deepcopy((mappings, companies))
        result = price_jobs.new_listings([{'symbol': 'AAA', 'name': 'A'},
            {'symbol': 'BBB', 'name': ' B '}, {'symbol': 'CCC', 'name': 'C'},
            {'symbol': 'CCC', 'name': 'C'}, {'symbol': '', 'name': 'Invalid'}], mappings, companies)
        self.assertEqual(result, {'additions': [
            {'format': {'symbol': 'BBB', 'name': 'B'}, 'company': None},
            {'format': {'symbol': 'CCC', 'name': 'C'}, 'company': {'name': 'C'}}], 'conflicts': []})
        self.assertEqual((mappings, companies), before)

    def test_listing_conflicts_require_review_instead_of_overwriting_identity(self):
        result = price_jobs.new_listings([
            {'symbol': 'AAA', 'name': 'Renamed'}, {'symbol': 'BBB', 'name': 'A'},
            {'symbol': 'CCC', 'name': 'C'}, {'symbol': 'CCC', 'name': 'Other C'},
            {'symbol': 'DDD', 'name': 'Shared'}, {'symbol': 'EEE', 'name': 'Shared'}],
            {'AAA': 'A'}, {'A': {}})
        self.assertEqual(result['additions'], [])
        self.assertEqual(len(result['conflicts']), 5)


if __name__ == '__main__':
    unittest.main()
