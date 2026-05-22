<?php
/**
 * debug_sync.php — Flask sync diagnostic tool
 * Visit this page to see exactly why "Sync marché" is failing.
 * DELETE or restrict access to this file in production.
 */
session_start();
require_once 'config/config.php';
require_once 'core/auth.php';
requireLogin();

$projectRoot = __DIR__;
$venvPython  = $projectRoot . '/scrapping/.venv_linux/bin/python';
$scriptPath  = $projectRoot . '/scrapping/GETjson.py';
$logFile     = sys_get_temp_dir() . '/myinterpreter_flask.log';
$pidFile     = sys_get_temp_dir() . '/myinterpreter_flask.pid';

// ── Helper: run a command synchronously, capture output ──
function run(string $cmd): array {
    $out = []; $code = -1;
    exec($cmd . ' 2>&1', $out, $code);
    return ['output' => implode("\n", $out), 'code' => $code];
}

// ── Helper: TCP port check (works even if allow_url_fopen=Off) ──
function portOpen(string $host, int $port, float $timeout = 1.5): bool {
    $sock = @fsockopen($host, $port, $errno, $errstr, $timeout);
    if ($sock) { fclose($sock); return true; }
    return false;
}

// ── Helper: HTTP GET bypassing allow_url_fopen ───────────
function httpGet(string $url, int $timeout = 10): ?string {
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER=>true,
            CURLOPT_TIMEOUT=>$timeout, CURLOPT_CONNECTTIMEOUT=>3]);
        $body = curl_exec($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        return ($body !== false && $code >= 200 && $code < 300) ? $body : null;
    }
    $parts = parse_url($url);
    $host = $parts['host'] ?? '127.0.0.1';
    $port = (int)($parts['port'] ?? 80);
    $path = ($parts['path'] ?? '/') . (isset($parts['query']) ? '?'.$parts['query'] : '');
    $sock = @fsockopen($host, $port, $errno, $errstr, 3);
    if (!$sock) return null;
    stream_set_timeout($sock, $timeout);
    fwrite($sock, "GET {$path} HTTP/1.0\r\nHost: {$host}\r\nConnection: close\r\n\r\n");
    $raw = ''; while (!feof($sock)) { $raw .= fread($sock, 8192); }
    fclose($sock);
    $sep = strpos($raw, "\r\n\r\n");
    return $sep !== false ? substr($raw, $sep + 4) : $raw;
}

// ─────────────────────────────────────────────────────────
// Run all checks
// ─────────────────────────────────────────────────────────
$checks = [];

// 1. PHP exec() available
$disabledFns = array_map('trim', explode(',', ini_get('disable_functions') ?: ''));
$execOk = !in_array('exec', $disabledFns);
$checks[] = [
    'label' => 'PHP exec() activé',
    'ok'    => $execOk,
    'info'  => $execOk ? 'exec() est disponible.' : 'exec() est dans disable_functions dans php.ini — PHP ne peut pas démarrer de processus.',
];

// 2. allow_url_fopen (used by file_get_contents for HTTP)
$urlFopen = (bool) ini_get('allow_url_fopen');
$checks[] = [
    'label' => 'allow_url_fopen activé',
    'ok'    => $urlFopen,
    'warn'  => !$urlFopen,
    'info'  => $urlFopen
        ? 'file_get_contents() peut accéder aux URLs HTTP.'
        : '⚠ allow_url_fopen=Off — c\'est probablement la cause de votre erreur "Requête Flask échouée". Le sync utilise désormais cURL/fsockopen pour contourner cela.',
];

// 3. GETjson.py exists
$scriptExists = file_exists($scriptPath);
$checks[] = [
    'label' => 'GETjson.py trouvé',
    'ok'    => $scriptExists,
    'info'  => $scriptExists
        ? 'Chemin : ' . $scriptPath
        : 'Fichier introuvable : ' . $scriptPath . ' — déposez GETjson.py dans scrapping/',
];

// 4. venv Python exists
$venvExists = file_exists($venvPython);
$python     = $venvExists ? $venvPython : 'python3';
$checks[] = [
    'label' => 'venv Python trouvé (' . basename(dirname($venvPython, 2)) . ')',
    'ok'    => $venvExists,
    'warn'  => !$venvExists,
    'info'  => $venvExists
        ? 'Chemin : ' . $venvPython
        : 'Venv absent — utilisation de python3 système comme fallback.',
];

// 5. Python version
if ($execOk) {
    $pyVer = run($python . ' --version');
    $checks[] = [
        'label' => 'Python version',
        'ok'    => $pyVer['code'] === 0,
        'info'  => $pyVer['code'] === 0
            ? $pyVer['output'] . ' (binaire : ' . $python . ')'
            : 'Impossible d\'exécuter Python : ' . $pyVer['output'],
    ];

    // 6. Flask importable
    $flaskTest = run($python . ' -c "import flask; print(\'Flask \' + flask.__version__)"');
    $checks[] = [
        'label' => 'Flask importable',
        'ok'    => $flaskTest['code'] === 0,
        'info'  => $flaskTest['code'] === 0
            ? $flaskTest['output']
            : 'Import Flask échoué : ' . $flaskTest['output'] .
              "\n→ Activez le venv et exécutez : pip install flask",
    ];

    // 7. Syntax check GETjson.py
    if ($scriptExists) {
        $syntax = run($python . ' -m py_compile ' . escapeshellarg($scriptPath));
        $checks[] = [
            'label' => 'GETjson.py — syntaxe Python',
            'ok'    => $syntax['code'] === 0,
            'info'  => $syntax['code'] === 0
                ? 'Aucune erreur de syntaxe.'
                : 'Erreur de syntaxe : ' . $syntax['output'],
        ];
    }
} else {
    $checks[] = ['label' => 'Python / Flask (ignorés)', 'ok' => null,
                 'info'  => 'exec() désactivé — impossible de tester.'];
}

// 8. cURL available?
$curlOk = function_exists('curl_init');
$checks[] = [
    'label' => 'cURL disponible',
    'ok'    => $curlOk,
    'warn'  => !$curlOk,
    'info'  => $curlOk
        ? 'cURL est disponible — utilisé pour les requêtes HTTP vers Flask.'
        : 'cURL absent — fallback fsockopen utilisé (fonctionne quand même).',
];

// 9. If Flask is already up, test the actual API endpoint
if ($port5000OpenEarly = portOpen('127.0.0.1', 5000)) {
    $apiResp = httpGet('http://127.0.0.1:5000/api/get-stocks', 10);
    $checks[] = [
        'label' => 'Endpoint /api/get-stocks (Flask déjà actif)',
        'ok'    => $apiResp !== null,
        'info'  => $apiResp !== null
            ? 'Réponse reçue : ' . substr($apiResp, 0, 200)
            : 'Endpoint ne répond pas — vérifiez la route dans GETjson.py.',
    ];
}

// 8-real. Port 5000 already in use?
$port5000Open = portOpen('127.0.0.1', 5000);
$checks[] = [
    'label' => 'Port 5000',
    'ok'    => true,  // either state is informational
    'info'  => $port5000Open
        ? '✔ Port 5000 répond déjà — Flask est peut-être déjà lancé.'
        : 'Port 5000 libre — Flask pourra s\'y attacher.',
];

// 9. Last Python error log
$lastLog = '';
if (file_exists($logFile)) {
    $lastLog = trim(file_get_contents($logFile));
}

// 10. Last saved PID still alive?
$lastPid = 0; $pidAlive = false;
if (file_exists($pidFile)) {
    $lastPid = (int) trim(file_get_contents($pidFile));
    if ($lastPid > 0 && PHP_OS_FAMILY !== 'Windows') {
        exec("kill -0 {$lastPid} 2>&1", $_, $alive);
        $pidAlive = ($alive === 0);
    }
}

// 11. Quick live test: try to start Flask, wait 6 s, check port, kill
$liveResult = null;
if (isset($_POST['run_live_test']) && $execOk && $scriptExists && $venvExists) {
    csrf_verify();
    $tmpLog = sys_get_temp_dir() . '/myinterpreter_flask_test.log';
    @unlink($tmpLog);
    exec($python . ' ' . escapeshellarg($scriptPath) . ' > ' . escapeshellarg($tmpLog) . ' 2>&1 & echo $!', $testPidOut);
    $testPid = (int)($testPidOut[0] ?? 0);
    $started = false;
    for ($i = 0; $i < 12; $i++) {
        usleep(500_000);
        if (portOpen('127.0.0.1', 5000)) { $started = true; break; }
    }
    $testLog = file_exists($tmpLog) ? trim(file_get_contents($tmpLog)) : '(aucun output)';
    if ($testPid > 0) exec("kill {$testPid} 2>/dev/null");
    $liveResult = ['started' => $started, 'log' => $testLog, 'pid' => $testPid];
}
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>Debug — Flask Sync</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <style>
    .dbg-wrap { max-width: 820px; margin: 2rem auto; padding: 0 20px 60px; }
    .dbg-wrap h1 { font-family:var(--font-display);font-size:1.5rem;font-weight:800;margin-bottom:4px; }
    .dbg-wrap .sub { color:var(--text-mute);font-size:0.85rem;margin-bottom:2rem; }
    .check-row {
      display:flex; align-items:flex-start; gap:14px;
      padding:14px 18px; border-bottom:1px solid var(--border);
    }
    .check-row:last-child { border-bottom:none; }
    .check-icon { font-size:1rem; margin-top:2px; flex-shrink:0; width:20px; text-align:center; }
    .icon-ok   { color:var(--green); }
    .icon-fail { color:var(--rose); }
    .icon-warn { color:var(--amber); }
    .icon-info { color:var(--cyan); }
    .check-label { font-family:var(--font-display);font-weight:700;font-size:0.9rem;line-height:1.3; }
    .check-info  { font-size:0.82rem;color:var(--text-mute);margin-top:3px;white-space:pre-wrap;font-family:var(--font-mono); }
    .check-info.bad { color:var(--rose); }
    .log-box {
      background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius);
      padding:14px 16px;margin-top:8px;font-family:var(--font-mono);font-size:0.78rem;
      color:var(--text-dim);white-space:pre-wrap;max-height:200px;overflow-y:auto;
    }
    .section-title { font-family:var(--font-display);font-size:0.72rem;font-weight:700;
      text-transform:uppercase;letter-spacing:0.12em;color:var(--text-mute);
      padding:10px 18px 6px;border-bottom:1px solid var(--border); }
  </style>
</head>
<body>
<div class="page">
  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Debug — Sync Flask</span>
    <div class="topbar-spacer"></div>
    <a href="portfolio.php" class="btn btn-ghost btn-sm"><i class="fas fa-arrow-left"></i> Portefeuille</a>
  </nav>

  <div class="dbg-wrap animate-up">
    <h1><i class="fas fa-bug t-amber me-2"></i>Diagnostic Flask Sync</h1>
    <p class="sub">Vérification automatique de tous les prérequis pour "Sync marché".</p>

    <!-- Static checks -->
    <div class="card-glass mb-4">
      <div class="section-title">Vérifications statiques</div>
      <?php foreach ($checks as $c):
        if ($c['ok'] === true)       { $cls = 'icon-ok';   $icon = 'fa-check-circle'; }
        elseif ($c['ok'] === false)  { $cls = 'icon-fail'; $icon = 'fa-times-circle'; }
        elseif (!empty($c['warn']))  { $cls = 'icon-warn'; $icon = 'fa-exclamation-triangle'; }
        else                         { $cls = 'icon-info'; $icon = 'fa-info-circle'; }
        $badInfo = $c['ok'] === false;
      ?>
      <div class="check-row">
        <div class="check-icon <?= $cls ?>"><i class="fas <?= $icon ?>"></i></div>
        <div>
          <div class="check-label"><?= htmlspecialchars($c['label']) ?></div>
          <div class="check-info<?= $badInfo ? ' bad' : '' ?>"><?= htmlspecialchars($c['info']) ?></div>
        </div>
      </div>
      <?php endforeach; ?>
    </div>

    <!-- Last log -->
    <?php if ($lastLog): ?>
    <div class="card-glass mb-4">
      <div class="section-title">Dernière sortie Python (<?= basename($logFile) ?>)</div>
      <div class="p-3">
        <div class="log-box"><?= htmlspecialchars($lastLog) ?></div>
      </div>
    </div>
    <?php endif; ?>

    <!-- PID status -->
    <?php if ($lastPid): ?>
    <div class="card-glass mb-4">
      <div class="section-title">PID enregistré</div>
      <div class="check-row">
        <div class="check-icon <?= $pidAlive ? 'icon-ok' : 'icon-warn' ?>">
          <i class="fas <?= $pidAlive ? 'fa-circle' : 'fa-ghost' ?>"></i>
        </div>
        <div>
          <div class="check-label">PID <?= $lastPid ?></div>
          <div class="check-info"><?= $pidAlive ? 'Processus toujours en vie.' : 'Processus terminé (PID mort).' ?></div>
        </div>
      </div>
    </div>
    <?php endif; ?>

    <!-- Live test -->
    <?php if ($liveResult !== null): ?>
    <div class="card-glass mb-4">
      <div class="section-title">Résultat du test en direct</div>
      <div class="check-row">
        <div class="check-icon <?= $liveResult['started'] ? 'icon-ok' : 'icon-fail' ?>">
          <i class="fas <?= $liveResult['started'] ? 'fa-check-circle' : 'fa-times-circle' ?>"></i>
        </div>
        <div style="width:100%">
          <div class="check-label">
            <?= $liveResult['started'] ? 'Flask a démarré avec succès ✔' : 'Flask n\'a pas démarré ✗' ?>
          </div>
          <div class="check-info"><?= $liveResult['started'] ? 'Port 5000 a répondu dans les délais.' : 'Port 5000 n\'a pas répondu après 6 s.' ?></div>
          <?php if ($liveResult['log']): ?>
          <div class="log-box mt-2"><?= htmlspecialchars($liveResult['log']) ?></div>
          <?php endif; ?>
        </div>
      </div>
    </div>
    <?php endif; ?>

    <!-- Action buttons -->
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <?php if ($execOk && $scriptExists): ?>
      <form method="POST" action="" data-loading>
        <?= csrf_field() ?>
        <button type="submit" name="run_live_test" class="btn btn-amber"
                style="background:linear-gradient(135deg,#d97706,#f59e0b);color:#000"
                data-loading-text="Test en cours (6 s)…">
          <i class="fas fa-play"></i> Lancer le test en direct
        </button>
      </form>
      <?php endif; ?>
      <a href="portfolio.php" class="btn btn-ghost"><i class="fas fa-arrow-left"></i> Retour</a>
    </div>

    <div class="alert alert-warn mt-4" style="font-size:0.82rem">
      <i class="fas fa-trash me-2"></i>
      <strong>Supprimez ce fichier</strong> (<code>debug_sync.php</code>) une fois le problème résolu.
    </div>

  </div>
</div>
<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
</body>
</html>
