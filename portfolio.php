<?php
ob_start();
session_start();
require_once 'config/config.php';
require_once 'core/auth.php';
require_once 'core/Database.php';
requireLogin();

$db  = (new Database())->opendb();
$uid = (int) $_SESSION['ID_USER'];

$flash = [];

// ─── Add buy ──────────────────────────────────────────────
if (isset($_POST['add_buy'])) {
    csrf_verify();
    $name   = trim($_POST['NAME']     ?? '');
    $number = (int)   ($_POST['NUMBER']    ?? 0);
    $price  = (float) ($_POST['PRIX_ACHAT']?? 0);
    if ($name && $number > 0 && $price > 0) {
        $db->prepare('INSERT INTO ACHATS(`DATE`,C_NAME,`NUMBER`,PRIX_ACHAT,ID_USER) VALUES(CURRENT_DATE,?,?,?,?)')
           ->execute([$name,$number,$price,$uid]);
        $check = $db->prepare('SELECT * FROM PORTEFEUILLE WHERE C_NAME=? AND ID_USER=?');
        $check->execute([$name,$uid]);
        if ($check->fetch()) {
            $db->prepare('UPDATE PORTEFEUILLE SET `NUMBER`=`NUMBER`+?,MONTANT=MONTANT+? WHERE C_NAME=? AND ID_USER=?')
               ->execute([$number,$price*$number,$name,$uid]);
        } else {
            $db->prepare('INSERT INTO PORTEFEUILLE(C_NAME,`NUMBER`,MONTANT,ID_USER) VALUES(?,?,?,?)')
               ->execute([$name,$number,$price*$number,$uid]);
        }
        $flash[] = ['type'=>'success','msg'=>"Achat de {$number} × {$name} enregistré."];
    }
}

// ─── Add sell ─────────────────────────────────────────────
if (isset($_POST['add_sell'])) {
    csrf_verify();
    $name   = trim($_POST['NAME2']     ?? '');
    $number = (int)   ($_POST['NUMBER2']   ?? 0);
    $price  = (float) ($_POST['PRIX_VENTE']?? 0);
    if ($name && $number > 0 && $price > 0) {
        $check = $db->prepare('SELECT `NUMBER`,MONTANT FROM PORTEFEUILLE WHERE C_NAME=? AND ID_USER=?');
        $check->execute([$name,$uid]);
        $current = $check->fetch();
        if ($current && $number <= (int)$current['NUMBER']) {
            $db->prepare('INSERT INTO VENTES(`DATE`,C_NAME,`NUMBER`,PRIX_VENTE,ID_USER) VALUES(CURRENT_DATE,?,?,?,?)')
               ->execute([$name,$number,$price,$uid]);
            if ($number == (int)$current['NUMBER']) {
                $db->prepare('DELETE FROM PORTEFEUILLE WHERE C_NAME=? AND ID_USER=?')->execute([$name,$uid]);
            } else {
                $avg  = $current['MONTANT'] / $current['NUMBER'];
                $db->prepare('UPDATE PORTEFEUILLE SET `NUMBER`=`NUMBER`-?,MONTANT=MONTANT-? WHERE C_NAME=? AND ID_USER=?')
                   ->execute([$number,$avg*$number,$name,$uid]);
            }
            $flash[] = ['type'=>'success','msg'=>"Vente de {$number} × {$name} enregistrée."];
            header('Location: portfolio.php'); exit();
        } else {
            $flash[] = ['type'=>'error','msg'=>'Quantité insuffisante en portefeuille.'];
        }
    }
}

// ─── Save portfolio snapshot to BENEFITS ─────────────────
if (isset($_POST['save_snapshot'])) {
    csrf_verify();
    // Only save once per calendar day
    $lastDate = $db->prepare('SELECT `DATE` FROM BENEFITS WHERE ID_USER=? ORDER BY `DATE` DESC LIMIT 1');
    $lastDate->execute([$uid]);
    $lastSaved = $lastDate->fetchColumn();
    $today     = date('Y-m-d');
    if ($lastSaved !== $today) {
        $snapValue = (float) ($_POST['snapshot_value'] ?? 0);
        $db->prepare('INSERT INTO BENEFITS(`DATE`, VALUE, ID_USER) VALUES (CURRENT_DATE, ?, ?)')
           ->execute([$snapValue, $uid]);
        $flash[] = ['type' => 'success', 'msg' => 'Snapshot P&L enregistré pour aujourd\'hui.'];
    } else {
        $flash[] = ['type' => 'warn', 'msg' => 'Un snapshot a déjà été enregistré aujourd\'hui.'];
    }
}

// ─── HTTP helpers that bypass allow_url_fopen restrictions ───────────────────
// Uses cURL when available, falls back to raw fsockopen — never needs
// allow_url_fopen=On, unlike file_get_contents(http://...).

function flaskPortOpen(string $host = '127.0.0.1', int $port = 5000, float $timeout = 1.5): bool {
    $sock = @fsockopen($host, $port, $errno, $errstr, $timeout);
    if ($sock) { fclose($sock); return true; }
    return false;
}

function httpGet(string $url, int $timeout = 30): ?string {
    // ── cURL (preferred) ──────────────────────────────────
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => $timeout,
            CURLOPT_CONNECTTIMEOUT => 5,
            CURLOPT_FOLLOWLOCATION => true,
        ]);
        $body = curl_exec($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        return ($body !== false && $code >= 200 && $code < 300) ? $body : null;
    }

    // ── Raw fsockopen fallback ────────────────────────────
    $parts = parse_url($url);
    $host  = $parts['host'] ?? '127.0.0.1';
    $port  = (int) ($parts['port'] ?? 80);
    $path  = ($parts['path'] ?? '/') .
             (isset($parts['query']) ? '?' . $parts['query'] : '');

    $sock = @fsockopen($host, $port, $errno, $errstr, 5);
    if (!$sock) return null;

    stream_set_timeout($sock, $timeout);
    fwrite($sock, "GET {$path} HTTP/1.0
Host: {$host}
Connection: close

");

    $raw = '';
    while (!feof($sock)) { $raw .= fread($sock, 8192); }
    fclose($sock);

    // Strip HTTP response headers, return body only
    $sep = strpos($raw, "\r\n\r\n");
    return $sep !== false ? substr($raw, $sep + 4) : $raw;
}

// ─── Sync market data: auto-start Flask, call API, then stop Flask ───────────
if (isset($_POST['sync_market'])) {
    csrf_verify();

    $flaskBase  = 'http://127.0.0.1:5000';
    $flaskApi   = $flaskBase . '/api/get-stocks';
    $scriptPath = __DIR__ . '/scrapping/GETjson.py';  // user drops file here
    $pidFile    = sys_get_temp_dir() . '/myinterpreter_flask.pid';
    // 1. Check if Flask is already running
    $alreadyUp   = flaskPortOpen();
    $weStartedIt = false;

    // 2. If not running, start GETjson.py in the background
    if (!$alreadyUp) {
        if (!file_exists($scriptPath)) {
            $flash[] = ['type' => 'warn',
                'msg' => 'GETjson.py introuvable dans scrapping/. Déposez le fichier et réessayez.'];
        } else {
            // Use the project's own venv; fall back to system python3 / python
            $venvPython = __DIR__ . '/scrapping/.venv_linux/bin/python';
            if (file_exists($venvPython)) {
                $python = $venvPython;
            } else {
                exec('python3 --version 2>&1', $_, $pyCode);
                $python = ($pyCode === 0) ? 'python3' : 'python';
            }
            $real = realpath($scriptPath);

            if (PHP_OS_FAMILY === 'Windows') {
                // wmic lets us capture the PID of the spawned process
                $wmicCmd = 'wmic process call create ' .
                           '"cmd /c ' . $python . ' "' . str_replace('"', '\\"', $real) . '"' . '" 2>NUL';
                exec($wmicCmd, $wmicOut);
                foreach ($wmicOut as $line) {
                    if (preg_match('/ProcessId\s*=\s*(\d+)/i', $line, $m)) {
                        file_put_contents($pidFile, trim($m[1]));
                        break;
                    }
                }
            } else {
                // Linux/macOS: run in background, capture PID via $!
                $logFile = sys_get_temp_dir() . '/myinterpreter_flask.log';
                exec($python . ' ' . escapeshellarg($real) . ' > ' . escapeshellarg($logFile) . ' 2>&1 & echo $!', $pidOut);
                if (!empty($pidOut[0])) {
                    file_put_contents($pidFile, trim($pidOut[0]));
                }
            }
            $weStartedIt = true;

            // 3. Poll until Flask responds (max 10 s, every 0.5 s)
            $ready = false;
            for ($i = 0; $i < 20; $i++) {
                usleep(500_000);
                if (flaskPortOpen()) {
                    $ready = true;
                    break;
                }
            }
            if (!$ready) {
                $pythonLog = (!empty($logFile) && file_exists($logFile))
                    ? trim(file_get_contents($logFile)) : '';
                $errDetail = $pythonLog
                    ? '<br><code style="font-size:0.8rem">' . htmlspecialchars(substr($pythonLog, 0, 400)) . '</code>'
                    : 'Consultez <a href="debug_sync.php" class="t-cyan">debug_sync.php</a> pour diagnostiquer.';
                $flash[] = ['type' => 'error',
                    'msg' => 'Flask n\'a pas démarré dans les délais. ' . $errDetail];
                $weStartedIt = false;
            }
        }
    }

    // 4. Call the sync endpoint — verify result in the DB ourselves
    if ($alreadyUp || $weStartedIt) {

        // Row counts BEFORE the call so we can compare after
        $rowsBefore = (int) $db->query('SELECT COUNT(*) FROM `DATA`')->fetchColumn();

        $response = httpGet($flaskApi, 30);

        if ($response === null) {
            $flash[] = ['type' => 'error',
                'msg' => 'Requête Flask échouée sur ' . $flaskApi .
                         '<br><small class="muted">Flask tourne mais n\'a pas répondu. ' .
                         'Vérifiez que la route <code>/api/get-stocks</code> existe dans GETjson.py.</small>'];
        } else {
            // Row counts AFTER — this is ground truth regardless of what Flask says
            $rowsAfter = (int) $db->query('SELECT COUNT(*) FROM `DATA`')->fetchColumn();
            $newRows   = $rowsAfter - $rowsBefore;

            $result  = json_decode($response, true);
            $flaskMsg = htmlspecialchars($result['message'] ?? '—');

            // Build full raw response for transparency
            $rawPreview = htmlspecialchars(substr($response, 0, 300));

            if ($newRows > 0) {
                $flash[] = ['type' => 'success',
                    'msg' => "<i class='fas fa-check-circle me-1'></i> "
                           . "<strong>{$newRows} nouveau(x) snapshot(s)</strong> insérés dans DATA. "
                           . "Flask : <em>{$flaskMsg}</em>"];
            } else {
                // Flask said OK but nothing landed in DB
                $flash[] = ['type' => 'warn',
                    'msg' => "<i class='fas fa-exclamation-triangle me-1'></i>"
                           . "<strong>Flask a répondu mais aucune ligne n'a été insérée dans DATA.</strong><br>"
                           . "Message Flask : <em>{$flaskMsg}</em><br>"
                           . "<small>Réponse brute : <code>{$rawPreview}</code></small><br>"
                           . "<small>Causes possibles :<br>"
                           . "① Flask se connecte à une DB différente (vérifiez les credentials dans GETjson.py)<br>"
                           . "② La table <code>DATA</code> a un nom différent dans GETjson.py<br>"
                           . "③ Flask fait un INSERT mais gère silencieusement l'erreur<br>"
                           . "④ GETjson.py n'insère pas dans <code>DATA</code> — il met à jour une autre table</small>"];
            }
        }
    }

    // 5. Stop Flask if we were the ones who started it
    if ($weStartedIt && file_exists($pidFile)) {
        $pid = (int) trim(file_get_contents($pidFile));
        if ($pid > 0) {
            if (PHP_OS_FAMILY === 'Windows') {
                exec("taskkill /F /PID {$pid} 2>NUL");
            } else {
                exec("kill {$pid} 2>/dev/null");
            }
        }
        @unlink($pidFile);
    }
}

// ─── Load portfolio data ─────────────────────────────────
$stmtPf  = $db->prepare('SELECT * FROM PORTEFEUILLE WHERE ID_USER=?');
$stmtPf->execute([$uid]);
$holdings = $stmtPf->fetchAll();

$stmtPA = $db->prepare('SELECT PA FROM `DATA` WHERE C_NAME=? ORDER BY DATE DESC LIMIT 1');

$chartNames = []; $chartValues = []; $chartBuys = [];
$totalCurrentVal = 0.0; $totalBuyVal = 0.0;

foreach ($holdings as $h) {
    $stmtPA->execute([$h['C_NAME']]);
    $row    = $stmtPA->fetch();
    $curVal = $row ? $h['NUMBER'] * (float)$row['PA'] : 0;
    $buyVal = (float) $h['MONTANT'];
    $chartNames[]  = $h['C_NAME'];
    $chartValues[] = round($curVal, 2);
    $chartBuys[]   = round($buyVal, 2);
    $totalCurrentVal += $curVal;
    $totalBuyVal     += $buyVal;
    if (!$row) {
        $flash[] = ['type' => 'warn', 'msg' => "Prix introuvable pour « {$h['C_NAME']} » — lancez une sync ou ajoutez un snapshot via Update Stock."];
    }
}

$difference  = $totalBuyVal - $totalCurrentVal;  // negative = gain
$diffDisplay = $difference * (-1);               // positive = gain

// Last snapshot / sync dates
$lastSnap = $db->prepare('SELECT `DATE` FROM BENEFITS WHERE ID_USER=? ORDER BY `DATE` DESC LIMIT 1');
$lastSnap->execute([$uid]);
$lastSnapDate = $lastSnap->fetchColumn();

$lastSync = $db->query('SELECT `DATE` FROM `DATA` ORDER BY `DATE` DESC LIMIT 1')->fetchColumn();

// Earnings history
$benStmt = $db->prepare('SELECT `DATE`,VALUE FROM BENEFITS WHERE ID_USER=? ORDER BY `DATE` DESC');
$benStmt->execute([$uid]);
$earnings = $benStmt->fetchAll();

// Companies list for datalist
$allCompanies = $db->query('SELECT NAME FROM COMPANY ORDER BY NAME ASC')->fetchAll(PDO::FETCH_COLUMN);

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

    <!-- Sync row -->
    <div class="sync-row">
      <span class="sync-label"><i class="fas fa-save me-1"></i>Dernier snapshot :</span>
      <span class="sync-value"><?= $lastSnapDate ?: '—' ?></span>
      <div class="divider"></div>
      <span class="sync-label"><i class="fas fa-sync me-1"></i>Dernier sync :</span>
      <span class="sync-value"><?= $lastSync ?: '—' ?></span>
      <div class="topbar-spacer"></div>
      <form method="POST" style="display:inline">
        <?= csrf_field() ?>
        <button type="submit" name="sync_market" class="btn btn-ghost btn-sm">
          <i class="fas fa-cloud-download-alt"></i> Sync marché
        </button>
      </form>
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
          </tr></thead>
          <tbody>
            <?php foreach ($holdings as $i => $h):
              $cur = $chartValues[$i];
              $buy = $chartBuys[$i];
              $pnl = $cur - $buy;
              $cls = $pnl > 0 ? 'pos' : ($pnl < 0 ? 'neg' : 'zero');
            ?>
            <tr>
              <td class="label-cell"><?= htmlspecialchars($h['C_NAME']) ?></td>
              <td class="num mono"><?= (int)$h['NUMBER'] ?></td>
              <td class="num mono"><?= number_format($buy, 2) ?></td>
              <td class="num mono"><?= $cur > 0 ? number_format($cur, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono <?= $cls ?>"><?= $cur > 0 ? ($pnl>=0?'+':'') . number_format($pnl,2) : '<span class="muted">—</span>' ?></td>
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
</script>
</body>
</html>
