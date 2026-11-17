#!/usr/bin/env python3
"""Standalone synthetic worker acceptance; legacy parity remains in the main repo."""
from pathlib import Path
import sys
import unittest

# Explicitly exclude suites requiring original archives, legacy source or project
# tools. Their acceptance still runs in the main repository, never replaced here.
SUITES = (
    'test_worker', 'test_run_collection', 'test_market_frame', 'test_market_collect',
    'test_depth_frame', 'test_depth_collect', 'test_dividend_collect',
    'test_outbox', 'test_outbox_bundle', 'test_job_bundle', 'test_archive_store',
    'test_app_feed', 'test_app_publish', 'test_price_fallbacks', 'test_price_publication',
    'test_enrichment_context', 'test_runner_checkpoint', 'test_cloud_state', 'test_cloud_collect',
    'test_checkpoint_smoke','test_acquisition_admission','test_dividend_publication',
    'test_price_company_context', 'test_official_close_verify', 'test_official_close_collect',
    'test_official_close', 'test_official_review_dispatch', 'test_health_check', 'test_schedule_plan', 'test_receipt_history', 'test_recurring_schedule',
)
HELPERS = ('fixture_price', 'fixture_projection', 'fixture_official')


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'tests'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
