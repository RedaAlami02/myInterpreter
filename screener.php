<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';

// ─── Helper: color rating for a ratio ────────────────────
function rateColor(string $ratio, float $val): string {
    if ($val == 0) return 'none';
    switch ($ratio) {
        case 'PER': return $val < PER_GREEN ? 'green' : ($val < PER_ORANGE ? 'orange' : 'red');
        case 'PEG': return ($val > 0 && $val < PEG_GREEN)
                         ? 'green'
                         : (($val > 0 && $val < PEG_ORANGE) ? 'orange' : 'red');
        case 'PR':  return $val < PR_GREEN  ? 'green' : ($val < PR_ORANGE  ? 'orange' : 'red');
        case 'PB':  return $val < PB_GREEN  ? 'green' : ($val < PB_ORANGE  ? 'orange' : 'red');
    }
    return 'none';
}

// ─── Fetch: latest + previous snapshot per company ────────
$rows    = [];
$dbError = null;

try {
    // Fetch up to 500 records ordered newest-first.
    // First occurrence of each c_name = latest; second = previous (for Δ%).
    $docs = aw_list_docs('data', [q_order_desc('date'), q_limit(500)]);

    $latest = [];  // c_name => doc
    $prev   = [];  // c_name => doc (second occurrence)

    foreach ($docs as $d) {
        $n = trim($d['c_name'] ?? '');
        if (!$n) continue;
        if (!isset($latest[$n])) {
            $latest[$n] = $d;
        } elseif (!isset($prev[$n])) {
            $prev[$n] = $d;
        }
    }

    foreach ($latest as $name => $r) {
        $per = (float)($r['per'] ?? 0);
        if ($per <= 0) continue;

        $colors = [
            'PER' => rateColor('PER', $per),
            'PEG' => rateColor('PEG', (float)($r['peg'] ?? 0)),
            'PR'  => rateColor('PR',  (float)($r['pr']  ?? 0)),
            'PB'  => rateColor('PB',  (float)($r['pb']  ?? 0)),
        ];
        $score = count(array_filter($colors, fn($c) => $c === 'green'));

        $pa      = (float)($r['pa'] ?? 0);
        $prevPA  = isset($prev[$name]) ? (float)($prev[$name]['pa'] ?? 0) : 0;
        $trend   = ($prevPA > 0) ? (($pa - $prevPA) / $prevPA * 100) : null;

        $rows[] = [
            'name'   => $name,
            'PA'     => $pa,
            'CB'     => (float)($r['cb'] ?? 0),
            'PER'    => $per,
            'PEG'    => (float)($r['peg'] ?? 0),
            'PR'     => (float)($r['pr']  ?? 0),
            'PB'     => (float)($r['pb']  ?? 0),
            'date'   => $r['date'] ?? '',
            'colors' => $colors,
            'score'  => $score,
            'trend'  => $trend,
        ];
    }

    // Sort by PER ascending
    usort($rows, fn($a, $b) => $a['PER'] <=> $b['PER']);



} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// ─── Summary stats ────────────────────────────────────────
$totalCompanies = count($rows);
$avgPER         = $totalCompanies
    ? round(array_sum(array_column($rows, 'PER')) / $totalCompanies, 2)
    : 0;
$allGreen       = count(array_filter($rows, fn($r) => $r['score'] === 4));
$defaultBelow22 = count(array_filter($rows, fn($r) => $r['PER'] < 22));
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>myInterpreter | Screener</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/screener.css" rel="stylesheet">
</head>
<body>
<div class="page">

  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Screener</span>
    <div class="topbar-spacer"></div>
    <a href="index.php" class="btn btn-ghost btn-sm"><i class="fas fa-home"></i></a>
  </nav>

  <div class="screener-wrap animate-up">

    <!-- Header -->
    <div class="screener-hero">
      <h1><i class="fas fa-filter t-cyan me-2"></i>Stock Screener</h1>
      <p>Filtrez les sociétés par seuil de PER et qualité des ratios. Cliquez sur un en-tête pour trier.</p>
    </div>

    <?php if ($dbError): ?>
      <div class="alert alert-danger">
        <i class="fas fa-bug me-2"></i><strong>Erreur DB :</strong> <?= htmlspecialchars($dbError) ?>
      </div>
    <?php else: ?>

    <!-- Summary chips -->
    <div class="summary-row stagger-children">
      <div class="stat-chip">
        <span class="stat-chip__value t-cyan" id="visibleCount"><?= $defaultBelow22 ?></span>
        <span class="stat-chip__label">Sélectionnées (PER &lt; 22)</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value mono" style="font-size:1.3rem"><?= $totalCompanies ?></span>
        <span class="stat-chip__label">Sociétés au total</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value mono t-violet" style="font-size:1.3rem"><?= number_format($avgPER, 2) ?></span>
        <span class="stat-chip__label">PER moyen global</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value t-emerald"><?= $allGreen ?></span>
        <span class="stat-chip__label">Score 4/4 (tous verts)</span>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">

      <div class="filter-group">
        <div class="filter-label"><i class="fas fa-sliders-h me-1"></i>PER max</div>
        <input type="number" id="perInput" class="filter-input" value="22" min="1" max="999" step="1">
      </div>

      <div class="filter-group">
        <div class="filter-label">Préréglages rapides</div>
        <div class="filter-presets">
          <button class="preset-btn" onclick="setPreset(10)">≤ 10</button>
          <button class="preset-btn" onclick="setPreset(15)">≤ 15</button>
          <button class="preset-btn active" onclick="setPreset(22)">≤ 22</button>
          <button class="preset-btn" onclick="setPreset(25)">≤ 25</button>
          <button class="preset-btn" onclick="setPreset(999)">Tout</button>
        </div>
      </div>

      <div class="filter-divider"></div>

      <div class="filter-group">
        <div class="filter-label"><i class="fas fa-star me-1"></i>Score min</div>
        <div class="filter-presets">
          <button class="preset-btn active" id="score-0" onclick="setScore(0)">Tous</button>
          <button class="preset-btn" id="score-2" onclick="setScore(2)">≥ 2 <i class="fas fa-circle t-emerald" style="font-size:0.5rem"></i></button>
          <button class="preset-btn" id="score-3" onclick="setScore(3)">≥ 3 <i class="fas fa-circle t-emerald" style="font-size:0.5rem"></i></button>
          <button class="preset-btn" id="score-4" onclick="setScore(4)">4/4 <i class="fas fa-check-circle t-emerald" style="font-size:0.7rem"></i></button>
        </div>
      </div>

      <div class="topbar-spacer"></div>
      <span class="active-count"><i class="fas fa-table me-1"></i><span id="activeCount"><?= $defaultBelow22 ?></span> résultats</span>
    </div>

    <!-- Table -->
    <div class="screener-table-wrap">
      <div class="overflow-x-auto">
        <table class="tbl screener-tbl" id="screenerTable">
          <thead>
            <tr>
              <th onclick="sortTable(0,'str')" title="Nom de la société">
                Société <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(1,'num')" title="Dernier prix connu" class="num">
                PA <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(2,'num')" title="Évolution vs snapshot précédent" class="num">
                Δ% <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(3,'num')" title="Score : nombre de ratios verts (0-4)" style="text-align:center">
                Score <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(4,'num')" title="Price Earning Ratio — seuil vert : <?= PER_GREEN ?> · orange : <?= PER_ORANGE ?>" style="text-align:center">
                PER <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(5,'num')" title="Price/Earnings to Growth — seuil vert : <?= PEG_GREEN ?> · orange : <?= PEG_ORANGE ?>" style="text-align:center">
                PEG <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(6,'num')" title="Price / ROE — seuil vert : <?= PR_GREEN ?> · orange : <?= PR_ORANGE ?>" style="text-align:center">
                P/R <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(7,'num')" title="Price to Book — seuil vert : <?= PB_GREEN ?> · orange : <?= PB_ORANGE ?>" style="text-align:center">
                P/B <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(8,'str')" title="Date du dernier snapshot" class="num">
                Mise à jour <span class="sort-icon">↕</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <?php if (empty($rows)): ?>
              <tr class="no-results"><td colspan="9">
                <i class="fas fa-inbox fa-2x d-block mb-3 muted"></i>
                Aucune donnée. Ajoutez des sociétés via <a href="Update.php" class="t-cyan">Update Stock</a>.
              </td></tr>
            <?php else: ?>
              <?php foreach ($rows as $r):
                $trendClass = 'trend-flat';
                $trendTxt   = '—';
                $trendVal   = 0;
                if ($r['trend'] !== null) {
                    $trendVal   = round($r['trend'], 2);
                    $trendClass = $r['trend'] > 0 ? 'trend-up' : ($r['trend'] < 0 ? 'trend-down' : 'trend-flat');
                    $arrow      = $r['trend'] > 0 ? '▲' : ($r['trend'] < 0 ? '▼' : '●');
                    $trendTxt   = $arrow . ' ' . number_format(abs($r['trend']), 2) . '%';
                }
                $scoreClass = 'score-' . $r['score'];
              ?>
              <tr
                data-per="<?= $r['PER'] ?>"
                data-score="<?= $r['score'] ?>"
                onclick="window.location='infoAction.php'"
                style="cursor:pointer"
              >
                <!-- 0: Company -->
                <td class="company-cell" data-val="<?= htmlspecialchars($r['name']) ?>">
                  <a href="infoAction.php?name=<?= urlencode($r['name']) ?>" onclick="event.stopPropagation()">
                    <i class="fas fa-building" style="font-size:0.75rem;color:var(--text-mute)"></i>
                    <?= htmlspecialchars($r['name']) ?>
                  </a>
                </td>
                <!-- 1: PA -->
                <td class="pa-cell num" data-val="<?= $r['PA'] ?>">
                  <?= number_format($r['PA'], 2) ?>
                </td>
                <!-- 2: Trend -->
                <td class="trend-cell <?= $trendClass ?>" data-val="<?= $trendVal ?>">
                  <?= $trendTxt ?>
                </td>
                <!-- 3: Score -->
                <td class="score-cell" data-val="<?= $r['score'] ?>">
                  <span class="score-badge <?= $scoreClass ?>"><?= $r['score'] ?>/4</span>
                </td>
                <!-- 4: PER -->
                <td class="ratio-cell" data-val="<?= $r['PER'] ?>">
                  <span class="ratio-pill <?= $r['colors']['PER'] ?>"><?= number_format($r['PER'], 2) ?></span>
                </td>
                <!-- 5: PEG -->
                <td class="ratio-cell" data-val="<?= $r['PEG'] ?>">
                  <span class="ratio-pill <?= $r['colors']['PEG'] ?>">
                    <?= $r['PEG'] == 0 ? '—' : number_format($r['PEG'], 2) ?>
                  </span>
                </td>
                <!-- 6: PR -->
                <td class="ratio-cell" data-val="<?= $r['PR'] ?>">
                  <span class="ratio-pill <?= $r['colors']['PR'] ?>">
                    <?= $r['PR'] == 0 ? '—' : number_format($r['PR'], 2) ?>
                  </span>
                </td>
                <!-- 7: PB -->
                <td class="ratio-cell" data-val="<?= $r['PB'] ?>">
                  <span class="ratio-pill <?= $r['colors']['PB'] ?>">
                    <?= $r['PB'] == 0 ? '—' : number_format($r['PB'], 2) ?>
                  </span>
                </td>
                <!-- 8: Date -->
                <td class="date-cell" data-val="<?= $r['date'] ?>">
                  <?= htmlspecialchars($r['date']) ?>
                </td>
              </tr>
              <?php endforeach; ?>
            <?php endif; ?>
          </tbody>
        </table>
      </div>
    </div>

    <?php endif; // end !$dbError ?>

  </div><!-- .screener-wrap -->
</div><!-- .page -->

<script src="assets/js/app.js"></script>
<script>
// ── State ────────────────────────────────────────────────
let currentPER   = 22;
let currentScore = 0;
let sortCol      = 4;   // PER column
let sortAsc      = true;

// ── Filter ───────────────────────────────────────────────
function applyFilters() {
  const rows = document.querySelectorAll('#screenerTable tbody tr[data-per]');
  let visible = 0;
  rows.forEach(row => {
    const per   = parseFloat(row.dataset.per);
    const score = parseInt(row.dataset.score);
    const show  = per < currentPER && score >= currentScore;
    row.classList.toggle('hidden-row', !show);
    if (show) visible++;
  });
  document.getElementById('visibleCount').textContent = visible;
  document.getElementById('activeCount').textContent  = visible;
}

function setPreset(val) {
  currentPER = val;
  document.getElementById('perInput').value = val === 999 ? '' : val;
  document.querySelectorAll('.preset-btn[onclick^="setPreset"]').forEach(b => {
    b.classList.toggle('active', b.textContent.trim().includes(val === 999 ? 'Tout' : val));
  });
  applyFilters();
}

function setScore(val) {
  currentScore = val;
  ['0','2','3','4'].forEach(s => {
    const btn = document.getElementById('score-' + s);
    if (btn) btn.classList.toggle('active', parseInt(s) === val);
  });
  applyFilters();
}

document.getElementById('perInput').addEventListener('input', function () {
  currentPER = parseFloat(this.value) || 999;
  document.querySelectorAll('.preset-btn[onclick^="setPreset"]').forEach(b => b.classList.remove('active'));
  applyFilters();
});

// ── Sort ─────────────────────────────────────────────────
function sortTable(colIdx, type) {
  if (sortCol === colIdx) {
    sortAsc = !sortAsc;
  } else {
    sortCol = colIdx;
    sortAsc = type === 'str'; // strings start A-Z, numbers start small-first
  }

  const tbody = document.querySelector('#screenerTable tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr[data-per]'));

  rows.sort((a, b) => {
    const av = a.cells[colIdx].dataset.val ?? a.cells[colIdx].textContent.trim();
    const bv = b.cells[colIdx].dataset.val ?? b.cells[colIdx].textContent.trim();

    let cmp;
    if (type === 'num') {
      cmp = (parseFloat(av) || 0) - (parseFloat(bv) || 0);
    } else {
      cmp = av.localeCompare(bv, 'fr');
    }
    return sortAsc ? cmp : -cmp;
  });

  rows.forEach(r => tbody.appendChild(r));

  // Update header indicators
  document.querySelectorAll('#screenerTable thead th').forEach((th, i) => {
    th.classList.remove('sort-asc', 'sort-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '↕';
    if (i === colIdx) {
      th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
      if (icon) icon.textContent = sortAsc ? '↑' : '↓';
    }
  });
}

// ── Click row → open infoAction ──────────────────────────
document.querySelectorAll('#screenerTable tbody tr[data-per]').forEach(row => {
  const nameCell = row.querySelector('.company-cell a');
  row.addEventListener('click', (e) => {
    if (e.target.closest('a')) return;   // let direct link clicks through
    if (nameCell) window.location.href = nameCell.href;
  });
});

// ── Init: sort by PER asc, apply default PER < 22 ───────
window.addEventListener('DOMContentLoaded', () => {
  sortTable(4, 'num');  // sort by PER ascending
  applyFilters();
  // Mark PER header as sorted
  const perTh = document.querySelector('#screenerTable thead th:nth-child(5)');
  if (perTh) {
    perTh.classList.add('sort-asc');
    const icon = perTh.querySelector('.sort-icon');
    if (icon) icon.textContent = '↑';
  }
});
</script>
</body>
</html>
