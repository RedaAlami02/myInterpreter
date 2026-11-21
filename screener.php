<?php
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/core/i18n.php';
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';
require_once 'core/auth.php';
// Only index.php and infoAction.php are public; this screen needs an account.
requireLogin();

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
    // The two reads are independent shared tables, so they travel together:
    // measured as 1086 ms when issued back to back.
    $shared = aw_multi_list_docs([
        // Up to 500 records ordered newest-first. First occurrence of each
        // c_name = latest; second = previous (for Δ%).
        'data' => ['data', [q_order_desc('date'), q_limit(500)], null],
        'company' => ['company', [q_limit(500)], null],
    ]);
    $docs = $shared['data'];

    // Sector column + readable display label, from one pass over `company`.
    $sectorOf = [];
    $labelOf  = [];
    foreach ($shared['company'] as $c) {
        $n = trim($c['name'] ?? '');
        if ($n === '') continue;
        if (!empty($c['sector'])) $sectorOf[$n] = $c['sector'];
        $labelOf[$n] = display_name($n, $c['ext_name'] ?? null);
    }

    $latest = [];  // c_name => doc
    $prev   = [];  // c_name => previous *day* doc
    $latestDay = [];

    foreach ($docs as $d) {
        $n = trim($d['c_name'] ?? '');
        if (!$n) continue;
        $day = substr($d['date'] ?? '', 0, 10);
        if (!isset($latest[$n])) {
            $latest[$n] = $d;
            $latestDay[$n] = $day;
        } elseif (!isset($prev[$n]) && $day !== $latestDay[$n]) {
            // Intraday rows made "second occurrence" a fifteen-minute-old run.
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
app_timing_mark('data');

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
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title><?= te('myInterpreter | Screener') ?></title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/screener.css?v=20261115" rel="stylesheet">
  <?php require 'core/theme.php'; ?>
</head>
<body class="workspace workspace-screener">
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php $screenerCount = $totalCompanies; include 'core/sidebar.php'; ?>
  <main class="main">

  <div class="screener-wrap animate-up">

    <h1 class="screener-sr-title"><?= te('Sélection d’actions') ?></h1>

    <?php if ($dbError): ?>
      <div class="alert alert-danger">
        <i class="fas fa-bug me-2"></i><strong><?= te('Erreur DB :') ?></strong> <?= htmlspecialchars($dbError) ?>
      </div>
    <?php else: ?>

    <!-- Summary chips -->
    <div class="summary-row stagger-children">
      <div class="stat-chip">
        <span class="stat-chip__value t-cyan" id="visibleCount"><?= $defaultBelow22 ?></span>
        <span class="stat-chip__label"><?= te('Résultats avec PER &lt; 22') ?></span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value mono" style="font-size:1.3rem"><?= $totalCompanies ?></span>
        <span class="stat-chip__label"><?= te('Sociétés suivies') ?></span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value mono t-violet" style="font-size:1.3rem"><?= number_format($avgPER, 2) ?></span>
        <span class="stat-chip__label"><?= te('PER moyen') ?></span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value t-emerald"><?= $allGreen ?></span>
        <span class="stat-chip__label"><?= te('Score complet') ?></span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip__value mono muted" style="font-size:1.3rem"><?= $noPER ?></span>
        <span class="stat-chip__label"><?= te('Sans PER') ?></span>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">

      <div class="filter-group">
        <label class="filter-label" for="perInput"><?= te('PER maximum') ?></label>
        <input type="number" id="perInput" class="filter-input" value="22" min="1" max="999" step="1">
      </div>

      <div class="filter-group">
        <div class="filter-label"><?= te('Seuil rapide') ?></div>
        <div class="filter-presets">
          <button class="preset-btn" onclick="setPreset(10)">≤ 10</button>
          <button class="preset-btn" onclick="setPreset(15)">≤ 15</button>
          <button class="preset-btn active" onclick="setPreset(22)">≤ 22</button>
          <button class="preset-btn" onclick="setPreset(25)">≤ 25</button>
          <button class="preset-btn" onclick="setPreset(999)"><?= te('Tout') ?></button>
        </div>
      </div>

      <div class="filter-divider"></div>

      <div class="filter-group">
        <div class="filter-label"><?= te('Score minimum') ?></div>
        <div class="filter-presets">
          <button class="preset-btn active" id="score-0" onclick="setScore(0)"><?= te('Tous') ?></button>
          <button class="preset-btn" id="score-2" onclick="setScore(2)">≥ 2 <i class="fas fa-circle t-emerald" style="font-size:0.5rem"></i></button>
          <button class="preset-btn" id="score-3" onclick="setScore(3)">≥ 3 <i class="fas fa-circle t-emerald" style="font-size:0.5rem"></i></button>
          <button class="preset-btn" id="score-4" onclick="setScore(4)">4/4 <i class="fas fa-check-circle t-emerald" style="font-size:0.7rem"></i></button>
        </div>
      </div>

      <div class="topbar-spacer"></div>
      <span class="active-count"><span id="activeCount"><?= $defaultBelow22 ?></span> <?= te('résultats') ?></span>
    </div>

    <!-- Table -->
    <div class="screener-table-intro">
      <div>
        <h2><?= te('Sociétés correspondant aux critères') ?></h2>
        <p><?= te('Triées par PER croissant') ?></p>
      </div>
      <div class="ratio-key" aria-label="<?= te('Légende des ratios') ?>">
        <span><i class="key-dot key-good"></i> <?= te('favorable') ?></span>
        <span><i class="key-dot key-watch"></i> <?= te('à surveiller') ?></span>
        <span><i class="key-dot key-risk"></i> <?= te('élevé') ?></span>
      </div>
    </div>
    <p class="table-scroll-hint"><i class="fas fa-arrows-left-right" aria-hidden="true"></i> <?= te('Faites glisser pour comparer tous les ratios') ?></p>
    <div class="screener-table-wrap">
      <div class="overflow-x-auto">
        <table class="tbl screener-tbl" id="screenerTable">
          <caption class="visually-hidden"><?= te('Sociétés filtrées avec leurs cours, variations, scores et ratios de valorisation') ?></caption>
          <thead>
            <tr>
              <th data-column="0" aria-sort="none">
                <button type="button" class="sort-btn" onclick="sortTable(0,'str')" title="<?= te('Trier par société') ?>">
                  <?= te('Société') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="1" aria-sort="none">
                <button type="button" class="sort-btn" onclick="sortTable(1,'str')" title="<?= te('Trier par secteur') ?>">
                  <?= te('Secteur') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="2" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(2,'num')" title="<?= te('Trier par dernier cours connu') ?>">
                  <?= te('Cours (MAD)') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="3" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(3,'num')" title="<?= te('Trier par variation de séance') ?>">
                  <?= te('Séance') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="4" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(4,'num')" title="<?= te('Trier par score, sur quatre ratios') ?>">
                  <?= te('Score') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="5" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(5,'num')" title="Price Earning Ratio — seuil favorable : <?= PER_GREEN ?> <?= te('· à surveiller :') ?> <?= PER_ORANGE ?>">
                  <abbr title="<?= te('Price Earning Ratio') ?>">PER</abbr> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="6" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(6,'num')" title="Price/Earnings to Growth — seuil favorable : <?= PEG_GREEN ?> <?= te('· à surveiller :') ?> <?= PEG_ORANGE ?>">
                  <abbr title="<?= te('Price/Earnings to Growth') ?>">PEG</abbr> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="7" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(7,'num')" title="Price / ROE — seuil favorable : <?= PR_GREEN ?> <?= te('· à surveiller :') ?> <?= PR_ORANGE ?>">
                  <abbr title="<?= te('Price / ROE') ?>">P/R</abbr> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="8" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(8,'num')" title="Price to Book — seuil favorable : <?= PB_GREEN ?> <?= te('· à surveiller :') ?> <?= PB_ORANGE ?>">
                  <abbr title="<?= te('Price to Book') ?>">P/B</abbr> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
              <th data-column="9" aria-sort="none" class="num">
                <button type="button" class="sort-btn" onclick="sortTable(9,'str')" title="<?= te('Trier par heure du dernier snapshot, heure de Casablanca') ?>">
                  <?= te('Heure') ?> <span class="sort-icon" aria-hidden="true">↕</span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <?php if (empty($rows)): ?>
              <tr class="no-results"><td colspan="10">
                <i class="fas fa-inbox fa-2x d-block mb-3 muted"></i>
                <?= te('Aucune donnée. Ajoutez des sociétés via') ?> <a href="Update.php" class="t-cyan"><?= te('Update Stock') ?></a>.
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
                <td class="sector-cell" data-val="<?= te($r['sector']) ?>">
                  <?= $r['sector'] !== '' ? te($r['sector']) : '—' ?>
                </td>
                <!-- 2: PA -->
                <td class="pa-cell num" data-val="<?= $r['PA'] ?>" data-live-quote="<?= htmlspecialchars($r['name']) ?>">
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
                    <?= $r['PER'] <= 0 ? 'title="' . htmlspecialchars(te("Bénéfice négatif, nul ou non significatif — le PER n'a pas de sens")) . '"' : '' ?>>
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
                  <?= fmt_datetime($r['date']) ?>
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

<script src="assets/js/app.js?v=3"></script>
<?php if (!$dbError): ?>
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
    b.classList.toggle('active', b.getAttribute('onclick') === 'setPreset(' + val + ')');
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
    th.setAttribute('aria-sort', 'none');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '↕';
    if (i === colIdx) {
      th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
      th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
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
<?php endif; ?>
<?php app_timing_mark('rendered'); ?>
<script id="live-config" type="application/json"><?= json_encode([
    'endpoint' => BASE_URL . '/handlers/live_quotes.php',
    'interval' => 60000,
    'mode' => 'quotes',
], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
<script src="assets/js/live.js?v=2"></script>
</body>
</html>
