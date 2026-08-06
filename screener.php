<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';

// ─── Helper: color rating for a ratio ────────────────────
// A ratio is only meaningful when it is strictly positive. A negative PER means
// the company loses money; a negative P/R or P/B means a negative denominator.
// Those must never be scored — before, `-70.97 < PR_GREEN` returned 'green' and
// inflated the 0-4 composite for exactly the companies that deserve it least.
function rateColor(string $ratio, float $val): string {
    if ($val <= 0) return 'none';
    switch ($ratio) {
        case 'PER': return $val < PER_GREEN ? 'green' : ($val < PER_ORANGE ? 'orange' : 'red');
        case 'PEG': return $val < PEG_GREEN ? 'green' : ($val < PEG_ORANGE ? 'orange' : 'red');
        case 'PR':  return $val < PR_GREEN  ? 'green' : ($val < PR_ORANGE  ? 'orange' : 'red');
        case 'PB':  return $val < PB_GREEN  ? 'green' : ($val < PB_ORANGE  ? 'orange' : 'red');
    }
    return 'none';
}

// Render a ratio cell value: an em-dash whenever the ratio is not meaningful.
function ratioTxt(float $val): string {
    return $val > 0 ? number_format($val, 2) : '—';
}

// ─── Fetch: latest + previous snapshot per company ────────
$rows    = [];
$dbError = null;

$lastUpdate = null;

try {
    // Fetch up to 500 records ordered newest-first.
    // First occurrence of each c_name = latest; second = previous (for Δ%).
    $docs = aw_list_docs('data', [q_order_desc('date'), q_limit(500)]);

    // Sector column + readable display label, from one pass over `company`.
    $sectorOf = [];
    $labelOf  = [];
    foreach (aw_list_docs('company', [q_limit(500)]) as $c) {
        $n = trim($c['name'] ?? '');
        if ($n === '') continue;
        if (!empty($c['sector'])) $sectorOf[$n] = $c['sector'];
        $labelOf[$n] = display_name($n, $c['ext_name'] ?? null);
    }

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
        // MASI is an index, not a screenable company.
        if ($name === 'MASI') { $lastUpdate = $r['date'] ?? $lastUpdate; continue; }

        // A non-positive PER means the company has negative or unknown earnings.
        // That is information worth showing, not a reason to drop the row — this
        // `continue` used to hide 9 real listed companies from the screener.
        $per = (float)($r['per'] ?? 0);

        $colors = [
            'PER' => rateColor('PER', $per),
            'PEG' => rateColor('PEG', (float)($r['peg'] ?? 0)),
            'PR'  => rateColor('PR',  (float)($r['pr']  ?? 0)),
            'PB'  => rateColor('PB',  (float)($r['pb']  ?? 0)),
        ];
        $score = count(array_filter($colors, fn($c) => $c === 'green'));

        $pa    = (float)($r['pa'] ?? 0);
        // Use API variation if stored, fall back to calculated from prev snapshot
        if (isset($r['variation'])) {
            $trend = (float)$r['variation'];
        } else {
            $prevPA = isset($prev[$name]) ? (float)($prev[$name]['pa'] ?? 0) : 0;
            $trend  = ($prevPA > 0) ? (($pa - $prevPA) / $prevPA * 100) : null;
        }

        if ($lastUpdate === null || ($r['date'] ?? '') > $lastUpdate) {
            $lastUpdate = $r['date'] ?? $lastUpdate;
        }

        // TICKER-sourced rows (instruments that did not trade today) carry no
        // volume at all. Absent volume — not zero volume — is the signal.
        $traded = isset($r['qty_traded']) && (float)$r['qty_traded'] > 0;

        $rows[] = [
            'name'   => $name,
            // Readable label for display; `name` stays the link/sort key.
            'label'  => $labelOf[$name] ?? $name,
            'symbol' => $r['symbol'] ?? '',
            'sector' => $sectorOf[$name] ?? '',
            'traded' => $traded,
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

    // Sort by PER ascending, with unscoreable companies (PER <= 0) last.
    usort($rows, function ($a, $b) {
        $av = $a['PER'] > 0 ? $a['PER'] : INF;
        $bv = $b['PER'] > 0 ? $b['PER'] : INF;
        return $av <=> $bv;
    });

} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// ─── Summary stats ────────────────────────────────────────
// Averages and counts are over companies with a meaningful PER only; the total
// count covers every listed company we hold a price for.
$totalCompanies = count($rows);
$rated          = array_filter($rows, fn($r) => $r['PER'] > 0);
$avgPER         = $rated
    ? round(array_sum(array_column($rated, 'PER')) / count($rated), 2)
    : 0;
$allGreen       = count(array_filter($rows, fn($r) => $r['score'] === 4));
$defaultBelow22 = count(array_filter($rows, fn($r) => $r['PER'] > 0 && $r['PER'] < 22));
$noPER          = $totalCompanies - count($rated);
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>myInterpreter | Screener</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=3" rel="stylesheet">
  <link href="assets/css/screener.css?v=4" rel="stylesheet">
</head>
<body>
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php $screenerCount = $totalCompanies; include 'core/sidebar.php'; ?>
  <main class="main">

  <div class="screener-wrap animate-up">

    <!-- Header -->
    <div class="screener-hero">
      <h1><i class="fas fa-filter t-cyan me-2"></i>Stock Screener</h1>
      <p>Filtrez les sociétés par seuil de PER et qualité des ratios. Cliquez sur un en-tête pour trier.</p>
      <p class="data-source">
        <i class="fas fa-clock me-1"></i>
        Dernière mise à jour :
        <strong><?= fmt_datetime($lastUpdate) ?></strong>
        <span class="muted">(heure de Casablanca)</span>
        &nbsp;·&nbsp;
        <i class="fas fa-database me-1"></i>
        Source : the market data feed — cours différés d’environ 15 minutes,
        actualisés toutes les 15 min de 09:00 à 16:45, du lundi au vendredi.
      </p>
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
      <div class="stat-chip">
        <span class="stat-chip__value mono muted" style="font-size:1.3rem"><?= $noPER ?></span>
        <span class="stat-chip__label">Sans PER (pertes / données manquantes)</span>
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
              <th onclick="sortTable(0,'str')" title="Nom de la société et symbole boursier">
                Société <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(1,'str')" title="Secteur d'activité">
                Secteur <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(2,'num')" title="Dernier prix connu" class="num">
                PA <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(3,'num')" title="Variation depuis le cours de référence" class="num">
                Δ% <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(4,'num')" title="Score : nombre de ratios verts (0-4)" style="text-align:center">
                Score <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(5,'num')" title="Price Earning Ratio — seuil vert : <?= PER_GREEN ?> · orange : <?= PER_ORANGE ?>" style="text-align:center">
                PER <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(6,'num')" title="Price/Earnings to Growth — seuil vert : <?= PEG_GREEN ?> · orange : <?= PEG_ORANGE ?>" style="text-align:center">
                PEG <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(7,'num')" title="Price / ROE — seuil vert : <?= PR_GREEN ?> · orange : <?= PR_ORANGE ?>" style="text-align:center">
                P/R <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(8,'num')" title="Price to Book — seuil vert : <?= PB_GREEN ?> · orange : <?= PB_ORANGE ?>" style="text-align:center">
                P/B <span class="sort-icon">↕</span>
              </th>
              <th onclick="sortTable(9,'str')" title="Horodatage du dernier snapshot (heure de Casablanca)" class="num">
                Mise à jour <span class="sort-icon">↕</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <?php if (empty($rows)): ?>
              <tr class="no-results"><td colspan="10">
                <i class="fas fa-inbox fa-2x d-block mb-3 muted"></i>
                Aucune donnée. Ajoutez des sociétés via <a href="Update.php" class="t-cyan">Update Stock</a>.
              </td></tr>
            <?php else: ?>
              <?php foreach ($rows as $r):
                $trendClass = 'trend-flat';
                $trendTxt   = '—';
                $trendVal   = 0;
                if (!$r['traded']) {
                    // No trade today: the price is the last known close, and a
                    // "0.00%" here would wrongly read as "opened and went flat".
                    $trendClass = 'trend-untraded';
                    $trendTxt   = 'non traité';
                } elseif ($r['trend'] !== null) {
                    $trendVal   = round($r['trend'], 2);
                    $trendClass = $r['trend'] > 0 ? 'trend-up' : ($r['trend'] < 0 ? 'trend-down' : 'trend-flat');
                    $arrow      = $r['trend'] > 0 ? '▲' : ($r['trend'] < 0 ? '▼' : '●');
                    $trendTxt   = $arrow . ' ' . number_format(abs($r['trend']), 2) . '%';
                }
                $scoreClass = 'score-' . $r['score'];
                // Rows with no meaningful PER carry an empty data-per so the JS
                // filter can treat them as "unrated" rather than as PER = 0,
                // which would otherwise pass every "PER max" threshold.
                $perAttr = $r['PER'] > 0 ? $r['PER'] : '';
              ?>
              <tr
                data-per="<?= $perAttr ?>"
                data-score="<?= $r['score'] ?>"
                data-href="infoAction.php?name=<?= urlencode($r['name']) ?>"
                style="cursor:pointer"
              >
                <!-- 0: Company -->
                <td class="company-cell" data-val="<?= htmlspecialchars($r['label']) ?>"
                    <?= $r['label'] !== $r['name'] ? 'title="' . htmlspecialchars($r['name']) . '"' : '' ?>>
                  <a href="infoAction.php?name=<?= urlencode($r['name']) ?>">
                    <i class="fas fa-building" style="font-size:0.75rem;color:var(--text-mute)"></i>
                    <?= htmlspecialchars($r['label']) ?>
                  </a>
                  <?php if ($r['symbol'] !== '' && strcasecmp($r['label'], $r['symbol']) !== 0): ?>
                    <span class="ticker-badge mono"><?= htmlspecialchars($r['symbol']) ?></span>
                  <?php endif; ?>
                </td>
                <!-- 1: Sector -->
                <td class="sector-cell" data-val="<?= htmlspecialchars($r['sector']) ?>">
                  <?= $r['sector'] !== '' ? htmlspecialchars($r['sector']) : '—' ?>
                </td>
                <!-- 2: PA -->
                <td class="pa-cell num" data-val="<?= $r['PA'] ?>">
                  <?= number_format($r['PA'], 2) ?>
                </td>
                <!-- 3: Trend -->
                <td class="trend-cell <?= $trendClass ?>" data-val="<?= $trendVal ?>">
                  <?= $trendTxt ?>
                </td>
                <!-- 4: Score -->
                <td class="score-cell" data-val="<?= $r['score'] ?>">
                  <span class="score-badge <?= $scoreClass ?>"><?= $r['score'] ?>/4</span>
                </td>
                <!-- 5: PER -->
                <td class="ratio-cell" data-val="<?= $perAttr ?>"
                    <?= $r['PER'] < 0 ? 'title="Bénéfice par action négatif — le PER n\'a pas de sens"' : '' ?>>
                  <span class="ratio-pill <?= $r['colors']['PER'] ?>"><?= ratioTxt($r['PER']) ?></span>
                </td>
                <!-- 6: PEG -->
                <td class="ratio-cell" data-val="<?= $r['PEG'] > 0 ? $r['PEG'] : '' ?>">
                  <span class="ratio-pill <?= $r['colors']['PEG'] ?>"><?= ratioTxt($r['PEG']) ?></span>
                </td>
                <!-- 7: PR -->
                <td class="ratio-cell" data-val="<?= $r['PR'] > 0 ? $r['PR'] : '' ?>">
                  <span class="ratio-pill <?= $r['colors']['PR'] ?>"><?= ratioTxt($r['PR']) ?></span>
                </td>
                <!-- 8: PB -->
                <td class="ratio-cell" data-val="<?= $r['PB'] > 0 ? $r['PB'] : '' ?>">
                  <span class="ratio-pill <?= $r['colors']['PB'] ?>"><?= ratioTxt($r['PB']) ?></span>
                </td>
                <!-- 9: Date -->
                <td class="date-cell" data-val="<?= $r['date'] ?>">
                  <?= fmt_time($r['date']) ?>
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
  </main>
</div>

<script src="assets/js/app.js"></script>
<script>
// ── State ────────────────────────────────────────────────
const PER_COL    = 5;   // index of the PER column
let currentPER   = 22;
let currentScore = 0;
let sortCol      = null;  // no column sorted yet — see the init block
let sortAsc      = true;

// ── Filter ───────────────────────────────────────────────
// Rows with no meaningful PER (negative or unknown earnings) carry an empty
// data-per. They can't satisfy a "PER max" threshold, so they surface only
// under the "Tout" preset — but they are never removed from the document.
function applyFilters() {
  const rows = document.querySelectorAll('#screenerTable tbody tr[data-per]');
  const showAll = currentPER >= 999;
  let visible = 0;
  rows.forEach(row => {
    const raw   = row.dataset.per;
    const per   = raw === '' ? NaN : parseFloat(raw);
    const score = parseInt(row.dataset.score);
    const passesPER = Number.isNaN(per) ? showAll : per < currentPER;
    const show  = passesPER && score >= currentScore;
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
    // A newly picked column always starts ascending: strings A-Z, numbers
    // small-first. (This used to read `sortAsc = type === 'str'`, which gave
    // numeric columns a descending first click — the opposite of its comment.)
    sortCol = colIdx;
    sortAsc = true;
  }

  const tbody = document.querySelector('#screenerTable tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr[data-per]'));

  rows.sort((a, b) => {
    const av = a.cells[colIdx].dataset.val ?? a.cells[colIdx].textContent.trim();
    const bv = b.cells[colIdx].dataset.val ?? b.cells[colIdx].textContent.trim();

    if (type === 'num') {
      const an = av === '' ? NaN : parseFloat(av);
      const bn = bv === '' ? NaN : parseFloat(bv);
      // Blanks ("—" cells) always sink to the bottom, in both directions —
      // otherwise flipping to descending would bury every rated company under
      // a block of empty rows.
      if (Number.isNaN(an) && Number.isNaN(bn)) return 0;
      if (Number.isNaN(an)) return 1;
      if (Number.isNaN(bn)) return -1;
      return sortAsc ? an - bn : bn - an;
    }

    const cmp = av.localeCompare(bv, 'fr');
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
// The row's target lives in data-href. There used to be an inline
// onclick="window.location='infoAction.php'" here as well, which raced this
// handler and could land the user on the search page with no company selected.
document.querySelectorAll('#screenerTable tbody tr[data-href]').forEach(row => {
  row.addEventListener('click', (e) => {
    if (e.target.closest('a')) return;   // let direct link clicks through
    window.location.href = row.dataset.href;
  });
});

// ── Init: sort by PER asc, apply default PER < 22 ───────
// sortCol starts as null so this call takes the "new column" branch and sets
// ascending. Previously sortCol was pre-set to the PER column, so this same
// call hit the toggle branch and flipped to descending — while the code below
// stamped an ascending arrow on the header, making the table lie about itself.
window.addEventListener('DOMContentLoaded', () => {
  sortTable(PER_COL, 'num');
  applyFilters();
});
</script>
</body>
</html>
