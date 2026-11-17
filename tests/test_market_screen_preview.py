"""Actual PHP controllers in a CLI-only fixture; no credentials or network."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


def render(page, enabled='true', state='AVAILABLE', mode='report', locale='fr'):
    result=subprocess.run(['php','tests/render_market_screen_fixture.php',page,enabled,state,mode,locale],
        cwd=ROOT,capture_output=True,text=True,check=True)
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.stdout


class MarketScreenPreviewTests(unittest.TestCase):
    def test_both_real_controllers_render_panel_and_recorded_content(self):
        for page in ('index','screener'):
            with self.subTest(page=page):
                data=json.loads(render(page))
                self.assertEqual(data['preview_requests'],1)
                self.assertEqual(data['source_requests'],0)
                self.assertGreater(data['legacy_requests'],0)
                self.assertEqual(data['snapshot_status'],'AVAILABLE')
                self.assertEqual(data['snapshot_rows'],3)

    def test_default_mode_keeps_existing_read_path_and_makes_no_preview_request(self):
        for page in ('index','screener'):
            data=json.loads(render(page,enabled='false'))
            self.assertEqual(data['preview_requests'],0)
            self.assertGreater(data['legacy_requests'],0)
            self.assertEqual(data['source_requests'],0)

    def test_disabled_failed_and_waiting_feeds_never_render_live_prices(self):
        for page in ('index','screener'):
            for state in ('DISABLED','WAITING','ERROR'):
                with self.subTest(page=page,state=state):
                    data=json.loads(render(page,state=state))
                    self.assertGreater(data['legacy_requests'],0)
                    self.assertEqual((data['source_requests'],data['snapshot_rows']),(0,0))
                    html=render(page,state=state,mode='html')
                    self.assertIn('Les cours récents sont indisponibles.',html)
                    self.assertNotIn('private-fixture-diagnostic',html)
                    self.assertNotIn('data-market-card ',html)

    def test_real_page_templates_show_reference_context_index_and_expiry(self):
        for page in ('index','screener'):
            html=render(page,mode='html')
            self.assertIn('Prix de référence',html)
            self.assertIn('Date de cotation inconnue.',html)
            self.assertIn('Date annoncée :',html)
            self.assertIn('data-market-expiry="2026-10-28T12:10:00+00:00"',html)
            self.assertIn('MASI',html)
            self.assertNotIn('infoAction.php?name=MASI',html)
            self.assertIn('1 234,56',html)
            if page == 'index':
                self.assertIn('tbody-gainers',html)
            else:
                self.assertIn('screenerTable',html)
