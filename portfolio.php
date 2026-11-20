<?php
ob_start();
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/core/i18n.php';
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/auth.php';
require_once 'core/dividends.php';
require_once 'core/sector_allocation.php';
require_once 'core/portfolio_prices.php';
require_once 'core/current_prices.php';
requireLogin();

$uid     = aw_user_id();
$session = aw_session();
$flash   = [];
$tradeInputValid = true;
if (isset($_POST['add_buy']) || isset($_POST['add_sell'])) {
    csrf_verify();
    foreach (['NAME', 'NAME2', 'NUMBER', 'NUMBER2', 'PRIX_ACHAT', 'PRIX_VENTE', 'trade_request_id'] as $field) {
        if (isset($_POST[$field]) && !is_string($_POST[$field])) $tradeInputValid = false;
    }
    if (isset($_POST['add_buy'], $_POST['add_sell'])) $tradeInputValid = false;
    if (!$tradeInputValid) {
        $flash[] = ['type' => 'error', 'msg' => 'Formulaire invalide. Vérifiez les valeurs et réessayez.'];
    }
}

// ─── Add buy ──────────────────────────────────────────────
if ($tradeInputValid && isset($_POST['add_buy'])) {
    csrf_verify();
    $name   = trim($_POST['NAME']      ?? '');
    $number = (float) ($_POST['NUMBER']    ?? 0);
    $price  = (float) ($_POST['PRIX_ACHAT']?? 0);
    if ($name && is_finite($number) && is_finite($price) && $number > 0 && $price > 0) {
        try {
            sb_app()->recordTrade(sb_access_token(), $_POST['trade_request_id'] ?? '', 'buy', $name,
                $_POST['NUMBER'] ?? '', $_POST['PRIX_ACHAT'] ?? '');
            $flash[] = ['type' => 'success', 'msg' => t('Achat de {quantity} × {name} enregistré.', ['quantity' => $number, 'name' => $name])];
        } catch (Throwable $e) {
            error_log('[myInterpreter] add_buy failed');
            $flash[] = ['type' => 'error', 'msg' => 'Impossible d’enregistrer cet achat. Vérifiez les valeurs et réessayez.'];
        }
    } else {
        $flash[] = ['type' => 'error', 'msg' => 'Indiquez une société, une quantité et un prix strictement positifs.'];
    }
}

// ─── Add sell ─────────────────────────────────────────────
if ($tradeInputValid && isset($_POST['add_sell'])) {
    csrf_verify();
    $name   = trim($_POST['NAME2']      ?? '');
    $number = (float) ($_POST['NUMBER2']   ?? 0);
    $price  = (float) ($_POST['PRIX_VENTE']?? 0);
    if ($name && is_finite($number) && is_finite($price) && $number > 0 && $price > 0) {
        try {
            sb_app()->recordTrade(sb_access_token(), $_POST['trade_request_id'] ?? '', 'sell', $name,
                $_POST['NUMBER2'] ?? '', $_POST['PRIX_VENTE'] ?? '');
            header('Location: portfolio.php'); exit();
        } catch (Throwable $e) {
            error_log('[myInterpreter] add_sell failed');
            $flash[] = ['type' => 'error', 'msg' => 'Impossible d’enregistrer cette vente. Vérifiez la quantité et réessayez.'];
        }
    } else {
        $flash[] = ['type' => 'error', 'msg' => 'Indiquez une société, une quantité et un prix strictement positifs.'];
    }
}

// Explicit maintenance action. The page never writes a valuation while loading.
$valuationStatus = null;
if (isset($_POST['record_valuation'])) {
    csrf_verify();
    try {
        $valuationResult = MYINTERPRETER_PORTFOLIO_VALUATION
            ? sb_app()->recordHistoryValuation(sb_access_token()) : ['status' => 'DISABLED'];
        $valuationStatus = $valuationResult['status'];
        if ($valuationStatus === 'EXISTING' && ($valuationResult['basis'] ?? '') === 'PREEXISTING_UNVERIFIED') {
            $valuationStatus = 'EXISTING_UNVERIFIED';
        }
    } catch (Throwable $e) {
        error_log('[myInterpreter] record_valuation failed');
        $valuationStatus = 'FAILED';
    }
}
$valuationLabels = [
    'CREATED' => 'Valorisation enregistrée.',
    'EXISTING' => 'Valorisation déjà enregistrée aujourd’hui.',
    'EXISTING_UNVERIFIED' => 'Le relevé existant est conservé ; sa clôture officielle n’est pas vérifiée.',
    'EMPTY' => 'Aucune position à valoriser.',
    'PRICE_UNAVAILABLE' => 'Prix de clôture indisponible : rien n’a été enregistré.',
    'OUTSIDE_WINDOW' => 'Valorisation indisponible hors de la fenêtre autorisée.',
    'DISABLED' => 'Valorisation indisponible pour le moment.',
    'RECOVERY_REQUIRED' => 'La récupération du portefeuille doit être terminée avant la valorisation.',
    'FAILED' => 'Valorisation indisponible pour le moment.',
];

// Once a day, record the valuation without being asked. It is idempotent and
// skipped entirely when the close for a holding is missing.
$valuationAuto = null;
if ($uid && MYINTERPRETER_PORTFOLIO_VALUATION) {
    $valuationDay = (new DateTimeImmutable('now', new DateTimeZone('Africa/Casablanca')))->format('Y-m-d');
    if (($_SESSION['valuation_history_day'] ?? null) !== $valuationDay) {
        try {
            $auto = sb_app()->recordHistoryValuation(sb_access_token());
            $valuationAuto = $auto['status'];
            $_SESSION['valuation_history_day'] = $valuationDay;
        } catch (Throwable $e) {
            error_log('[myInterpreter] automatic valuation failed');
        }
    }
}

// Load portfolio data; the daily P&L writer runs separately from page requests.
$holdingsDocs = [];
$latestData   = [];
$earningsDocs = [];
$loadError    = null;

try {
    // Independent reads overlap; private queries retain their user and session.
    $portfolioData = aw_multi_list_docs([
        'holdings' => ['portefeuille', [q_equal('user_id', $uid), q_limit(500)], $session],
        'earnings' => ['benefits', [q_equal('user_id', $uid), q_order_desc('date'), q_limit(500)], $session],
    ]);
    $holdingsDocs = $portfolioData['holdings'];

    $earningsDocs = $portfolioData['earnings'];
} catch (Throwable $e) {
    error_log('[myInterpreter] portfolio.php data load error: ' . $e->getMessage());
    $loadError = 'Impossible de charger les données. Veuillez réessayer.';
}

// Recovered latest-price rows are dated references, never implicitly current.
$holdingsComplete = $loadError === null && count($holdingsDocs) < 500;
$priceMap = [];
try { $lpDocs = aw_list_docs('latest_prices', [q_limit(500)]); }
catch (Throwable $error) { $lpDocs = []; error_log('[myInterpreter] recorded prices unavailable'); }
$currentQuoteCount = 0;
if (MYINTERPRETER_MARKET_PREVIEW) {
    try {
        $currentQuotes = current_market_prices(sb_market_preview());
        $currentQuoteCount = count($currentQuotes);
        $lpDocs = overlay_current_prices($lpDocs, $currentQuotes);
    } catch (Throwable $error) { /* Keep old references explicitly dated. */ }
}
$recordedPriceMap = portfolio_recorded_prices($lpDocs);
foreach ($recordedPriceMap as $name => $quote) {
    if ($quote['price'] !== null) $priceMap[$name] = $quote['price'];
}
$referenceTotals = portfolio_reference_totals($holdingsDocs, $recordedPriceMap, $holdingsComplete);

// ─── Expected dividend income ─────────────────────────────
// One query for the whole year, then joined in memory against the holdings.
// Quantities come from `portefeuille`, so this is what the user would actually
// receive — not a market-wide yield.
$divYear   = (int)date('Y');
$divToday  = date('Y-m-d');
$divByName = [];
foreach (div_for_year($divYear) as $d) {
    $n = $d['c_name'] ?? '';
    if ($n !== '') $divByName[$n][] = $d;
}

$holdings = [];
$sectorHoldings = [];
$chartNames = []; $chartValues = []; $chartBuys = [];
$totalCurrentVal = 0.0; $totalBuyVal = 0.0;

foreach ($holdingsDocs as $h) {
    $name   = $h['c_name'];
    $qty    = (float)($h['quantity'] ?? 0);
    $cost   = (float)($h['total_cost'] ?? 0);
    $pa     = $priceMap[$name] ?? 0;
    $curVal = $pa > 0 ? $qty * $pa : 0;

    $holdings[]    = $h;
    $sectorHoldings[] = ['c_name' => $name, 'quantity' => $qty,
        'current_value' => round($curVal, 2), 'has_price' => $pa > 0];
    $chartNames[]  = $name;
    $chartValues[] = round($curVal, 2);
    $chartBuys[]   = round($cost, 2);
    $totalCurrentVal += $curVal;
    $totalBuyVal     += $cost;

    if ($pa <= 0) {
        $flash[] = ['type' => 'warn', 'msg' => t('Prix introuvable pour « {name} ».', ['name' => $name])];
    }
}

$totalCurrentVal = $referenceTotals['value'];
$totalBuyVal = $referenceTotals['invested'];
$diffDisplay = $referenceTotals['pnl'];
$sectorAllocation = market_sector_allocation($sectorHoldings);
$sectorRows = $sectorAllocation['rows'];
$sectorChartRows = array_values(array_filter($sectorRows, fn($row) => $row['held'] > 0));
if ($sectorAllocation['unclassified']) {
    $sectorChartRows[] = ['code' => 'OTHER', 'label' => 'Non classé', 'held' => count($sectorAllocation['unclassified'])];
}
$earnings    = array_map(fn($d) => ['DATE' => fmt_date($d['date']), 'VALUE' => $d['value']], $earningsDocs);

// ─── Dividend income rows, one per holding that pays ──────
// Aggregated by company first: two lots of the same stock are one payment line,
// otherwise the same dividend would appear twice and the total would be right
// only by accident.
$divQty = [];
foreach ($holdingsDocs as $h) {
    $n = $h['c_name'] ?? '';
    if ($n !== '') $divQty[$n] = ($divQty[$n] ?? 0) + (float)($h['quantity'] ?? 0);
}

$divLines = [];
$divTotalYear = 0.0; $divTotalUpcoming = 0.0; $divPaying = 0; $divPayingNames = [];
foreach ($divQty as $name => $qty) {
    if ($qty <= 0 || empty($divByName[$name])) continue;
    $paid = false;
    foreach ($divByName[$name] as $d) {
        $amt = (float)($d['amount'] ?? 0);
        if ($amt <= 0) continue;
        $gross    = $amt * $qty;
        $when     = div_date_end($d) ?: div_date($d);
        $upcoming = $when && $when >= $divToday;
        $divLines[] = [
            'name'      => $name,
            'qty'       => $qty,
            'amount'    => $amt,
            'gross'     => $gross,
            'row'       => $d,
            'upcoming'  => $upcoming,
            'sort'      => div_date($d) ?: '9999-99-99',
            'yield'     => div_yield($d, $priceMap[$name] ?? null),
        ];
        $divTotalYear += $gross;
        if ($upcoming) $divTotalUpcoming += $gross;
        $paid = true;
    }
    if ($paid) { $divPaying++; $divPayingNames[$name] = true; }
}
usort($divLines, fn($a, $b) => strcmp($a['sort'], $b['sort']));
$divNonPayers = array_values(array_diff(
    array_keys(array_filter($divQty, fn($qty) => $qty > 0)),
    array_keys($divPayingNames)));
sort($divNonPayers);
$divYieldOnCost = $totalBuyVal > 0 ? $divTotalYear / $totalBuyVal * 100 : null;

// Companies list — session-cached for 5 min to avoid re-fetching on every load
if (empty($_SESSION['company_list_cache']) || (time() - ($_SESSION['company_list_ts'] ?? 0)) > 300) {
    try {
        $companyDocs  = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
        $allCompanies = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));
        $_SESSION['company_list_cache'] = $allCompanies;
        $_SESSION['company_list_ts']    = time();
    } catch (Throwable $e) {
        error_log('[myInterpreter] portfolio.php company list error: ' . $e->getMessage());
        $allCompanies = $_SESSION['company_list_cache'] ?? [];
    }
} else {
    $allCompanies = $_SESSION['company_list_cache'];
}
$sectorDirectory = market_sector_directory($allCompanies);

// Default active tab
$activeTab = $_GET['tab'] ?? 'portfolio';
?>
<!DOCTYPE html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title><?= te('myInterpreter | Portefeuille') ?></title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/portfolio.css?v=6" rel="stylesheet">
  <link href="assets/css/statistics.css?v=3" rel="stylesheet">
  <?php require 'core/theme.php'; ?>
</head>
<body class="workspace workspace-portfolio">
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">

  <div class="portfolio-wrap animate-up">
    <header class="workspace-heading">
      <h1><?= te('Portefeuille') ?></h1>
      <p><?= te('Vos positions, leur répartition et vos opérations au même endroit.') ?></p>
    </header>

    <!-- Flash messages -->
    <?php foreach ($flash as $f): ?>
      <div class="alert alert-<?= $f['type'] ?>"><i class="fas fa-<?= $f['type']==='success'?'check-circle':'exclamation-triangle' ?> me-2"></i><?= te($f['msg']) ?></div>
    <?php endforeach; ?>
    <?php if ($loadError): ?>
      <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i><?= te($loadError) ?></div>
    <?php endif; ?>

    <!-- Tab navigation -->
    <div class="tab-nav" role="tablist">
      <button class="tab-btn <?= $activeTab==='portfolio'?'active':'' ?>" onclick="switchTab('portfolio')" type="button">
        <i class="fas fa-wallet"></i> <?= te('Portefeuille') ?>
      </button>
      <button class="tab-btn <?= $activeTab==='transactions'?'active':'' ?>" onclick="switchTab('transactions')" type="button">
        <i class="fas fa-exchange-alt"></i> <?= te('Transactions') ?>
      </button>
      <button class="tab-btn <?= $activeTab==='history'?'active':'' ?>" onclick="switchTab('history')" type="button">
        <i class="fas fa-chart-bar"></i> <?= te('Historique P&L') ?>
      </button>
    </div>

    <!-- ── Tab 1: Portfolio ───────────────────────────────────── -->
    <div id="tab-portfolio" class="tab-panel <?= $activeTab==='portfolio'?'active':'' ?>">

      <!-- Summary chips -->
      <div class="pf-summary stagger-children">
        <div class="stat-chip">
          <span class="stat-chip__value mono t-cyan"><?= $totalCurrentVal !== null ? number_format($totalCurrentVal,2) : '—' ?></span>
          <span class="stat-chip__label"><?= te('Valeur actuelle (MAD)') ?></span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip__value mono t-violet"><?= $totalBuyVal !== null ? number_format($totalBuyVal,2) : '—' ?></span>
          <span class="stat-chip__label"><?= te('Montant investi (MAD)') ?></span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip__value mono <?= $diffDisplay === null ? '' : ($diffDisplay >= 0 ? 't-emerald' : 't-rose') ?>">
            <?= $diffDisplay !== null ? ($diffDisplay >= 0 ? '+' : '') . number_format($diffDisplay, 2) : '—' ?>
          </span>
          <span class="stat-chip__label"><?= te('Gain / Perte') ?></span>
        </div>
      </div>
      <p class="muted"><?= $currentQuoteCount > 0 ? te('Dernières cotations collectées et références datées ; valorisation indicative, pas une clôture officielle.') : te('Cours enregistrés, pas de cotations en direct.') ?>
        <?php if ($referenceTotals['complete']): ?>
          <?php if ($referenceTotals['day'] === $referenceTotals['day_latest']): ?>
            <?= htmlspecialchars($referenceTotals['day']) ?> (UTC).
          <?php else: ?>
            <?= te('clôtures du {from} au {to} (UTC) ; chaque ligne non traitée garde son dernier cours.',
                ['from' => $referenceTotals['day'], 'to' => $referenceTotals['day_latest']]) ?>
          <?php endif; ?>
        <?php else: ?>
          <?= te('Total indisponible : cours manquants ou positions incomplètes.') ?>
        <?php endif; ?>
      </p>

      <?php require __DIR__ . '/core/holdings_table.php'; ?>

      <!-- Charts -->
      <?php if (!empty($chartNames) && $holdingsComplete): ?>
      <div class="charts-viewport mb-4">
        <div class="charts-track" id="allocationTrack">
          <div class="charts-grid charts-page" id="allocationValues">
            <div class="chart-card">
              <h5><i class="fas fa-circle-dot me-2 t-cyan"></i><?= te('Répartition par valeur') ?></h5>
              <?php if ($referenceTotals['complete']): ?>
              <div class="chart-canvas"><canvas id="chartCurrent"></canvas></div>
              <?php else: ?><p class="muted"><?= te('Estimation indisponible') ?></p><?php endif; ?>
            </div>
            <div class="chart-card">
              <div class="chart-heading">
                <h5><i class="fas fa-circle-dot me-2 t-violet"></i><?= te('Répartition valeur d\'achat') ?></h5>
                <button class="chart-switch chart-switch--next" type="button" id="showSectors" aria-label="<?= te('Afficher la répartition par secteurs') ?>" title="<?= te('Voir les secteurs') ?>"><i class="fas fa-arrow-right" aria-hidden="true"></i></button>
              </div>
              <div class="chart-canvas"><canvas id="chartBuy"></canvas></div>
            </div>
          </div>
          <div class="charts-grid charts-page" id="allocationSectors" aria-hidden="true" inert>
            <div class="chart-card">
              <div class="chart-heading">
                <button class="chart-switch chart-switch--previous" type="button" id="showValues" aria-label="<?= te('Afficher la répartition par société') ?>" title="<?= te('Voir les sociétés') ?>"><i class="fas fa-arrow-left" aria-hidden="true"></i></button>
                <h5><i class="fas fa-circle-dot me-2 t-cyan"></i><?= te('Répartition par secteur') ?></h5>
              </div>
              <p class="chart-caption"><?= te('Part des sociétés détenues · une société compte une fois') ?></p>
              <div class="chart-canvas"><canvas id="chartSectors"></canvas></div>
              <?php if (!$sectorChartRows): ?><p class="sector-note"><?= te('Aucune société détenue à répartir.') ?></p><?php endif; ?>
              <?php if ($sectorAllocation['unclassified']): ?>
                <p class="sector-note"><?= te('Hors classement officiel :') ?> <?= htmlspecialchars(implode(', ', $sectorAllocation['unclassified'])) ?></p>
              <?php endif; ?>

            </div>
            <div class="chart-card">
              <h5><i class="fas fa-bars me-2 t-violet"></i><?= te('Couverture des secteurs') ?></h5>
              <p class="chart-caption"><?= te('Sociétés détenues / sociétés cotées · Bourse de Casablanca,') ?> <?= MARKET_SECTOR_DATE ?></p>
              <div class="sector-list" role="list">
                <?php foreach ($sectorRows as $row):
                  $fill = $row['market'] > 0 ? min(100, $row['held'] / $row['market'] * 100) : 0;
                ?>
                  <a class="sector-item" role="listitem" data-sector="<?= htmlspecialchars($row['code']) ?>" href="infoAction.php?sector=<?= urlencode($row['code']) ?>#companyDirectory" aria-label="Voir les sociétés du secteur <?= te($row['label']) ?>">
                    <div class="sector-item__heading"><span><?= te($row['label']) ?></span><strong><?= $row['held'] ?>/<?= $row['market'] ?></strong></div>
                    <div class="sector-item__track"><span style="width:<?= number_format($fill, 2, '.', '') ?>%"></span></div>
                  </a>
                <?php endforeach; ?>
              </div>
            </div>
          </div>
        </div>
      </div>
      <?php endif; ?>

      <!-- ── Revenus de dividendes ─────────────────────────── -->
      <?php if ($divLines): ?>
      <div class="div-panel mb-4">
        <div class="div-panel-head">
          <h5><i class="fas fa-coins me-2 t-emerald"></i><?= te('Revenus de dividendes') ?> <?= $divYear ?></h5>
          <div class="div-panel-totals">
            <div class="div-total">
              <span class="div-total-val"><?= $holdingsComplete ? number_format($divTotalYear, 2, ',', ' ') : '—' ?></span>
              <span class="div-total-lbl"><?= te('MAD sur l\'année') ?></span>
            </div>
            <?php if ($divTotalUpcoming > 0): ?>
            <div class="div-total">
              <span class="div-total-val t-cyan"><?= $holdingsComplete ? number_format($divTotalUpcoming, 2, ',', ' ') : '—' ?></span>
              <span class="div-total-lbl"><?= te('MAD à venir') ?></span>
            </div>
            <?php endif; ?>
            <?php if ($divYieldOnCost !== null): ?>
            <div class="div-total">
              <span class="div-total-val t-emerald"><?= number_format($divYieldOnCost, 2, ',', ' ') ?>&nbsp;%</span>
              <span class="div-total-lbl"><?= te('rendement / prix d\'achat') ?></span>
            </div>
            <?php endif; ?>
          </div>
        </div>

        <div class="card-glass overflow-x-auto">
          <table class="tbl">
            <thead><tr>
              <th><?= te('Société') ?></th>
              <th class="num"><?= te('Actions') ?></th>
              <th class="num"><?= te('MAD/action') ?></th>
              <th class="num"><?= te('Rendement indicatif') ?></th>
              <th><?= te('Détachement') ?></th>
              <th><?= te('Paiement') ?></th>
              <th class="num"><?= te('Montant brut') ?></th>
            </tr></thead>
            <tbody>
            <?php foreach ($divLines as $l): $r = $l['row']; ?>
              <tr class="<?= $l['upcoming'] ? 'div-upcoming' : 'div-done' ?>">
                <td>
                  <a href="infoAction.php?name=<?= urlencode($l['name']) ?>" class="t-cyan">
                    <?= htmlspecialchars($l['name']) ?></a>
                  <?php if (!div_confirmed($r)): ?>
                    <span class="div-badge estimated"><?= te('prévu') ?></span>
                  <?php endif; ?>
                  <?php if (strcasecmp((string)($r['frequency'] ?? ''), 'Trimestriel') === 0): ?>
                    <span class="div-badge quarterly"><?= te('trim.') ?></span>
                  <?php endif; ?>
                </td>
                <td class="num mono"><?= number_format($l['qty'], 0, ',', ' ') ?></td>
                <td class="num mono"><?= number_format($l['amount'], 2, ',', ' ') ?></td>
                <td class="num mono"><?= $l['yield'] === null ? '—' : number_format($l['yield'], 2, ',', ' ') . '&nbsp;%' ?>
                  <?php if ($l['yield'] !== null && !empty($recordedPriceMap[$l['name']]['day'])): ?>
                    <small class="muted"><?= htmlspecialchars($recordedPriceMap[$l['name']]['day']) ?> UTC</small>
                  <?php endif; ?>
                </td>
                <td class="date"><?= fmt_date($r['ex_date'] ?? '', '—') ?></td>
                <td class="date"><?= div_fmt_date($r) ?></td>
                <td class="num mono div-gross"><?= number_format($l['gross'], 2, ',', ' ') ?></td>
              </tr>
            <?php endforeach; ?>
            </tbody>
          </table>
        </div>

        <p class="fund-source mt-2">
          <i class="fas fa-info-circle me-1"></i>
          <?= $divPaying ?> <?= te('de vos') ?> <?= count($divQty) ?> <?= te('positions versent un dividende cette année.') ?>
          <?php if ($divNonPayers): ?>
            <span class="muted"><?= $divPaying === 0 ? '' : te('Sans dividende cette année :') ?>
              <?php foreach ($divNonPayers as $i => $payer): ?><?= $i ? ', ' : '' ?><a class="t-cyan" href="infoAction.php?name=<?= urlencode($payer) ?>"><strong><?= htmlspecialchars($payer) ?></strong></a><?php endforeach; ?>.</span>
          <?php endif; ?>
          <span class="muted"><?= te('Montants bruts, avant retenue à la source · les lignes « prévu » n\'ont pas encore été votées en assemblée générale') ?></span>
        </p>
      </div>
      <?php endif; ?>

    </div><!-- tab-portfolio -->

    <!-- ── Tab 2: Transactions ───────────────────────────────── -->
    <div id="tab-transactions" class="tab-panel <?= $activeTab==='transactions'?'active':'' ?>">

      <div class="forms-grid">

        <!-- Buy form -->
        <div class="form-card">
          <h4 class="t-cyan"><i class="fas fa-plus-circle"></i> <?= te('Ajouter un achat') ?></h4>
          <form method="POST" action="" data-loading>
            <?= csrf_field() ?>
            <?php if (app_uses_supabase()): ?>
            <input type="hidden" name="trade_request_id" value="<?= htmlspecialchars(sb_trade_request_id(), ENT_QUOTES) ?>">
            <?php endif; ?>
            <datalist id="companyListBuy">
              <?php foreach ($allCompanies as $n): ?><option value="<?= htmlspecialchars($n) ?>"><?php endforeach; ?>
            </datalist>
            <div class="mb-3">
              <label class="form-label small muted"><?= te('Société') ?></label>
              <input type="text" name="NAME" list="companyListBuy" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label small muted"><?= te('Nombre d\'actions') ?></label>
              <input type="number" name="NUMBER" class="form-control" step="1" min="1" required>
            </div>
            <div class="mb-4">
              <label class="form-label small muted"><?= te('Prix d\'achat (MAD)') ?></label>
              <input type="number" name="PRIX_ACHAT" class="form-control" step="0.01" min="0.01" required>
            </div>
            <button type="submit" name="add_buy" class="btn btn-cyan w-100" data-loading-text="Enregistrement...">
              <i class="fas fa-plus"></i> <?= te('Ajouter l\'achat') ?>
            </button>
          </form>
        </div>

        <!-- Sell form -->
        <div class="form-card">
          <h4 class="t-rose"><i class="fas fa-minus-circle"></i> <?= te('Enregistrer une vente') ?></h4>
          <form method="POST" action="" data-loading>
            <?= csrf_field() ?>
            <?php if (app_uses_supabase()): ?>
            <input type="hidden" name="trade_request_id" value="<?= htmlspecialchars(sb_trade_request_id(), ENT_QUOTES) ?>">
            <?php endif; ?>
            <datalist id="companyListSell">
              <?php foreach ($allCompanies as $n): ?><option value="<?= htmlspecialchars($n) ?>"><?php endforeach; ?>
            </datalist>
            <div class="mb-3">
              <label class="form-label small muted"><?= te('Société') ?></label>
              <input type="text" name="NAME2" list="companyListSell" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label small muted"><?= te('Nombre d\'actions à vendre') ?></label>
              <input type="number" name="NUMBER2" class="form-control" step="1" min="1" required>
            </div>
            <div class="mb-4">
              <label class="form-label small muted"><?= te('Prix de vente (MAD)') ?></label>
              <input type="number" name="PRIX_VENTE" class="form-control" step="0.01" min="0.01" required>
            </div>
            <button type="submit" name="add_sell" class="btn btn-rose w-100" data-loading-text="Enregistrement...">
              <i class="fas fa-minus"></i> <?= te('Enregistrer la vente') ?>
            </button>
          </form>
        </div>

      </div><!-- .forms-grid -->

    </div><!-- tab-transactions -->

    <!-- ── Tab 3: FIFO History ───────────────────────────────── -->
    <div id="tab-history" class="tab-panel <?= $activeTab==='history'?'active':'' ?>">

      <div class="card-glass mb-4" style="padding:16px;display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap">
        <div>
          <strong><i class="fas fa-gauge-high me-2 t-emerald"></i><?= te('Valorisation du jour') ?></strong>
          <p class="muted" style="margin:4px 0 0;font-size:0.85rem"><?= te('Enregistrement indisponible tant que les cours officiels de clôture ne sont pas vérifiés.') ?></p>
          <?php if ($valuationStatus !== null): ?>
            <p style="margin:6px 0 0;font-size:0.85rem;color:<?= in_array($valuationStatus, ['CREATED', 'EXISTING'], true) ? 'var(--pos)' : 'var(--neg)' ?>">
              <?= te($valuationLabels[$valuationStatus] ?? $valuationLabels['FAILED']) ?>
            </p>
          <?php endif; ?>
        </div>
        <form method="POST" action="" data-loading>
          <?= csrf_field() ?>
          <button type="submit" name="record_valuation" class="btn btn-ghost btn-sm" <?= MYINTERPRETER_PORTFOLIO_VALUATION ? '' : 'disabled' ?>>
            <i class="fas fa-clock-rotate-left"></i> <?= te('Enregistrer la valorisation') ?>
          </button>
        </form>
      </div>

      <?php if (!empty($earnings)): ?>
      <div class="chart-card mb-4">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
          <h5 style="margin:0"><i class="fas fa-chart-line me-2 t-emerald"></i><?= te('Évolution P&L') ?></h5>
          <span id="pnlHoverVal" style="font-family:var(--font-mono);font-size:0.88rem;font-weight:700;color:var(--cyan)"></span>
        </div>
        <div style="position:relative;height:200px"><canvas id="chartPnl"></canvas></div>
      </div>
      <?php endif; ?>

      <div class="card-glass overflow-x-auto">
        <?php require_once 'statistics.php'; stats(); ?>
      </div>
    </div>

  </div><!-- .portfolio-wrap -->
  </main>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels"></script>
<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js?v=2"></script>
<script src="assets/js/holdings_sort.js?v=1"></script>
<script>
/* ── Tab switching ─────────────────────────────────────── */
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector(`[onclick="switchTab('${name}')"]`).classList.add('active');
}

/* ── Collapsible column groups (frais / seuil) — collapsed by default ── */
function toggleCols(group, btn) {
  const table = document.getElementById('holdingsTbl');
  const cells = [...table.querySelectorAll('th, td')];
  cells.forEach(cell => cell.getAnimations().forEach(animation => animation.cancel()));
  const before = new Map(cells.filter(cell => cell.offsetWidth).map(cell => [cell, cell.getBoundingClientRect()]));
  const open = table.classList.toggle('show-' + group);
  btn.classList.toggle('active', open);
  btn.setAttribute('aria-pressed', String(open));
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  for (const cell of cells) {
    if (!cell.offsetWidth || cell.cellIndex === 0) continue;
    const old = before.get(cell), next = cell.getBoundingClientRect();
    cell.animate([
      {transform: old ? `translateX(${old.left - next.left}px)` : 'translateX(8px)', opacity: old ? 1 : 0},
      {transform: 'translateX(0)', opacity: 1}
    ], {duration: 240, easing: 'cubic-bezier(.2,.7,.2,1)'});
  }
}

/* ── Doughnut charts ───────────────────────────────────── */
<?php if (!empty($chartNames) && $holdingsComplete): ?>
Chart.register(ChartDataLabels);

const PALETTE = [
  '#22d3ee', '#818cf8', '#10b981', '#f59e0b', '#f43f5e', '#a78bfa',
  '#34d399', '#fb923c', '#facc15', '#f472b6', '#38bdf8', '#84cc16',
  '#c084fc', '#2dd4bf', '#f87171', '#60a5fa', '#e879f9', '#14b8a6',
  '#fbbf24', '#6366f1', '#4ade80', '#fb7185', '#06b6d4', '#d946ef'
];

function makeDoughnut(id, labels, data) {
  const ctx = document.getElementById(id);
  if (!ctx || !data.length) return;
  new Chart(ctx, {
    type: 'doughnut',
    plugins: [window.WorkspaceCharts.allocationLegend],
    data: {
      labels,
      datasets: [{ data, backgroundColor: PALETTE, hoverOffset: 6 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      onClick: id === 'chartSectors' ? (_event, elements) => {
        if (elements.length) window.location.href = 'infoAction.php?sector=' + encodeURIComponent(sectorChartCodes[elements[0].index]) + '#companyDirectory';
      } : undefined,
      onHover: id === 'chartSectors' ? (_event, elements) => {
        ctx.style.cursor = elements.length ? 'pointer' : 'default';
      } : undefined,
      plugins: {
        legend: {
          display: false,
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 }, padding: 14 }
        },
        tooltip: id === 'chartSectors' ? {
          callbacks: {
            label: (ctx) => window.I18n.t('Nombre de sociétés : {count}', {count: ctx.raw}),
            afterLabel: (ctx) => (sectorHoldingDetails[sectorChartCodes[ctx.dataIndex]] || []).map(h =>
              `${h.name} — ${h.has_price ? new Intl.NumberFormat('fr-MA', { maximumFractionDigits: 2 }).format(h.value) + ' MAD' : window.I18n.t('cours indisponible')}`
            )
          }
        } : {},
        datalabels: {
          anchor: 'center', align: 'center',
          color: '#030712',
          font: { size: 11, weight: 'bold' },
          display: (ctx) => {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
            return total > 0 && ctx.dataset.data[ctx.dataIndex] / total >= 0.05;
          },
          formatter: (value, ctx) => {
            const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
            const pct   = total > 0 ? ((value/total)*100).toFixed(1) : 0;
            return pct + '%';
          }
        }
      }
    }
  });
}

<?php if ($referenceTotals['complete']): ?>
makeDoughnut('chartCurrent', <?= json_encode($chartNames) ?>, <?= json_encode($chartValues) ?>);
<?php endif; ?>
makeDoughnut('chartBuy',     <?= json_encode($chartNames) ?>, <?= json_encode($chartBuys) ?>);
const sectorChartCodes = <?= json_encode(array_column($sectorChartRows, 'code')) ?>;
const sectorHoldingDetails = <?= json_encode($sectorAllocation['held_companies'], JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP) ?>;
const sectorDirectory = <?= json_encode($sectorDirectory, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP) ?>;
makeDoughnut('chartSectors', <?= json_encode(array_map('t', array_column($sectorChartRows, 'label')), JSON_UNESCAPED_UNICODE | JSON_HEX_TAG) ?>, <?= json_encode(array_column($sectorChartRows, 'held')) ?>);

const allocationTrack = document.getElementById('allocationTrack');
const allocationValues = document.getElementById('allocationValues');
const allocationSectors = document.getElementById('allocationSectors');
function fitAllocationPanel() {
  const active = allocationTrack.classList.contains('show-sectors') ? allocationSectors : allocationValues;
  if(active.offsetHeight > 0) allocationTrack.parentElement.style.height = active.offsetHeight + 'px';
}
const allocationSizeObserver = new ResizeObserver(fitAllocationPanel);
allocationSizeObserver.observe(allocationValues);
allocationSizeObserver.observe(allocationSectors);
function showAllocationSectors(show) {
  allocationTrack.classList.toggle('show-sectors', show);
  allocationValues.setAttribute('aria-hidden', String(show));
  allocationSectors.setAttribute('aria-hidden', String(!show));
  allocationValues.inert = show;
  allocationSectors.inert = !show;
  fitAllocationPanel();
}
document.getElementById('showSectors').addEventListener('click', () => showAllocationSectors(true));
document.getElementById('showValues').addEventListener('click', () => showAllocationSectors(false));

const sectorHover = document.createElement('div');
sectorHover.className = 'sector-hover';
sectorHover.setAttribute('role', 'tooltip');
sectorHover.hidden = true;
document.body.appendChild(sectorHover);

function placeSectorHover(x, y) {
  const width = sectorHover.offsetWidth;
  const height = sectorHover.offsetHeight;
  sectorHover.style.left = `${Math.max(12, Math.min(x + 14, window.innerWidth - width - 12))}px`;
  sectorHover.style.top = `${Math.max(12, Math.min(y + 14, window.innerHeight - height - 12))}px`;
}
function showSectorHover(item, x, y) {
  const code = item.dataset.sector;
  const all = sectorDirectory[code] || [];
  const held = (sectorHoldingDetails[code] || []).map(h => h.name);
  sectorHover.replaceChildren();
  for (const [heading, names] of [
    [window.I18n.t('Sociétés du secteur ({count})', {count: all.length}), all],
    [window.I18n.t('En portefeuille ({count})', {count: held.length}), held]
  ]) {
    const title = document.createElement('strong');
    title.textContent = heading;
    sectorHover.appendChild(title);
    const list = document.createElement('div');
    list.textContent = names.length ? names.join(' · ') : window.I18n.t('Aucune');
    sectorHover.appendChild(list);
  }
  sectorHover.hidden = false;
  placeSectorHover(x, y);
}
document.querySelectorAll('.sector-item[data-sector]').forEach(item => {
  item.addEventListener('pointerenter', event => showSectorHover(item, event.clientX, event.clientY));
  item.addEventListener('pointermove', event => placeSectorHover(event.clientX, event.clientY));
  item.addEventListener('pointerleave', () => { sectorHover.hidden = true; });
  item.addEventListener('focus', () => {
    const rect = item.getBoundingClientRect();
    showSectorHover(item, rect.right, rect.top);
  });
  item.addEventListener('blur', () => { sectorHover.hidden = true; });
});
<?php endif; ?>

<?php if (!empty($earnings)):
  $earningsAsc = array_reverse($earnings);
?>
const pnlDates  = <?= json_encode(array_column($earningsAsc, 'DATE')) ?>;
const pnlValues = <?= json_encode(array_map('floatval', array_column($earningsAsc, 'VALUE'))) ?>;

const pnlHoverVal = document.getElementById('pnlHoverVal');
const pnlCrosshair = {
  id: 'pnlCrosshair',
  afterDraw(chart) {
    const active = chart.tooltip && chart.tooltip._active;
    if (!active || !active.length) return;
    const x = active[0].element.x;
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = 'rgba(148,163,184,0.5)';
    ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
    ctx.restore();
  },
  afterEvent(chart, args) {
    if (args.event.type === 'mouseout') { pnlHoverVal.textContent = ''; chart.draw(); }
  }
};

new Chart(document.getElementById('chartPnl'), {
  type: 'line',
  plugins: [pnlCrosshair],
  data: {
    labels: pnlDates,
    datasets: [{
      data: pnlValues,
      borderColor: pnlValues[pnlValues.length - 1] >= 0 ? '#10b981' : '#f43f5e',
      backgroundColor: pnlValues[pnlValues.length - 1] >= 0
        ? 'rgba(16,185,129,0.08)' : 'rgba(244,63,94,0.08)',
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      pointBackgroundColor: pnlValues.map(v => v >= 0 ? '#10b981' : '#f43f5e'),
      fill: true,
      tension: 0.3,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      datalabels: { display: false },
      tooltip: {
        backgroundColor: 'rgba(15,23,42,0.92)',
        titleColor: '#94a3b8', bodyColor: '#f1f5f9',
        borderColor: 'rgba(148,163,184,0.15)', borderWidth: 1, padding: 10,
        callbacks: {
          label: ctx => {
            const v = ctx.parsed.y;
            pnlHoverVal.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + ' MAD  •  ' + ctx.label;
            return ' P&L : ' + (v >= 0 ? '+' : '') + v.toFixed(2) + ' MAD';
          }
        }
      }
    },
    scales: {
      x: {
        ticks: { color: '#94a3b8', font: { family: 'Inter', size: 11 } },
        grid:  { color: 'rgba(148,163,184,0.1)' }
      },
      y: {
        ticks: {
          color: '#94a3b8', font: { family: 'JetBrains Mono', size: 11 },
          callback: v => (v >= 0 ? '+' : '') + v.toFixed(0)
        },
        grid: { color: 'rgba(148,163,184,0.1)' }
      }
    }
  }
});
<?php endif; ?>

</script>
</body>
</html>
