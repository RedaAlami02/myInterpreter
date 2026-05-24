<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';

$allCompanies = [];
$company      = null;
$history      = [];
$sparkLabels  = [];
$sparkData    = [];
$searched     = false;
$dbError      = null;

// ─── Initial company list ─────────────────────────────────
try {
    $companyDocs  = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
    $allCompanies = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));
} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// ─── Handle search ────────────────────────────────────────
if (!$dbError && isset($_GET['name']) && !empty($_GET['name']) && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $_POST['NAME'] = trim($_GET['name']);
    $_SERVER['REQUEST_METHOD'] = 'POST';
}

if (!$dbError && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['NAME'])) {
    $searched = true;
    $name     = trim($_POST['NAME']);

    try {
        $companyRes = aw_list_docs('company', [
            q_equal('name', $name),
            q_limit(1),
        ]);
        $company = !empty($companyRes) ? $companyRes[0] : null;

        if ($company) {
            $history = aw_list_docs('data', [
                q_equal('c_name', $name),
                q_order_desc('date'),
                q_limit(500),
            ]);

            foreach (array_reverse($history) as $row) {
                $sparkLabels[] = $row['date'] ?? '';
                $sparkData[]   = (float)($row['pa'] ?? 0);
            }
        }
    } catch (Throwable $e) {
        $dbError = $e->getMessage();
    }
}
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>myInterpreter | Consulter Action</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/infoAction.css" rel="stylesheet">
</head>
<body>
<div class="page">

  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Consulter Action</span>
    <div class="topbar-spacer"></div>
    <a href="index.php" class="btn btn-ghost btn-sm"><i class="fas fa-home"></i></a>
  </nav>

  <div class="search-wrap">

    <?php if ($dbError): ?>
      <div class="alert alert-danger">
        <strong><i class="fas fa-bug me-2"></i>Erreur PHP/DB :</strong>
        <pre style="margin-top:8px;font-size:0.8rem;white-space:pre-wrap"><?= htmlspecialchars($dbError) ?></pre>
        <p class="mb-0 mt-2" style="font-size:0.82rem">
          Vérifiez que <code>stock.sql</code> a bien été importé et que les identifiants DB dans
          <code>config/config.php</code> sont corrects.
        </p>
      </div>
    <?php else: ?>

    <div class="search-hero">
      <h1><i class="fas fa-search t-emerald me-2"></i>Recherche Société</h1>
      <p>Consultez les ratios fondamentaux et l'historique des prix.</p>
    </div>

    <form method="POST" action="" data-loading>
      <div class="search-bar-wrap">
        <div class="form-floating flex-grow-1">
          <input type="text" name="NAME" id="nameInput" list="companyList"
                 class="form-control" placeholder=" " required autocomplete="off"
                 value="<?= htmlspecialchars($_POST['NAME'] ?? '') ?>">
          <label for="nameInput"><i class="fas fa-building me-2"></i>Nom de l'entreprise</label>
          <datalist id="companyList">
            <?php foreach ($allCompanies as $n): ?>
              <option value="<?= htmlspecialchars($n) ?>">
            <?php endforeach; ?>
          </datalist>
        </div>
        <button type="submit" class="btn btn-emerald" style="height:58px;padding:0 28px"
                data-loading-text="Recherche...">
          <i class="fas fa-search"></i> Afficher
        </button>
      </div>
    </form>

    <?php if ($searched): ?>
      <?php if (!$company): ?>
        <div class="alert alert-danger">
          <i class="fas fa-times-circle me-2"></i>Entreprise introuvable.
        </div>
      <?php else: ?>
        <div class="search-result">

          <h4 class="mb-3" style="font-family:var(--font-display);font-weight:700">
            <i class="fas fa-building t-emerald me-2"></i><?= htmlspecialchars($company['NAME']) ?>
          </h4>

          <div class="card-glass overflow-x-auto mb-4">
            <table class="tbl">
              <thead><tr>
                <?php foreach (array_keys($company) as $col): ?>
                  <th><?= htmlspecialchars($col) ?></th>
                <?php endforeach; ?>
              </tr></thead>
              <tbody><tr>
                <?php foreach ($company as $key => $val): ?>
                  <td class="<?= $key === 'NAME' ? 'label-cell' : 'num mono' ?>">
                    <?= htmlspecialchars((string)($val ?? '—')) ?>
                  </td>
                <?php endforeach; ?>
              </tr></tbody>
            </table>
          </div>

          <?php if (!empty($history)): ?>

            <?php if (count($sparkData) > 1): ?>
            <div class="sparkline-wrap mb-4">
              <h5><i class="fas fa-chart-line me-2 t-cyan"></i>Évolution du prix (PA)</h5>
              <canvas id="sparklineChart" height="80"></canvas>
            </div>
            <?php endif; ?>

            <h5 class="mb-3" style="font-family:var(--font-display);font-weight:700">
              <i class="fas fa-history me-2 t-cyan"></i>Historique des snapshots
            </h5>
            <div class="card-glass overflow-x-auto">
              <table class="tbl">
                <thead><tr>
                  <th>DATE</th>
                  <th class="num">PA</th>
                  <th class="num">CB</th>
                  <th class="num col-per">PER</th>
                  <th class="num col-peg">PEG</th>
                  <th class="num col-pr">P/R</th>
                  <th class="num col-pb">P/B</th>
                </tr></thead>
                <tbody>
                  <?php foreach ($history as $row):
                    $per = (float)($row['per'] ?? 0);
                    $peg = (float)($row['peg'] ?? 0);
                    $pr  = (float)($row['pr']  ?? 0);
                    $pb  = (float)($row['pb']  ?? 0);
                    $perColor = $per == 0 ? 'none' : ($per < PER_GREEN ? 'green' : ($per < PER_ORANGE ? 'orange' : 'red'));
                    $pegColor = $peg <= 0 ? 'none' : ($peg < PEG_GREEN ? 'green' : ($peg < PEG_ORANGE ? 'orange' : 'red'));
                    $prColor  = $pr  == 0 ? 'none' : ($pr  < PR_GREEN  ? 'green' : ($pr  < PR_ORANGE  ? 'orange' : 'red'));
                    $pbColor  = $pb  == 0 ? 'none' : ($pb  < PB_GREEN  ? 'green' : ($pb  < PB_ORANGE  ? 'orange' : 'red'));
                  ?>
                  <tr>
                    <td class="date"><?= fmt_date($row['date'] ?? '') ?></td>
                    <td class="num mono"><?= number_format((float)($row['pa'] ?? 0), 2) ?></td>
                    <td class="num mono"><?= number_format((float)($row['cb'] ?? 0), 0, ',', ' ') ?></td>
                    <td class="num mono col-per c-<?= $perColor ?>">
                      <?= $per == 0 ? '—' : number_format($per, 2) ?>
                    </td>
                    <td class="num mono col-peg c-<?= $pegColor ?>">
                      <?= $peg == 0 ? '—' : number_format($peg, 2) ?>
                    </td>
                    <td class="num mono col-pr c-<?= $prColor ?>">
                      <?= $pr == 0 ? '—' : number_format($pr, 2) ?>
                    </td>
                    <td class="num mono col-pb c-<?= $pbColor ?>">
                      <?= $pb == 0 ? '—' : number_format($pb, 2) ?>
                    </td>
                  </tr>
                  <?php endforeach; ?>
                </tbody>
              </table>
            </div>

          <?php else: ?>
            <div class="alert alert-info">
              <i class="fas fa-info-circle me-2"></i>
              Aucun snapshot pour cette société. Utilisez
              <a href="Update.php" class="t-cyan">Update Stock</a> pour en créer un.
            </div>
          <?php endif; ?>

        </div>
      <?php endif; ?>
    <?php endif; ?>

    <?php endif; ?>

  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="assets/js/app.js"></script>
<?php if (!empty($sparkData) && count($sparkData) > 1): ?>
<script>
  const ctx    = document.getElementById('sparklineChart').getContext('2d');
  const labels = <?= json_encode($sparkLabels) ?>;
  const data   = <?= json_encode($sparkData) ?>;
  const first  = data[0], last = data[data.length - 1];
  const color  = last >= first ? '#10b981' : '#f43f5e';

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data,
        borderColor: color,
        borderWidth: 2,
        pointRadius: data.length < 25 ? 4 : 0,
        pointHoverRadius: 6,
        pointBackgroundColor: color,
        fill: true,
        backgroundColor: (ctx) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
          g.addColorStop(0, color === '#10b981' ? 'rgba(16,185,129,0.18)' : 'rgba(244,63,94,0.18)');
          g.addColorStop(1, 'rgba(0,0,0,0)');
          return g;
        },
        tension: 0.35,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ' PA : ' + c.raw.toFixed(2) + ' MAD' } }
      },
      scales: {
        x: { ticks: { color: '#475569', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { ticks: { color: '#475569' },                   grid: { color: 'rgba(255,255,255,0.04)' } }
      }
    }
  });
</script>
<?php endif; ?>
</body>
</html>
