<?php
require __DIR__ . '/../core/company_disclosures.php';
function verify($condition, $label) { if (!$condition) throw new RuntimeException($label); }
$r = reviewed_company_disclosure('T2S');
verify($r['fields']['fiscal_year'] === 2025, 'Reported fiscal year');
verify($r['fields']['na'] === 22584118, 'Post-capital-increase shares');
verify(abs($r['fields']['bpa'] - 9.06) < .001, 'Normalized EPS');
verify(abs(array_sum(array_column($r['shareholders'], 'pct')) - 100) < .001, 'Dated shareholder total');
$d = apply_reviewed_disclosure('T2S', ['error' => 'unavailable']);
verify(!isset($d['error']) && $d['computed']['net_profit'] === 204.576, 'Offline reviewed fallback');
verify($d['interim'][1]['net_profit'] === 91, 'Interim earnings kept separate');
$d = apply_reviewed_disclosure('T2S', ['charts' => ['rnpg' => ['2025p' => 204.5, '2026p' => 241]]]);
verify(!isset($d['charts']['rnpg']['2025p']) && isset($d['charts']['rnpg']['2026p']), 'Only obsolete forecast removed');
$d = apply_reviewed_disclosure('T2S', ['charts' => ['rnpg' => ['2026' => 250]], 'computed' => ['net_profit' => 250]]);
verify($d['computed']['net_profit'] === 250, 'Newer reported accounts preserved');
verify(apply_reviewed_disclosure('OTHER', ['error' => 'missing']) === ['error' => 'missing'], 'Other companies unchanged');
echo "PASS reviewed company disclosures\n";
