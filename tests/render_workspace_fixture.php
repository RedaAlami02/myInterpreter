<?php
// CLI-only render of real templates with invented data. Never execute controllers.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
session_start(['save_path' => sys_get_temp_dir()]);
chdir(dirname(__DIR__));
$page = $argv[1] ?? 'portfolio';
if (!in_array($page, ['portfolio', 'index', 'login'], true)) throw new RuntimeException('Unknown fixture');
$_SERVER['PHP_SELF'] = $_SERVER['SCRIPT_NAME'] = '/' . ($page === 'portfolio' ? 'portfolio.php' : 'index.php');
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SESSION = ['logged_in' => $page !== 'login', 'USER_ID' => 'fixture-user', 'USER_EMAIL' => 'demo@example.invalid', 'csrf_token' => 'fictional-test-token'];
// Load pure formatting/calculation helpers, explicitly excluding secret loading.
$config = file_get_contents('config/config.php');
$config = preg_replace('/^require_once[^\n]+secrets\.php[^\n]*\n/m', '', $config);
$config = preg_replace("/^define\\('ADMIN_USER_ID'.*$/m", "define('ADMIN_USER_ID', 'fixture-user');", $config);
eval('?>' . $config);
function aw_user_id() { return 'fixture-user'; }
require 'core/auth.php';
require 'core/sector_allocation.php';

$names = ['Atlas Industrie', 'Rive Banque', 'Noria Énergie', 'Orbe Services', 'Cap Finance', 'Ligne Télécom'];
$prices = [412, 535, 286, 128, 345, 92];
$costs = [380, 510, 260, 135, 320, 88];
$quantities = [140, 90, 120, 200, 60, 180];
$holdings = []; $chartValues = []; $chartBuys = [];
foreach ($names as $i => $name) {
    $holdings[] = ['c_name' => $name, 'quantity' => $quantities[$i]];
    $chartValues[] = $prices[$i] * $quantities[$i];
    $chartBuys[] = $costs[$i] * $quantities[$i];
}
$allCompanies = $chartNames = $names;
$totalCurrentVal = array_sum($chartValues); $totalBuyVal = array_sum($chartBuys);
$diffDisplay = $totalCurrentVal - $totalBuyVal;
$flash = [['type' => 'info', 'msg' => 'APERÇU — données fictives, aucune opération réelle.']];
$loadError = null; $lastSnapDate = $lastSync = '2026-10-18T12:00:00Z';
$activeTab = 'portfolio'; $divLines = []; $divYear = 2026;
$earnings = [['DATE' => '01/09/2026', 'VALUE' => 8000], ['DATE' => '18/10/2026', 'VALUE' => $diffDisplay]];
$sectorRows = [
    ['code' => 'DEMO-A', 'label' => 'Industrie (démo)', 'held' => 2, 'market' => 8],
    ['code' => 'DEMO-B', 'label' => 'Finance (démo)', 'held' => 2, 'market' => 6],
    ['code' => 'DEMO-C', 'label' => 'Services (démo)', 'held' => 2, 'market' => 7],
];
$sectorChartRows = $sectorRows;
for ($i = 4; $i <= 14; $i++) {
    $sectorRows[] = ['code' => 'DEMO-' . $i, 'label' => 'Secteur fictif ' . $i, 'held' => 1, 'market' => 8];
}
$sectorAllocation = ['unclassified' => [], 'held_companies' => []];
$sectorDirectory = [];
$isLoggedIn = $page !== 'login'; $loginError = ''; $isSignUp = false;
$dateLabel = 'Dimanche 18 octobre 2026 · démonstration'; $timeLabel = '12:00';
$isMarketOpen = false; $sessionLabel = 'Données fictives';
$companyCount = $ratedCount = $totalCompanies = 6; $snapshotDays = 365; $totalDataRows = 1500;
$oldestDate = '2025-10-18'; $newestDate = '2026-10-18'; $avgPER = 18.5; $allGreen = 2;
$masiFullSeries = [];
for ($i = 0; $i < 60; $i++) {
    $masiFullSeries[] = ['d' => date('Y-m-d', strtotime('-' . (59 - $i) . ' days')), 'v' => 14000 + $i * 10 + sin($i) * 20];
}
$masiLast = end($masiFullSeries)['v']; $masiChange = 35; $masiChangePct = .25;
$topGainers = $topLosers = $topScored = [];
foreach ($names as $i => $name) {
    $row = ['name' => $name, 'abbr' => 'D' . $i, 'PA' => $prices[$i], 'trend' => $i % 2 ? -.5 : 1.2, 'PER' => 18.5, 'PEG' => .8, 'PR' => 1.2, 'PB' => 1.6, 'score' => 4];
    if ($row['trend'] > 0) $topGainers[] = $row; else $topLosers[] = $row;
    $topScored[] = $row;
}
$source = file_get_contents($page === 'portfolio' ? 'portfolio.php' : 'index.php');
$template = substr($source, strpos($source, '<!DOCTYPE html>'));
// FIFO fetching belongs to integration tests with a safe account, not screenshots.
$template = str_replace("<?php require_once 'statistics.php'; stats(); ?>", '<p class="p-3 muted">Historique fictif — aucune transaction chargée.</p>', $template);
eval('?>' . $template);
session_destroy();
