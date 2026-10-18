<?php
ob_start();
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/auth.php';
require_once 'core/dividends.php';
require_once 'core/sector_allocation.php';
requireLogin();

$uid     = aw_user_id();
$session = aw_session();
$flash   = [];

// ─── Add buy ──────────────────────────────────────────────
if (isset($_POST['add_buy'])) {
    csrf_verify();
    $name   = trim($_POST['NAME']      ?? '');
    $number = (float) ($_POST['NUMBER']    ?? 0);
    $price  = (float) ($_POST['PRIX_ACHAT']?? 0);
    if ($name && $number > 0 && $price > 0) {
        try {
            $perms = aw_user_permissions($uid);
            aw_create_doc('achats', [
                'date'       => date('Y-m-d'),
                'c_name'     => $name,
                'number'     => $number,
                'prix_achat' => $price,
                'user_id'    => $uid,
            ], $perms, $session);

            // Upsert portefeuille
            $pf = aw_list_docs('portefeuille', [
                q_equal('c_name', $name),
                q_equal('user_id', $uid),
                q_limit(1),
            ], $session);

            if (!empty($pf)) {
                $doc = $pf[0];
                aw_update_doc('portefeuille', $doc['$id'], [
                    'quantity'   => $doc['quantity'] + $number,
                    'total_cost' => $doc['total_cost'] + $price * $number,
                ], $session);
            } else {
                aw_create_doc('portefeuille', [
                    'c_name'     => $name,
                    'quantity'   => $number,
                    'total_cost' => $price * $number,
                    'user_id'    => $uid,
                ], $perms, $session);
            }
            $flash[] = ['type' => 'success', 'msg' => "Achat de {$number} × {$name} enregistré."];
        } catch (Throwable $e) {
            error_log('[myInterpreter] add_buy error: ' . $e->getMessage());
            $flash[] = ['type' => 'error', 'msg' => 'Erreur lors de l\'enregistrement : ' . $e->getMessage()];
        }
    }
}

// ─── Add sell ─────────────────────────────────────────────
if (isset($_POST['add_sell'])) {
    csrf_verify();
    $name   = trim($_POST['NAME2']      ?? '');
    $number = (float) ($_POST['NUMBER2']   ?? 0);
    $price  = (float) ($_POST['PRIX_VENTE']?? 0);
    if ($name && $number > 0 && $price > 0) {
        try {
            $pf = aw_list_docs('portefeuille', [
                q_equal('c_name', $name),
                q_equal('user_id', $uid),
                q_limit(1),
            ], $session);

            if (!empty($pf) && $number <= $pf[0]['quantity']) {
                $doc   = $pf[0];
                $perms = aw_user_permissions($uid);
                aw_create_doc('ventes', [
                    'date'       => date('Y-m-d'),
                    'c_name'     => $name,
                    'number'     => $number,
                    'prix_vente' => $price,
                    'user_id'    => $uid,
                ], $perms, $session);

                if ($number == $doc['quantity']) {
                    aw_delete_doc('portefeuille', $doc['$id'], $session);
                } else {
                    $avg = $doc['total_cost'] / $doc['quantity'];
                    aw_update_doc('portefeuille', $doc['$id'], [
                        'quantity'   => $doc['quantity'] - $number,
                        'total_cost' => $doc['total_cost'] - $avg * $number,
                    ], $session);
                }
                $flash[] = ['type' => 'success', 'msg' => "Vente de {$number} × {$name} enregistrée."];
                header('Location: portfolio.php'); exit();
            } else {
                $flash[] = ['type' => 'error', 'msg' => 'Quantité insuffisante en portefeuille.'];
            }
        } catch (Throwable $e) {
            error_log('[myInterpreter] add_sell error: ' . $e->getMessage());
            $flash[] = ['type' => 'error', 'msg' => 'Erreur lors de la vente : ' . $e->getMessage()];
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
        'holdings' => ['portefeuille', [q_equal('user_id', $uid), q_limit(200)], $session],
        'earnings' => ['benefits', [q_equal('user_id', $uid), q_order_desc('date'), q_limit(500)], $session],
    ]);
    $holdingsDocs = $portfolioData['holdings'];

    $earningsDocs = $portfolioData['earnings'];
} catch (Throwable $e) {
    error_log('[myInterpreter] portfolio.php data load error: ' . $e->getMessage());
    $loadError = 'Impossible de charger les données. Veuillez réessayer.';
}

// Build price map from latest_prices — one row per company, always current
$priceMap = [];
$lpDocs = aw_list_docs('latest_prices', [q_limit(200)]);
foreach ($lpDocs as $d) {
    $n = $d['c_name'] ?? '';
    if ($n) $priceMap[$n] = (float)($d['pa'] ?? 0);
}

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
    $sectorHoldings[] = ['c_name' => $name, 'quantity' => $qty, 'current_value' => $curVal, 'has_price' => $pa > 0];
    $chartNames[]  = $name;
    $chartValues[] = round($curVal, 2);
    $chartBuys[]   = round($cost, 2);
    $totalCurrentVal += $curVal;
    $totalBuyVal     += $cost;

    if ($pa <= 0) {
        $flash[] = ['type' => 'warn', 'msg' => "Prix introuvable pour « {$name} »."];
    }
}

$diffDisplay = $totalCurrentVal - $totalBuyVal;
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
$divTotalYear = 0.0; $divTotalUpcoming = 0.0; $divPaying = 0;
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
    if ($paid) $divPaying++;
}
usort($divLines, fn($a, $b) => strcmp($a['sort'], $b['sort']));
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
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>myInterpreter | Portefeuille</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/portfolio.css?v=5" rel="stylesheet">
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
      <h1>Portefeuille</h1>
      <p>Vos positions, leur répartition et vos opérations au même endroit.</p>
    </header>

    <!-- Flash messages -->
    <?php foreach ($flash as $f): ?>
      <div class="alert alert-<?= $f['type'] ?>"><i class="fas fa-<?= $f['type']==='success'?'check-circle':'exclamation-triangle' ?> me-2"></i><?= htmlspecialchars($f['msg']) ?></div>
    <?php endforeach; ?>
    <?php if ($loadError): ?>
      <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i><?= htmlspecialchars($loadError) ?></div>
    <?php endif; ?>

    <!-- Tab navigation -->
    <div class="tab-nav" role="tablist">
      <button class="tab-btn <?= $activeTab==='portfolio'?'active':'' ?>" onclick="switchTab('portfolio')" type="button">
        <i class="fas fa-wallet"></i> Portefeuille
      </button>
      <button class="tab-btn <?= $activeTab==='transactions'?'active':'' ?>" onclick="switchTab('transactions')" type="button">
        <i class="fas fa-exchange-alt"></i> Transactions
      </button>
      <button class="tab-btn <?= $activeTab==='history'?'active':'' ?>" onclick="switchTab('history')" type="button">
        <i class="fas fa-chart-bar"></i> Historique P&L
      </button>
    </div>

    <!-- ── Tab 1: Portfolio ───────────────────────────────────── -->
    <div id="tab-portfolio" class="tab-panel <?= $activeTab==='portfolio'?'active':'' ?>">

      <!-- Summary chips -->
      <div class="pf-summary stagger-children">
        <div class="stat-chip">
          <span class="stat-chip__value mono t-cyan"><?= number_format($totalCurrentVal,2) ?></span>
          <span class="stat-chip__label">Valeur actuelle (MAD)</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip__value mono t-violet"><?= number_format($totalBuyVal,2) ?></span>
          <span class="stat-chip__label">Valeur d'achat (MAD)</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip__value mono <?= $diffDisplay >= 0 ? 't-emerald' : 't-rose' ?>">
            <?= ($diffDisplay >= 0 ? '+' : '') . number_format($diffDisplay, 2) ?>
          </span>
          <span class="stat-chip__label">Plus/Moins value latente</span>
        </div>
      </div>


      <!-- Holdings table -->
      <?php if (!empty($holdings)): ?>
      <style>
        /* Extra column groups are collapsed by default so the table stays narrow;
           the toggles below reveal them on demand (progressive disclosure). */
        #holdingsTbl .col-frais, #holdingsTbl .col-seuil { display: none; }
        #holdingsTbl.show-frais .col-frais { display: table-cell; }
        #holdingsTbl.show-seuil .col-seuil { display: table-cell; }
        .col-toggles { display:flex; gap:8px; justify-content:flex-end; align-items:center; margin-bottom:10px; flex-wrap:wrap; }
        .col-toggles .lbl { font-size:0.82rem; color:var(--text-mute); margin-right:2px; }
        .col-toggle { opacity:0.5; }
        .col-toggle.active { opacity:1; }
        /* Pin the Société column so it stays visible during horizontal scroll. */
        #holdingsTbl thead th:first-child,
        #holdingsTbl tbody td:first-child {
          position: sticky; left: 0; z-index: 2;
          background: var(--surface-1);
        }
        #holdingsTbl thead th:first-child { z-index: 3; }
      </style>
      <div class="col-toggles">
        <span class="lbl"><i class="fas fa-table-columns me-1"></i>Colonnes :</span>
        <button type="button" class="btn btn-ghost btn-sm col-toggle" onclick="toggleCols('frais', this)">
          <i class="fas fa-coins"></i> Frais
        </button>
        <button type="button" class="btn btn-ghost btn-sm col-toggle" onclick="toggleCols('seuil', this)">
          <i class="fas fa-scale-balanced"></i> Équilibre
        </button>
      </div>
      <div class="card-glass overflow-x-auto mb-4">
        <table class="tbl" id="holdingsTbl">
          <thead><tr>
            <th>Société</th>
            <th class="num">Actions</th>
            <th class="num">Val. Achat</th>
            <th class="num">Val. Actuelle</th>
            <th class="num">P/MV Latente</th>
            <th class="num col-frais">Frais achat</th>
            <th class="num col-frais">Frais vente (est.)</th>
            <th class="num col-frais">Total frais</th>
            <th class="num col-seuil">Seuil équilibre</th>
          </tr></thead>
          <tbody>
            <?php foreach ($holdings as $i => $h):
              $cur = $chartValues[$i];
              $buy = $chartBuys[$i];
              $pnl = $cur - $buy;
              $cls = $pnl > 0 ? 'pos' : ($pnl < 0 ? 'neg' : 'zero');
              $pct = ($cur > 0 && $buy > 0) ? ($pnl / $buy) * 100 : null;
              $fraisAchat = commission($buy);                    // 1 % already paid to build this position
              $fraisVente = $cur > 0 ? commission($cur) : null;  // 1 % you'd pay to sell now (live estimate)
              $totalFrais = $fraisAchat + ($fraisVente ?? 0);
              // Break-even: market value where selling nets exactly the cash paid in,
              // covering both the 1 % buy commission (already paid) and the 1 % sell commission.
              //   V·(1−r) = B·(1+r)  →  V_be = B·(1+r)/(1−r)
              // Break-even value (incl. 1% commission both legs + 10% gain tax).
              $breakeven  = breakeven_value($buy);
              // Écart vs current value: how much MORE it must gain to break even (>0 ⇒ to go, ≤0 ⇒ past).
              $ecartSeuil = ($buy > 0 && $cur > 0) ? ($breakeven - $cur) : null;
            ?>
            <tr>
              <td class="label-cell"><a href="infoAction.php?name=<?= urlencode($h['c_name']) ?>" class="t-cyan"><?= htmlspecialchars($h['c_name']) ?></a></td>
              <td class="num mono"><?= (int)$h['quantity'] ?></td>
              <td class="num mono"><?= number_format($buy, 2) ?></td>
              <td class="num mono"><?= $cur > 0 ? number_format($cur, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono <?= $cls ?>"><?php if ($cur > 0): ?><?= ($pnl>=0?'+':'') . number_format($pnl,2) ?><?php if ($pct !== null): ?> <span class="muted">(<?= ($pct>=0?'+':'') . number_format($pct,2) ?>%)</span><?php endif; ?><?php else: ?><span class="muted">—</span><?php endif; ?></td>
              <td class="num mono muted col-frais"><?= number_format($fraisAchat, 2) ?></td>
              <td class="num mono muted col-frais"><?= $fraisVente !== null ? number_format($fraisVente, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono col-frais"><?= number_format($totalFrais, 2) ?></td>
              <td class="num mono col-seuil"><?php if ($breakeven > 0): ?><?= number_format($breakeven, 2) ?><?php if ($ecartSeuil !== null): ?> <span class="muted">(<?= ($ecartSeuil > 0 ? '+' : '') . number_format($ecartSeuil, 2) ?>)</span><?php endif; ?><?php else: ?><span class="muted">—</span><?php endif; ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <?php else: ?>
        <div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>Aucune position ouverte.</div>
      <?php endif; ?>

      <!-- Charts -->
      <?php if (!empty($chartNames)): ?>
      <div class="charts-viewport mb-4">
        <div class="charts-track" id="allocationTrack">
          <div class="charts-grid charts-page" id="allocationValues">
            <div class="chart-card">
              <h5><i class="fas fa-circle-dot me-2 t-cyan"></i>Répartition valeur actuelle</h5>
              <div class="chart-canvas"><canvas id="chartCurrent"></canvas></div>
            </div>
            <div class="chart-card">
              <div class="chart-heading">
                <h5><i class="fas fa-circle-dot me-2 t-violet"></i>Répartition valeur d'achat</h5>
                <button class="chart-switch chart-switch--next" type="button" id="showSectors" aria-label="Afficher la répartition par secteurs" title="Voir les secteurs"><i class="fas fa-arrow-right" aria-hidden="true"></i></button>
              </div>
              <div class="chart-canvas"><canvas id="chartBuy"></canvas></div>
            </div>
          </div>
          <div class="charts-grid charts-page" id="allocationSectors" aria-hidden="true" inert>
            <div class="chart-card">
              <div class="chart-heading">
                <button class="chart-switch chart-switch--previous" type="button" id="showValues" aria-label="Afficher la répartition par société" title="Voir les sociétés"><i class="fas fa-arrow-left" aria-hidden="true"></i></button>
                <h5><i class="fas fa-circle-dot me-2 t-cyan"></i>Répartition par secteur</h5>
              </div>
              <p class="chart-caption">Part des sociétés détenues · une société compte une fois</p>
              <div class="chart-canvas"><canvas id="chartSectors"></canvas></div>
              <?php if (!$sectorChartRows): ?><p class="sector-note">Aucune société détenue à répartir.</p><?php endif; ?>
              <?php if ($sectorAllocation['unclassified']): ?>
                <p class="sector-note">Hors classement officiel : <?= htmlspecialchars(implode(', ', $sectorAllocation['unclassified'])) ?></p>
              <?php endif; ?>

            </div>
            <div class="chart-card">
              <h5><i class="fas fa-bars me-2 t-violet"></i>Couverture des secteurs</h5>
              <p class="chart-caption">Sociétés détenues / sociétés cotées · Bourse de Casablanca, <?= MARKET_SECTOR_DATE ?></p>
              <div class="sector-list" role="list">
                <?php foreach ($sectorRows as $row):
                  $fill = $row['market'] > 0 ? min(100, $row['held'] / $row['market'] * 100) : 0;
                ?>
                  <a class="sector-item" role="listitem" data-sector="<?= htmlspecialchars($row['code']) ?>" href="infoAction.php?sector=<?= urlencode($row['code']) ?>#companyDirectory" aria-label="Voir les sociétés du secteur <?= htmlspecialchars($row['label']) ?>">
                    <div class="sector-item__heading"><span><?= htmlspecialchars($row['label']) ?></span><strong><?= $row['held'] ?>/<?= $row['market'] ?></strong></div>
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
          <h5><i class="fas fa-coins me-2 t-emerald"></i>Revenus de dividendes <?= $divYear ?></h5>
          <div class="div-panel-totals">
            <div class="div-total">
              <span class="div-total-val"><?= number_format($divTotalYear, 2, ',', ' ') ?></span>
              <span class="div-total-lbl">MAD sur l'année</span>
            </div>
            <?php if ($divTotalUpcoming > 0): ?>
            <div class="div-total">
              <span class="div-total-val t-cyan"><?= number_format($divTotalUpcoming, 2, ',', ' ') ?></span>
              <span class="div-total-lbl">MAD à venir</span>
            </div>
            <?php endif; ?>
            <?php if ($divYieldOnCost !== null): ?>
            <div class="div-total">
              <span class="div-total-val t-emerald"><?= number_format($divYieldOnCost, 2, ',', ' ') ?>&nbsp;%</span>
              <span class="div-total-lbl">rendement / prix d'achat</span>
            </div>
            <?php endif; ?>
          </div>
        </div>

        <div class="card-glass overflow-x-auto">
          <table class="tbl">
            <thead><tr>
              <th>Société</th>
              <th class="num">Actions</th>
              <th class="num">MAD/action</th>
              <th class="num">Rendement</th>
              <th>Détachement</th>
              <th>Paiement</th>
              <th class="num">Montant brut</th>
            </tr></thead>
            <tbody>
            <?php foreach ($divLines as $l): $r = $l['row']; ?>
              <tr class="<?= $l['upcoming'] ? 'div-upcoming' : 'div-done' ?>">
                <td>
                  <a href="infoAction.php?name=<?= urlencode($l['name']) ?>" class="t-cyan">
                    <?= htmlspecialchars($l['name']) ?></a>
                  <?php if (!div_confirmed($r)): ?>
                    <span class="div-badge estimated">prévu</span>
                  <?php endif; ?>
                  <?php if (strcasecmp((string)($r['frequency'] ?? ''), 'Trimestriel') === 0): ?>
                    <span class="div-badge quarterly">trim.</span>
                  <?php endif; ?>
                </td>
                <td class="num mono"><?= number_format($l['qty'], 0, ',', ' ') ?></td>
                <td class="num mono"><?= number_format($l['amount'], 2, ',', ' ') ?></td>
                <td class="num mono"><?= $l['yield'] === null ? '—' : number_format($l['yield'], 2, ',', ' ') . '&nbsp;%' ?></td>
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
          <?= $divPaying ?> de vos <?= count($divQty) ?> positions versent un dividende cette année.
          <span class="muted">Montants bruts, avant retenue à la source · les lignes « prévu »
          n'ont pas encore été votées en assemblée générale</span>
        </p>
      </div>
      <?php endif; ?>

    </div><!-- tab-portfolio -->

    <!-- ── Tab 2: Transactions ───────────────────────────────── -->
    <div id="tab-transactions" class="tab-panel <?= $activeTab==='transactions'?'active':'' ?>">

      <div class="forms-grid">

        <!-- Buy form -->
        <div class="form-card">
          <h4 class="t-cyan"><i class="fas fa-plus-circle"></i> Ajouter un achat</h4>
          <form method="POST" action="" data-loading>
            <?= csrf_field() ?>
            <datalist id="companyListBuy">
              <?php foreach ($allCompanies as $n): ?><option value="<?= htmlspecialchars($n) ?>"><?php endforeach; ?>
            </datalist>
            <div class="mb-3">
              <label class="form-label small muted">Société</label>
              <input type="text" name="NAME" list="companyListBuy" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label small muted">Nombre d'actions</label>
              <input type="number" name="NUMBER" class="form-control" step="1" min="1" required>
            </div>
            <div class="mb-4">
              <label class="form-label small muted">Prix d'achat (MAD)</label>
              <input type="number" name="PRIX_ACHAT" class="form-control" step="0.01" min="0.01" required>
            </div>
            <button type="submit" name="add_buy" class="btn btn-cyan w-100" data-loading-text="Enregistrement...">
              <i class="fas fa-plus"></i> Ajouter l'achat
            </button>
          </form>
        </div>

        <!-- Sell form -->
        <div class="form-card">
          <h4 class="t-rose"><i class="fas fa-minus-circle"></i> Enregistrer une vente</h4>
          <form method="POST" action="" data-loading>
            <?= csrf_field() ?>
            <datalist id="companyListSell">
              <?php foreach ($allCompanies as $n): ?><option value="<?= htmlspecialchars($n) ?>"><?php endforeach; ?>
            </datalist>
            <div class="mb-3">
              <label class="form-label small muted">Société</label>
              <input type="text" name="NAME2" list="companyListSell" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label small muted">Nombre d'actions à vendre</label>
              <input type="number" name="NUMBER2" class="form-control" step="1" min="1" required>
            </div>
            <div class="mb-4">
              <label class="form-label small muted">Prix de vente (MAD)</label>
              <input type="number" name="PRIX_VENTE" class="form-control" step="0.01" min="0.01" required>
            </div>
            <button type="submit" name="add_sell" class="btn btn-rose w-100" data-loading-text="Enregistrement...">
              <i class="fas fa-minus"></i> Enregistrer la vente
            </button>
          </form>
        </div>

      </div><!-- .forms-grid -->

    </div><!-- tab-transactions -->

    <!-- ── Tab 3: FIFO History ───────────────────────────────── -->
    <div id="tab-history" class="tab-panel <?= $activeTab==='history'?'active':'' ?>">

      <?php if (!empty($earnings)): ?>
      <div class="chart-card mb-4">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
          <h5 style="margin:0"><i class="fas fa-chart-line me-2 t-emerald"></i>Évolution P&L</h5>
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
<script src="assets/js/app.js"></script>
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
  document.getElementById('holdingsTbl').classList.toggle('show-' + group);
  btn.classList.toggle('active');
}

/* ── Doughnut charts ───────────────────────────────────── */
<?php if (!empty($chartNames)): ?>
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
            label: (ctx) => `${ctx.raw} société${ctx.raw > 1 ? 's' : ''}`,
            afterLabel: (ctx) => (sectorHoldingDetails[sectorChartCodes[ctx.dataIndex]] || []).map(h =>
              `${h.name} — ${h.has_price ? new Intl.NumberFormat('fr-MA', { maximumFractionDigits: 2 }).format(h.value) + ' MAD' : 'cours indisponible'}`
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

makeDoughnut('chartCurrent', <?= json_encode($chartNames) ?>, <?= json_encode($chartValues) ?>);
makeDoughnut('chartBuy',     <?= json_encode($chartNames) ?>, <?= json_encode($chartBuys) ?>);
const sectorChartCodes = <?= json_encode(array_column($sectorChartRows, 'code')) ?>;
const sectorHoldingDetails = <?= json_encode($sectorAllocation['held_companies'], JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP) ?>;
const sectorDirectory = <?= json_encode($sectorDirectory, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP) ?>;
makeDoughnut('chartSectors', <?= json_encode(array_column($sectorChartRows, 'label'), JSON_UNESCAPED_UNICODE) ?>, <?= json_encode(array_column($sectorChartRows, 'held')) ?>);

const allocationTrack = document.getElementById('allocationTrack');
const allocationValues = document.getElementById('allocationValues');
const allocationSectors = document.getElementById('allocationSectors');
function showAllocationSectors(show) {
  allocationTrack.classList.toggle('show-sectors', show);
  allocationValues.setAttribute('aria-hidden', String(show));
  allocationSectors.setAttribute('aria-hidden', String(!show));
  allocationValues.inert = show;
  allocationSectors.inert = !show;
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
    [`Sociétés du secteur (${all.length})`, all],
    [`En portefeuille (${held.length})`, held]
  ]) {
    const title = document.createElement('strong');
    title.textContent = heading;
    sectorHover.appendChild(title);
    const list = document.createElement('div');
    list.textContent = names.length ? names.join(' · ') : 'Aucune';
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
