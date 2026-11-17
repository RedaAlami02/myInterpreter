<?php
function te($s) { return htmlspecialchars($s, ENT_QUOTES, 'UTF-8'); }
require __DIR__.'/../core/recorded_market_panel.php';
$now = new DateTimeImmutable('2026-11-13T22:00:00Z');
$rows = [
 ['c_name'=>'<Company>','pa'=>'216.00','date'=>'2026-11-12T12:00:00Z'],
 ['c_name'=>'Future','pa'=>'100','date'=>'2026-11-14T12:00:00Z'],
 ['c_name'=>'Invalid','pa'=>'NaN','date'=>'2026-11-12T12:00:00Z'],
];
ob_start(); $ok=render_recorded_market_panel($rows,$now); $html=ob_get_clean();
if (!$ok || !str_contains($html,'216,00') || !str_contains($html,'2026-11-12')
 || !str_contains($html,'&lt;Company&gt;') || str_contains($html,'<Company>')
 || str_contains($html,'Future') || str_contains($html,'Invalid') || str_contains($html,'data-market-expiry=')) {
 throw new RuntimeException('Recorded display safety regression');
}
echo "Recorded fallback: PASS\n";
