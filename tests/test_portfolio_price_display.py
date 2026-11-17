import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


def php(*args):
    result=subprocess.run(['php',*args],cwd=ROOT,capture_output=True,text=True,check=True)
    if result.stderr:raise AssertionError(result.stderr)
    return result.stdout


class PortfolioPriceDisplayTests(unittest.TestCase):
    def test_invalid_trade_forms_show_errors_without_writes(self):
        for mode in ('invalid-buy', 'zero-buy', 'both-trades'):
            with self.subTest(mode=mode):
                report=json.loads(php('tests/render_portfolio_controller_fixture.php',mode))
                self.assertEqual(report['write_calls'],0)
                self.assertEqual(report['flash'][0]['type'],'error')

    def test_disabled_valuation_post_never_calls_a_writer(self):
        report=json.loads(php('tests/render_portfolio_controller_fixture.php','disabled-post'))
        self.assertEqual(report['write_calls'],0)
        self.assertEqual(report['valuation_status'],'DISABLED')

    def test_actual_get_controller_never_writes_or_sums_partial_prices(self):
        partial=json.loads(php('tests/render_portfolio_controller_fixture.php','partial'))
        self.assertIsNone(partial['totals']['value'])
        self.assertIsNone(partial['totals']['pnl'])
        self.assertEqual(partial['totals']['invested'],35)
        self.assertEqual(partial['write_calls'],0)
        complete=json.loads(php('tests/render_portfolio_controller_fixture.php','complete'))
        self.assertEqual(complete['totals']['value'],45)
        self.assertFalse(complete['totals']['portfolio_valuation_eligible'])
        self.assertEqual(complete['write_calls'],0)

    def test_controller_holding_cap_suppresses_all_totals_even_with_all_prices(self):
        report=json.loads(php('tests/render_portfolio_controller_fixture.php','capped'))
        self.assertEqual(report['totals']['covered'],500)
        self.assertFalse(report['holdings_complete'])
        for key in ['invested','value','pnl']:self.assertIsNone(report['totals'][key])

    def test_actual_template_omits_partial_value_chart_and_labels_reference_estimates(self):
        html=php('tests/render_workspace_fixture.php','portfolio','fr','incomplete-prices')
        self.assertNotIn('id="chartCurrent"',html)
        self.assertNotIn("makeDoughnut('chartCurrent'",html)
        self.assertIn('Cours enregistrés, pas de cotations en direct.',html)
        self.assertIn('Total indisponible',html)
        self.assertRegex(html, r'stat-chip__value mono t-cyan[^>]*>—</span>')
        self.assertIn('name="record_valuation" class="btn btn-ghost btn-sm" disabled',html)

    def test_capped_template_omits_all_portfolio_allocation_charts(self):
        html=php('tests/render_workspace_fixture.php','portfolio','fr','incomplete-holdings')
        self.assertNotIn('id="chartCurrent"',html)
        self.assertNotIn('id="chartBuy"',html)
        self.assertNotIn("makeDoughnut('chartBuy'",html)


if __name__=='__main__':unittest.main()
