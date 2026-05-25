<?php
ob_start();
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/auth.php';
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
        $perms = aw_user_permissions($uid);
        aw_create_doc('achats', [
            'date'      => date('Y-m-d'),
            'c_name'    => $name,
            'quantity'  => $number,
            'price'     => $price,
            'user_id'   => $uid,
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
    }
}

// ─── Add sell ─────────────────────────────────────────────
if (isset($_POST['add_sell'])) {
    csrf_verify();
    $name   = trim($_POST['NAME2']      ?? '');
    $number = (float) ($_POST['NUMBER2']   ?? 0);
    $price  = (float) ($_POST['PRIX_VENTE']?? 0);
    if ($name && $number > 0 && $price > 0) {
        $pf = aw_list_docs('portefeuille', [
            q_equal('c_name', $name),
            q_equal('user_id', $uid),
            q_limit(1),
        ], $session);

        if (!empty($pf) && $number <= $pf[0]['quantity']) {
            $doc   = $pf[0];
            $perms = aw_user_permissions($uid);
            aw_create_doc('ventes', [
                'date'     => date('Y-m-d'),
                'c_name'   => $name,
                'quantity' => $number,
                'price'    => $price,
                'user_id'  => $uid,
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
    }
}

// ─── Save portfolio snapshot to benefits ─────────────────
if (isset($_POST['save_snapshot'])) {
    csrf_verify();
    $today    = date('Y-m-d');
    $existing = aw_list_docs('benefits', [
        q_equal('user_id', $uid),
        q_equal('date', $today),
        q_limit(1),
    ], $session);
    if (empty($existing)) {
        $snapValue = (float) ($_POST['snapshot_value'] ?? 0);
        aw_create_doc('benefits', [
            'date'    => $today,
            'value'   => $snapValue,
            'user_id' => $uid,
        ], aw_user_permissions($uid), $session);
        $flash[] = ['type' => 'success', 'msg' => "Snapshot P&L enregistré pour aujourd'hui."];
    } else {
        $flash[] = ['type' => 'warn', 'msg' => 'Un snapshot a déjà été enregistré aujourd\'hui.'];
    }
}

// ─── Load portfolio data ──────────────────────────────────────────────────────
$holdingsDocs = [];
$latestData   = [];
$lastSnapDate = null;
$lastSync     = null;
$earningsDocs = [];
$loadError    = null;

try {
    $holdingsDocs = aw_list_docs('portefeuille', [
        q_equal('user_id', $uid),
        q_limit(200),
    ], $session);

    $latestData = aw_list_docs('data', [q_order_desc('date'), q_limit(100)]);

    // Derive last sync from already-fetched data — no extra request needed
    $lastSync = $latestData[0]['date'] ?? null;

    $lastSnapDocs = aw_list_docs('benefits', [
        q_equal('user_id', $uid),
        q_order_desc('date'),
        q_limit(1),
    ], $session);
    $lastSnapDate = $lastSnapDocs[0]['date'] ?? null;

    $earningsDocs = aw_list_docs('benefits', [
        q_equal('user_id', $uid),
        q_order_desc('date'),
        q_limit(500),
    ], $session);
} catch (Throwable $e) {
    error_log('[myInterpreter] portfolio.php data load error: ' . $e->getMessage());
    $loadError = 'Impossible de charger les données. Veuillez réessayer.';
}

// Build price map
$heldNames = array_map(fn($h) => $h['c_name'], $holdingsDocs);
$priceMap  = [];
foreach ($latestData as $d) {
    $n = $d['c_name'] ?? '';
    if (!isset($priceMap[$n]) && in_array($n, $heldNames)) {
        $priceMap[$n] = (float)($d['pa'] ?? 0);
    }
}

$holdings = [];
$chartNames = []; $chartValues = []; $chartBuys = [];
$totalCurrentVal = 0.0; $totalBuyVal = 0.0;

foreach ($holdingsDocs as $h) {
    $name   = $h['c_name'];
    $qty    = (float)($h['quantity'] ?? 0);
    $cost   = (float)($h['total_cost'] ?? 0);
    $pa     = $priceMap[$name] ?? 0;
    $curVal = $pa > 0 ? $qty * $pa : 0;

    $holdings[]    = $h;
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
$earnings    = array_map(fn($d) => ['DATE' => fmt_date($d['date']), 'VALUE' => $d['value']], $earningsDocs);

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

// Default active tab
$activeTab = $_GET['tab'] ?? 'portfolio';
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>myInterpreter | Portefeuille</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/portfolio.css" rel="stylesheet">
  <link href="assets/css/statistics.css" rel="stylesheet">
</head>
<body>
<div class="page">

  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Portefeuille</span>
    <div class="topbar-spacer"></div>
    <a href="index.php" class="btn btn-ghost btn-sm"><i class="fas fa-home"></i></a>
  </nav>

  <div class="portfolio-wrap animate-up">

    <!-- Flash messages -->
    <?php foreach ($flash as $f): ?>
      <div class="alert alert-<?= $f['type'] ?>"><i class="fas fa-<?= $f['type']==='success'?'check-circle':'exclamation-triangle' ?> me-2"></i><?= htmlspecialchars($f['msg']) ?></div>
    <?php endforeach; ?>
    <?php if ($loadError): ?>
      <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i><?= htmlspecialchars($loadError) ?></div>
    <?php endif; ?>

    <!-- Info row -->
    <div class="sync-row">
      <span class="sync-label"><i class="fas fa-save me-1"></i>Dernier snapshot :</span>
      <span class="sync-value"><?= fmt_date($lastSnapDate) ?></span>
      <div class="divider"></div>
      <span class="sync-label"><i class="fas fa-sync me-1"></i>Dernier sync :</span>
      <span class="sync-value"><?= fmt_date($lastSync) ?></span>
    </div>

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

      <!-- Charts -->
      <?php if (!empty($chartNames)): ?>
      <div class="charts-grid mb-4">
        <div class="chart-card">
          <h5><i class="fas fa-circle-dot me-2 t-cyan"></i>Répartition valeur actuelle</h5>
          <canvas id="chartCurrent"></canvas>
        </div>
        <div class="chart-card">
          <h5><i class="fas fa-circle-dot me-2 t-violet"></i>Répartition valeur d'achat</h5>
          <canvas id="chartBuy"></canvas>
        </div>
      </div>
      <?php endif; ?>

      <!-- Holdings table -->
      <?php if (!empty($holdings)): ?>
      <div class="card-glass overflow-x-auto mb-4">
        <table class="tbl">
          <thead><tr>
            <th>Société</th>
            <th class="num">Actions</th>
            <th class="num">Val. Achat</th>
            <th class="num">Val. Actuelle</th>
            <th class="num">P/MV Latente</th>
            <th class="num">%</th>
          </tr></thead>
          <tbody>
            <?php foreach ($holdings as $i => $h):
              $cur = $chartValues[$i];
              $buy = $chartBuys[$i];
              $pnl = $cur - $buy;
              $cls = $pnl > 0 ? 'pos' : ($pnl < 0 ? 'neg' : 'zero');
              $pct = ($cur > 0 && $buy > 0) ? ($pnl / $buy) * 100 : null;
            ?>
            <tr>
              <td class="label-cell"><?= htmlspecialchars($h['c_name']) ?></td>
              <td class="num mono"><?= (int)$h['quantity'] ?></td>
              <td class="num mono"><?= number_format($buy, 2) ?></td>
              <td class="num mono"><?= $cur > 0 ? number_format($cur, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono <?= $cls ?>"><?= $cur > 0 ? ($pnl>=0?'+':'') . number_format($pnl,2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono <?= $pct !== null ? $cls : '' ?>"><?= $pct !== null ? ($pct>=0?'+':'') . number_format($pct,2) . '%' : '<span class="muted">—</span>' ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <?php else: ?>
        <div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>Aucune position ouverte.</div>
      <?php endif; ?>

      <!-- Save snapshot -->
      <div style="display:flex;gap:12px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
        <span class="muted" style="font-size:0.82rem">Sauvegarder la plus/moins-value d'aujourd'hui :</span>
        <form method="POST" style="display:inline">
          <?= csrf_field() ?>
          <input type="hidden" name="snapshot_value" value="<?= $diffDisplay ?>">
          <button type="submit" name="save_snapshot" class="btn btn-ghost btn-sm">
            <i class="fas fa-bookmark"></i> Snapshot
          </button>
        </form>
      </div>

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

      <!-- Earnings history -->
      <?php if (!empty($earnings)): ?>
      <div class="mt-4">
        <div class="section-label"><i class="fas fa-history me-1"></i>Historique des snapshots</div>
        <div class="card-glass overflow-x-auto">
          <table class="tbl">
            <thead><tr><th>Date</th><th class="num">Plus/Moins-value</th></tr></thead>
            <tbody>
              <?php foreach ($earnings as $e):
                $cls = $e['VALUE'] > 0 ? 'pos' : ($e['VALUE'] < 0 ? 'neg' : 'zero');
              ?>
              <tr>
                <td class="date"><?= htmlspecialchars($e['DATE']) ?></td>
                <td class="num mono <?= $cls ?>"><?= ($e['VALUE']>=0?'+':'') . number_format((float)$e['VALUE'],2) ?></td>
              </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
        </div>
      </div>
      <?php endif; ?>

    </div><!-- tab-transactions -->

    <!-- ── Tab 3: FIFO History ───────────────────────────────── -->
    <div id="tab-history" class="tab-panel <?= $activeTab==='history'?'active':'' ?>">

      <?php if (!empty($earnings)): ?>
      <div class="chart-card mb-4">
        <h5><i class="fas fa-chart-line me-2 t-emerald"></i>Évolution P&L (snapshots)</h5>
        <canvas id="chartPnl"></canvas>
      </div>
      <?php endif; ?>

      <div class="card-glass overflow-x-auto">
        <?php require_once 'statistics.php'; stats(); ?>
      </div>
    </div>

  </div><!-- .portfolio-wrap -->
</div><!-- .page -->

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

/* ── Doughnut charts ───────────────────────────────────── */
<?php if (!empty($chartNames)): ?>
Chart.register(ChartDataLabels);

const PALETTE = ['#22d3ee','#818cf8','#10b981','#f59e0b','#f43f5e','#a78bfa','#34d399','#fb923c'];

function makeDoughnut(id, labels, data) {
  const ctx = document.getElementById(id);
  if (!ctx || !data.length) return;
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: PALETTE, hoverOffset: 6 }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 }, padding: 14 }
        },
        datalabels: {
          anchor: 'center', align: 'center',
          color: '#030712',
          font: { size: 11, weight: 'bold' },
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
<?php endif; ?>

<?php if (!empty($earnings)):
  $earningsAsc = array_reverse($earnings);
?>
const pnlDates  = <?= json_encode(array_column($earningsAsc, 'DATE')) ?>;
const pnlValues = <?= json_encode(array_map('floatval', array_column($earningsAsc, 'VALUE'))) ?>;

new Chart(document.getElementById('chartPnl'), {
  type: 'line',
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
    plugins: {
      legend: { display: false },
      datalabels: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y.toFixed(2) + ' MAD'
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
