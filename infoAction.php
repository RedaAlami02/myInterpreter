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
                $sparkLabels[] = substr($row['date'] ?? '', 0, 10);
                $sparkData[]   = (float)($row['pa'] ?? 0);
            }

            // Get symbol for financial enrichment
            // Try from latest history doc first (has symbol since scraper update)
            $symbol = null;
            foreach ($history as $row) {
                if (!empty($row['symbol'])) { $symbol = $row['symbol']; break; }
            }
            // Fallback: format collection
            if (!$symbol) {
                $fmtRes = aw_list_docs('format', [q_equal('name', $name), q_limit(1)]);
                if (!empty($fmtRes)) $symbol = $fmtRes[0]['symbol'] ?? null;
            }
        }
    } catch (Throwable $e) {
        $dbError = $e->getMessage();
    }
}

// ─── Buy markers (shown when user is logged in) ───────────
$buyMarkers = [];
$awSession  = $_SESSION['aw_cookie'] ?? null;
if ($awSession && !empty($name ?? '')) {
    try {
        $uid = aw_user_id();
        if ($uid) {
            $achatsDocs = aw_list_docs('achats', [
                q_equal('c_name', $name),
                q_equal('user_id', $uid),
                q_order_asc('date'),
                q_limit(50),
            ], $awSession);
            foreach ($achatsDocs as $a) {
                $buyMarkers[] = [
                    'date'     => substr($a['date'] ?? '', 0, 10),
                    'price'    => (float)($a['price'] ?? 0),
                    'quantity' => (int)($a['quantity'] ?? 0),
                ];
            }
        }
    } catch (Throwable $e) { /* silently ignore — markers are optional */ }
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
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">

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

          <!-- Company header -->
          <div class="company-header mb-4">
            <div class="company-title-row">
              <div>
                <h4 class="company-name">
                  <?php if ($symbol): ?>
                    <span class="ticker-badge"><?= htmlspecialchars($symbol) ?></span>
                  <?php endif; ?>
                  <?= htmlspecialchars($company['name'] ?? $name) ?>
                  <?php if (!empty($company['sector'])): ?>
                    <span class="sector-badge"><?= htmlspecialchars($company['sector']) ?></span>
                  <?php endif; ?>
                </h4>
                <?php if (!empty($company['description'])): ?>
                  <p class="company-desc"><?= htmlspecialchars(mb_substr($company['description'], 0, 300)) ?>…</p>
                <?php endif; ?>
              </div>
            </div>

            <!-- Fundamentals grid -->
            <div class="fundamentals-grid">
              <?php
              $funds = [
                  'BPA'  => ['label' => 'BPA', 'val' => $company['bpa'] ?? null, 'unit' => 'MAD'],
                  'DPA'  => ['label' => 'DPA', 'val' => $company['dpa'] ?? null, 'unit' => 'MAD'],
                  'TC5'  => ['label' => 'TC5', 'val' => $company['tc5'] ?? null, 'unit' => '%'],
                  'ROE'  => ['label' => 'ROE', 'val' => $company['roe'] ?? null, 'unit' => '%'],
                  'NA'   => ['label' => 'Actions', 'val' => $company['na'] ?? null, 'unit' => ''],
                  'β3Y'  => ['label' => 'Béta 3Y', 'val' => $company['beta_3y'] ?? null, 'unit' => ''],
                  'CA'   => ['label' => 'CA', 'val' => $company['revenue'] ?? null, 'unit' => 'M'],
                  'RNPG' => ['label' => 'RNPG', 'val' => $company['net_profit'] ?? null, 'unit' => 'M'],
                  'DN'   => ['label' => 'Dette nette', 'val' => $company['net_debt'] ?? null, 'unit' => 'M'],
                  'Marge'=> ['label' => 'Marge nette', 'val' => $company['profit_margin'] ?? null, 'unit' => '%'],
              ];
              foreach ($funds as $key => $f):
                  if ($f['val'] === null) continue;
                  $v = is_float($f['val']) ? number_format($f['val'], 2, ',', ' ') : $f['val'];
              ?>
              <div class="fund-chip">
                <span class="fund-label"><?= $key ?></span>
                <span class="fund-val"><?= $v ?><?= $f['unit'] ? '<span class="fund-unit"> '.$f['unit'].'</span>' : '' ?></span>
              </div>
              <?php endforeach; ?>
            </div>
          </div>

          <?php if (!empty($history)): ?>

            <?php if (count($sparkData) > 1): ?>
            <div class="sparkline-wrap mb-4">
              <h5><i class="fas fa-chart-line me-2 t-cyan"></i>Évolution du prix (PA)</h5>
              <canvas id="sparklineChart" height="80"></canvas>
            </div>
            <?php endif; ?>

            <?php if ($symbol): ?>
            <!-- Financial enrichment (JS-loaded) -->
            <div id="mkt-enrichment" class="mb-4">
              <div id="mkt-loading" style="padding:24px;text-align:center;color:var(--text-faint);font-size:13px">
                <i class="fas fa-circle-notch fa-spin me-2"></i>Chargement données financières…
              </div>
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
  </main>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="assets/js/app.js"></script>

<?php if ($symbol ?? null): ?>
<script>
(async function() {
  const sym = <?= json_encode($symbol) ?>;
  const container = document.getElementById('mkt-enrichment');
  if (!container) return;

  try {
    const r   = await fetch('handlers/market_proxy.php?symbol=' + encodeURIComponent(sym));
    const d   = await r.json();
    const c   = d.computed || {};
    const ch  = d.charts   || {};

    let html = '';

    // Description
    if (d.description) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-info-circle me-2 t-cyan"></i>À propos</div>
        <p class="mkt-desc">${d.description.replace(/\r\n|\n/g,'<br>')}</p>
      </div>`;
    }

    // Financial charts
    const caData = ch.ca || {}; const rnpgData = ch.rnpg || {}; const ebeData = ch.ebe || {};
    const allYears = [...new Set([...Object.keys(caData), ...Object.keys(rnpgData), ...Object.keys(ebeData)])].sort();
    if (allYears.length > 0) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-chart-bar me-2 t-violet"></i>Résultats annuels (MMAD)</div>
        <div class="mkt-chart-wrap"><canvas id="finChart"></canvas></div>
      </div>`;
    }

    // Quarterly CA
    const trim = d.trim;
    if (trim) {
      const qKeys = Object.keys(trim).filter(k => /^T\d\d{4}$/.test(k)).sort();
      if (qKeys.length > 0) {
        html += `<div class="mkt-section">
          <div class="mkt-section-title"><i class="fas fa-calendar-alt me-2 t-amber"></i>Chiffre d'affaires trimestriel (MMAD)</div>
          <div class="mkt-chart-wrap"><canvas id="trimChart"></canvas></div>
        </div>`;
      }
    }

    // Shareholders
    if (d.shareholders && d.shareholders.length > 0) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-users me-2 t-emerald"></i>Actionnariat</div>
        <div class="mkt-two-col">
          <canvas id="holdersChart" style="max-height:220px"></canvas>
          <div class="holders-list" id="holders-list"></div>
        </div>
      </div>`;
    }

    container.innerHTML = html || '<div style="color:var(--text-faint);font-size:13px;padding:12px">Aucune donnée financière disponible pour cette société.</div>';

    // Draw financial chart
    if (allYears.length > 0) {
      const projYears = allYears.filter(y => y.endsWith('p'));
      const colors = y => projYears.includes(y) ? 'rgba(34,211,238,0.4)' : '#22d3ee';
      new Chart(document.getElementById('finChart').getContext('2d'), {
        type: 'bar',
        data: {
          labels: allYears,
          datasets: [
            { label: 'CA', data: allYears.map(y => caData[y]   ?? null), backgroundColor: allYears.map(y => projYears.includes(y) ? 'rgba(34,211,238,0.25)' : 'rgba(34,211,238,0.6)'), borderRadius: 4, order: 2 },
            { label: 'EBE', data: allYears.map(y => ebeData[y] ?? null), backgroundColor: allYears.map(y => projYears.includes(y) ? 'rgba(129,140,248,0.25)' : 'rgba(129,140,248,0.55)'), borderRadius: 4, order: 2 },
            { label: 'RNPG', data: allYears.map(y => rnpgData[y] ?? null), type: 'line', borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.12)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#10b981', tension: 0.3, fill: true, order: 1 },
          ]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 12 } } },
            tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw !== null ? c.raw.toFixed(2) : '—'} M` } }
          },
          scales: {
            x: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } },
            y: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } }
          }
        }
      });
    }

    // Draw quarterly chart
    if (trim) {
      const qKeys = Object.keys(trim).filter(k => /^T\d\d{4}$/.test(k)).sort().slice(-12);
      if (qKeys.length > 0 && document.getElementById('trimChart')) {
        new Chart(document.getElementById('trimChart').getContext('2d'), {
          type: 'bar',
          data: {
            labels: qKeys.map(k => k.replace('T','Q').replace(/(\d)(\d{4})/, '$1 $2')),
            datasets: [{ label: 'CA', data: qKeys.map(k => trim[k] ?? null), backgroundColor: 'rgba(245,158,11,0.55)', borderRadius: 4 }]
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } },
              y: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
          }
        });
      }
    }

    // Shareholders chart
    if (d.shareholders && d.shareholders.length > 0 && document.getElementById('holdersChart')) {
      const colors = ['#22d3ee','#818cf8','#10b981','#f59e0b','#f43f5e','#6ee7b7','#fb7185','#fbbf24'];
      new Chart(document.getElementById('holdersChart').getContext('2d'), {
        type: 'doughnut',
        data: {
          labels: d.shareholders.map(h => h.name),
          datasets: [{ data: d.shareholders.map(h => h.pct), backgroundColor: colors.slice(0, d.shareholders.length), borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false } }
        }
      });
      const list = document.getElementById('holders-list');
      list.innerHTML = d.shareholders.map((h, i) =>
        `<div class="holder-row"><span class="holder-dot" style="background:${colors[i % colors.length]}"></span><span class="holder-name">${h.name}</span><span class="holder-pct">${h.pct.toFixed(1)}%</span></div>`
      ).join('');
    }

  } catch (e) {
    document.getElementById('mkt-enrichment').innerHTML =
      `<div style="color:var(--text-faint);font-size:13px;padding:12px">Données financières indisponibles.</div>`;
  }
})();
</script>
<?php endif; ?>

<?php if (!empty($sparkData) && count($sparkData) > 1): ?>
<script>
  const ctx        = document.getElementById('sparklineChart').getContext('2d');
  const labels     = <?= json_encode($sparkLabels) ?>;
  const data       = <?= json_encode($sparkData) ?>;
  const buyMarkers = <?= json_encode($buyMarkers) ?>;
  const first      = data[0], last = data[data.length - 1];
  const color      = last >= first ? '#10b981' : '#f43f5e';

  const buyPinPlugin = {
    id: 'buyPin',
    afterDraw(chart) {
      if (!buyMarkers.length) return;
      const { ctx: c, chartArea, scales } = chart;
      buyMarkers.forEach(marker => {
        const idx = labels.indexOf(marker.date);
        if (idx === -1) return;
        const x   = scales.x.getPixelForValue(idx);
        const top = chartArea.top;
        const bot = chartArea.bottom;

        c.save();
        c.setLineDash([4, 3]);
        c.strokeStyle = 'rgba(6,182,212,0.65)';
        c.lineWidth   = 1.5;
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bot); c.stroke();

        c.setLineDash([]);
        c.fillStyle = '#06b6d4';
        c.beginPath();
        c.moveTo(x,     top + 3);
        c.lineTo(x - 5, top - 6);
        c.lineTo(x + 5, top - 6);
        c.closePath();
        c.fill();

        c.fillStyle  = '#06b6d4';
        c.font       = 'bold 9px sans-serif';
        c.textAlign  = 'center';
        c.fillText('Achat', x, top - 9);
        c.restore();
      });
    }
  };

  new Chart(ctx, {
    type: 'line',
    plugins: [buyPinPlugin],
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
        tooltip: {
          callbacks: {
            label(c) {
              let line = ' PA : ' + c.raw.toFixed(2) + ' MAD';
              const m  = buyMarkers.find(b => b.date === labels[c.dataIndex]);
              if (m) line += '   •   Achat ' + m.quantity + ' × ' + m.price.toFixed(2) + ' MAD';
              return line;
            }
          }
        }
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
