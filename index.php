<?php
ob_start();
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/auth.php';

// ─── Restore session from cookie ─────────────────────────
if (!isset($_SESSION['logged_in']) && isset($_COOKIE['aw_session'])) {
    $_SESSION['aw_cookie'] = $_COOKIE['aw_session'];
    $me = aw_get('/account', $_SESSION['aw_cookie']);
    if (isset($me['body']['$id'])) {
        $_SESSION['logged_in'] = true;
        $_SESSION['USER_ID']   = $me['body']['$id'];
        $_SESSION['USER_EMAIL']= $me['body']['email'] ?? '';
        // Slide the cookie forward another year on each restore
        setcookie('aw_session', $_COOKIE['aw_session'], time() + 86400 * 365, '/', '', false, true);
    } else {
        setcookie('aw_session', '', time() - 3600, '/', '', false, true);
        unset($_SESSION['aw_cookie']);
    }
}

// ─── Logout ───────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['logout'])) {
    if (!empty($_SESSION['aw_cookie'])) {
        aw_delete('/account/sessions/current', $_SESSION['aw_cookie']);
    }
    session_destroy();
    setcookie('aw_session', '', time() - 3600, '/', '', false, true);
    header('Location: ' . BASE_URL . '/index.php');
    exit();
}

// ─── Sign up ──────────────────────────────────────────────
$loginError = '';
$isSignUp   = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['signup_form'])) {
    $isSignUp = true;
    $email    = trim($_POST['email']    ?? '');
    $password = $_POST['password']      ?? '';
    $name     = trim($_POST['name']     ?? '');
    $res = aw_post('/account', [
        'userId'   => 'unique()',
        'email'    => $email,
        'password' => $password,
        'name'     => $name ?: null,
    ]);
    if (isset($res['body']['$id'])) {
        $_POST['login_form'] = '1';
        $_POST['stay'] = $_POST['stay'] ?? '';
        $loginSignup = true;
    } else {
        $loginError = $res['body']['message'] ?? 'Inscription échouée.';
    }
}

// ─── Login ────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST' && (isset($_POST['login_form']) || isset($loginSignup))) {
    $email    = trim($_POST['email']    ?? '');
    $password = $_POST['password']      ?? '';
    $stay     = !empty($_POST['stay']);
    $res = aw_post('/account/sessions/email', ['email' => $email, 'password' => $password]);
    if (isset($res['body']['$id'])) {
        $_SESSION['logged_in']  = true;
        $_SESSION['USER_ID']    = $res['body']['userId'];
        $_SESSION['USER_EMAIL'] = $email;
        $_SESSION['aw_cookie']  = $res['cookies'];
        setcookie('aw_session', $res['cookies'], time() + 86400 * 365, '/', '', false, true);
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    } else {
        $loginError = $res['body']['message'] ?? 'Identifiants incorrects.';
    }
}

$isLoggedIn = isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true;

function _live_market_status(): array {
    $payload = json_encode(['ACTIONS' => [[
        'ACTION' => ['NAME' => 'MARKET-STATUS', 'TYPE' => 'SELECT', 'VALUE' => 'MARKET-STATUS'],
        'PARAMS' => [
            ['NAME' => 'Lang_',       'TYPE' => 'S', 'VALUE' => 'XX'],
            ['NAME' => 'Espace_',     'TYPE' => 'I', 'VALUE' => 1],
            ['NAME' => 'IdPartener_', 'TYPE' => 'I', 'VALUE' => 1],
            ['NAME' => 'NumSeq_',     'TYPE' => 'I', 'VALUE' => 0],
        ],
    ]]]);
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => 'https://www.cdgcapitalbourse.ma/api/',
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 3,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            'Origin: https://www.cdgcapitalbourse.ma',
            'Referer: https://www.cdgcapitalbourse.ma/',
        ],
    ]);
    $body = curl_exec($ch);
    curl_close($ch);
    if (!$body) return [];
    $data = json_decode($body, true);
    return $data[0]['MARKET-STATUS']['Data'][0] ?? [];
}

// ─── Dashboard data ───────────────────────────────────────
$companyCount   = 0;
$snapshotDays   = 0;
$totalDataRows  = 0;
$oldestDate     = null;
$newestDate     = null;
$avgPER         = null;
$allGreen       = 0;
$totalCompanies = 0;
$masiSeries     = [];
$masiLast       = null;
$masiChange     = null;
$masiChangePct  = null;
$topGainers     = [];
$topLosers      = [];
$topScored      = [];
$screenerCount  = null;
$isMarketOpen   = false;

if ($isLoggedIn) {
    try {
        $docs = aw_list_docs('data', [q_order_desc('date'), q_limit(500)]);

        $latest = []; $prev = []; $byDate = [];
        foreach ($docs as $d) {
            $n  = trim($d['c_name'] ?? '');
            $pa = (float)($d['pa'] ?? 0);
            $dt = $d['date'] ?? '';
            if (!$n || !$pa) continue;
            if (!isset($latest[$n])) { $latest[$n] = $d; }
            elseif (!isset($prev[$n])) { $prev[$n] = $d; }
            if ($dt) { $byDate[$dt][] = $pa; }
        }

        $companyCount = count($latest);

        // Total rows and date span from the data collection
        $totalDataRows = aw_count_docs('data');
        $oldestDoc = aw_list_docs('data', [q_order_asc('date'), q_limit(1)]);
        $oldestDate = !empty($oldestDoc) ? substr($oldestDoc[0]['date'] ?? '', 0, 10) : null;
        $newestDoc  = aw_list_docs('data', [q_order_desc('date'), q_limit(1)]);
        $newestDate = !empty($newestDoc) ? substr($newestDoc[0]['date'] ?? '', 0, 10) : null;
        $snapshotDays = ($oldestDate && $newestDate)
            ? (int)round((strtotime($newestDate) - strtotime($oldestDate)) / 86400)
            : 0;

        // MASI chart: fetch up to 5Y of daily docs
        $masiAllDocs = [];
        $masiOffset  = 0;
        $fiveYearsAgo = date('Y-m-d', strtotime('-5 years')) . 'T00:00:00.000+00:00';
        do {
            $page = aw_list_docs('data', [
                q_equal('c_name', 'MASI'),
                q_greater_equal('date', $fiveYearsAgo),
                q_order_desc('date'),
                q_limit(500),
                q_offset($masiOffset),
            ]);
            $masiAllDocs = array_merge($masiAllDocs, $page);
            $masiOffset += 500;
        } while (count($page) === 500);

        // Group by day, keep most recent per day, sort ascending
        $masiByDay = [];
        foreach ($masiAllDocs as $d) {
            $day = substr($d['date'] ?? '', 0, 10);
            if ($day && !isset($masiByDay[$day])) {
                $masiByDay[$day] = $d;
            }
        }
        ksort($masiByDay);

        // Build full series with dates for JS period filtering
        $masiFullSeries = [];
        foreach ($masiByDay as $day => $d) {
            $masiFullSeries[] = ['d' => $day, 'v' => round((float)($d['pa'] ?? 0), 2)];
        }

        if (!empty($masiFullSeries)) {
            $latest        = end($masiFullSeries);
            $masiLast      = $latest['v'];
            // variation vs previous day
            $prev          = count($masiFullSeries) >= 2 ? $masiFullSeries[count($masiFullSeries)-2]['v'] : $masiLast;
            $masiChange    = round($masiLast - $prev, 2);
            $masiChangePct = $prev ? round(($masiLast - $prev) / $prev * 100, 2) : null;
            // keep $masiSeries for legacy check (just need count >= 2)
            $masiSeries    = array_column($masiFullSeries, 'v');
        } else {
            // Fallback: avg PA across all stocks per day
            krsort($byDate);
            $byDate = array_slice($byDate, 0, 30, true);
            ksort($byDate);
            foreach ($byDate as $pas) {
                $masiSeries[] = round(array_sum($pas) / count($pas), 2);
                $masiFullSeries[] = ['d' => '', 'v' => end($masiSeries)];
            }
            if (count($masiSeries) >= 2) {
                $masiLast      = end($masiSeries);
                $masiFirst     = reset($masiSeries);
                $masiChange    = round($masiLast - $masiFirst, 2);
                $masiChangePct = $masiFirst ? round(($masiLast - $masiFirst) / $masiFirst * 100, 2) : null;
            }
        }

        // Score / PER stats
        function _dash_rate(string $ratio, float $val): string {
            if ($val == 0) return 'none';
            switch ($ratio) {
                case 'PER': return $val < PER_GREEN ? 'green' : ($val < PER_ORANGE ? 'orange' : 'red');
                case 'PEG': return ($val > 0 && $val < PEG_GREEN) ? 'green' : (($val > 0 && $val < PEG_ORANGE) ? 'orange' : 'red');
                case 'PR':  return $val < PR_GREEN  ? 'green' : ($val < PR_ORANGE  ? 'orange' : 'red');
                case 'PB':  return $val < PB_GREEN  ? 'green' : ($val < PB_ORANGE  ? 'orange' : 'red');
            }
            return 'none';
        }
        function _dash_abbr(string $name): string {
            $w = preg_split('/\s+/', strtoupper(trim($name)));
            if (count($w) >= 3) return $w[0][0] . $w[1][0] . $w[2][0];
            if (count($w) === 2) return substr($w[0], 0, 2) . $w[1][0];
            return substr($w[0] ?? $name, 0, 3);
        }

        $rows = [];
        foreach ($latest as $name => $r) {
            $per = (float)($r['per'] ?? 0);
            if ($per <= 0) continue;
            $colors = [
                'PER' => _dash_rate('PER', $per),
                'PEG' => _dash_rate('PEG', (float)($r['peg'] ?? 0)),
                'PR'  => _dash_rate('PR',  (float)($r['pr']  ?? 0)),
                'PB'  => _dash_rate('PB',  (float)($r['pb']  ?? 0)),
            ];
            $score  = count(array_filter($colors, fn($c) => $c === 'green'));
            $pa     = (float)($r['pa'] ?? 0);
            // Use API variation if stored, otherwise calculate from prev snapshot
            if (isset($r['variation'])) {
                $trend = (float)$r['variation'];
            } else {
                $prevPA = isset($prev[$name]) ? (float)($prev[$name]['pa'] ?? 0) : 0;
                $trend  = ($prevPA > 0) ? (($pa - $prevPA) / $prevPA * 100) : null;
            }
            $rows[] = [
                'name'  => $name,
                'abbr'  => $r['symbol'] ?? _dash_abbr($name),
                'PA'    => $pa,
                'PER'   => $per,
                'PEG'   => (float)($r['peg'] ?? 0),
                'PR'    => (float)($r['pr']  ?? 0),
                'PB'    => (float)($r['pb']  ?? 0),
                'score' => $score,
                'trend' => $trend,
            ];
        }

        $totalCompanies = count($rows);
        $screenerCount  = $totalCompanies ?: null;
        $avgPER         = $totalCompanies ? round(array_sum(array_column($rows, 'PER')) / $totalCompanies, 2) : null;
        $allGreen       = count(array_filter($rows, fn($r) => $r['score'] === 4));

        $withTrend = array_filter($rows, fn($r) => $r['trend'] !== null);
        $gainers = array_filter($withTrend, fn($r) => $r['trend'] > 0);
        $losers  = array_filter($withTrend, fn($r) => $r['trend'] < 0);
        usort($gainers, fn($a, $b) => $b['trend'] <=> $a['trend']);
        usort($losers,  fn($a, $b) => $a['trend'] <=> $b['trend']);
        $scored4 = array_filter($rows, fn($r) => $r['score'] === 4);
        usort($scored4, fn($a, $b) => $b['PER'] <=> $a['PER']);

        $topGainers = array_slice(array_values($gainers), 0, 6);
        $topLosers  = array_slice(array_values($losers),  0, 6);
        $topScored  = array_slice(array_values($scored4), 0, 6);

        // Market session status: live check (3s timeout), fallback to time-based
        $isMarketOpen  = false;
        $sessionLabel  = '';
        $mktStatus = _live_market_status();
        if (!empty($mktStatus)) {
            $isMarketOpen = ($mktStatus['Color'] ?? '') === 'G';
            $sessionLabel = $mktStatus['Statut'] ?? '';
        } else {
            $nowC = new DateTime('now', new DateTimeZone('Africa/Casablanca'));
            $tm   = (int)$nowC->format('G') * 60 + (int)$nowC->format('i');
            $dow  = (int)$nowC->format('N');
            $isMarketOpen = ($dow <= 5 && $tm >= 9*60+30 && $tm < 15*60+30);
        }

    } catch (Throwable $e) {
        // fail silently
    }
}

// Date/time for page header
$nowParis  = new DateTime('now', new DateTimeZone('Africa/Casablanca'));
$timeLabel = $nowParis->format('H:i');
$_days  = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
$_months = ['','janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
$dateLabel = $_days[(int)$nowParis->format('w')] . ' ' . $nowParis->format('j') . ' ' . $_months[(int)$nowParis->format('n')] . ' ' . $nowParis->format('Y');
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>myInterpreter | Tableau de bord</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=3" rel="stylesheet">
  <style>
    body { overflow-x: hidden; }
    /* Login card — shown when logged out */
    .login-wrap {
      display: flex; align-items: center; justify-content: center;
      min-height: calc(100vh - 60px);
    }
    .dash-card-inner {
      width: 100%; max-width: 420px;
      background: rgba(17,24,39,0.85);
      backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
      border: 1px solid var(--border-hi);
      border-radius: var(--radius-xl);
      padding: 2.5rem 2rem;
      box-shadow: 0 30px 60px rgba(0,0,0,0.5);
    }
    .logo-area { text-align: center; margin-bottom: 2rem; }
    .logo-icon {
      width: 60px; height: 60px; background: var(--cyan-dim);
      border: 1px solid rgba(34,211,238,0.25); border-radius: 18px;
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 1.5rem; color: var(--cyan); margin-bottom: 14px;
    }
    .logo-area h1 {
      font-family: var(--font-display); font-size: 1.7rem; font-weight: 800;
      background: linear-gradient(135deg, #fff 30%, #94a3b8);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0;
    }
    .nav-cards { display: flex; flex-direction: column; gap: 10px; }
    .nav-card {
      display: flex; align-items: center; gap: 14px;
      padding: 14px 18px; background: rgba(255,255,255,0.03);
      border: 1px solid var(--border); border-radius: var(--radius);
      text-decoration: none; color: var(--text-dim); transition: var(--transition);
      position: relative; overflow: hidden;
    }
    .nav-card::before {
      content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
      border-radius: 0 2px 2px 0; opacity: 0; transition: opacity 0.2s;
    }
    .nav-card:hover { background: rgba(255,255,255,0.07); border-color: var(--border-hi); color: var(--text); transform: translateX(4px); }
    .nav-card:hover::before { opacity: 1; }
    .nav-card.c1::before { background: var(--cyan); }
    .nav-card.c2::before { background: var(--emerald); }
    .nav-card.c3::before { background: var(--violet); }
    .nav-card.c4::before { background: var(--amber); }
    .nav-card .nav-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; }
    .nav-card .nav-icon.cyan    { background: var(--cyan-dim);    color: var(--cyan); }
    .nav-card .nav-icon.emerald { background: var(--emerald-dim); color: var(--emerald); }
    .nav-card .nav-icon.violet  { background: var(--violet-dim);  color: var(--violet); }
    .nav-card .nav-icon.amber   { background: var(--amber-dim);   color: var(--amber); }
    .nav-text strong { display: block; font-family: var(--font-display); font-size: 0.9rem; font-weight: 600; }
    .nav-text span { font-size: 0.78rem; color: var(--text-mute); }
    .nav-arrow { margin-left: auto; color: var(--text-mute); font-size: 0.8rem; }
    .modal-glass .modal-content {
      background: rgba(13,17,27,0.95); backdrop-filter: blur(24px);
      border: 1px solid var(--border-hi); border-radius: var(--radius-xl); color: var(--text);
    }
    .modal-glass .modal-header { border-bottom: 1px solid var(--border); }
    .modal-glass .modal-title  { font-family: var(--font-display); font-weight: 700; }
    .modal-glass .btn-close    { filter: invert(1) brightness(0.6); }
  </style>
</head>
<body>

<!-- Login Modal -->
<div class="modal fade modal-glass" id="loginModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <span class="modal-title"><i class="fas fa-lock me-2 t-cyan"></i>Connexion</span>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body p-4">
        <?php if ($loginError): ?>
          <div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i><?= htmlspecialchars($loginError) ?></div>
        <?php endif; ?>
        <div class="d-flex mb-4" style="gap:0;border:1px solid var(--border);border-radius:8px;overflow:hidden">
          <button type="button" id="tabLogin"  onclick="switchAuthTab('login')"
            class="btn btn-sm flex-fill" style="border-radius:0;border:none;padding:8px">
            <i class="fas fa-sign-in-alt me-1"></i>Connexion
          </button>
          <button type="button" id="tabSignup" onclick="switchAuthTab('signup')"
            class="btn btn-sm flex-fill" style="border-radius:0;border:none;border-left:1px solid var(--border);padding:8px">
            <i class="fas fa-user-plus me-1"></i>Inscription
          </button>
        </div>
        <form id="formLogin" method="POST" action="" data-loading>
          <?= csrf_field() ?>
          <input type="hidden" name="login_form" value="1">
          <div class="mb-3">
            <label class="form-label small muted">Email</label>
            <input type="email" name="email" class="form-control" placeholder="email@example.com" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label small muted">Mot de passe</label>
            <input type="password" name="password" class="form-control" placeholder="••••••••" required>
          </div>
          <div class="mb-4 d-flex align-items-center gap-2">
            <input type="checkbox" name="stay" id="stayLogin" value="1" checked
              style="width:16px;height:16px;accent-color:var(--cyan);cursor:pointer">
            <label for="stayLogin" class="mb-0 small muted" style="cursor:pointer">Rester connecté</label>
          </div>
          <button type="submit" name="login_form" class="btn btn-cyan w-100 btn-lg" data-loading-text="Vérification...">
            <i class="fas fa-sign-in-alt"></i> Se connecter
          </button>
        </form>
        <form id="formSignup" method="POST" action="" data-loading style="display:none">
          <?= csrf_field() ?>
          <input type="hidden" name="signup_form" value="1">
          <div class="mb-3">
            <label class="form-label small muted">Nom (optionnel)</label>
            <input type="text" name="name" class="form-control" placeholder="Votre nom">
          </div>
          <div class="mb-3">
            <label class="form-label small muted">Email</label>
            <input type="email" name="email" class="form-control" placeholder="email@example.com" required>
          </div>
          <div class="mb-3">
            <label class="form-label small muted">Mot de passe</label>
            <input type="password" name="password" class="form-control" placeholder="••••••••" minlength="8" required>
          </div>
          <div class="mb-4 d-flex align-items-center gap-2">
            <input type="checkbox" name="stay" id="staySignup" value="1" checked
              style="width:16px;height:16px;accent-color:var(--cyan);cursor:pointer">
            <label for="staySignup" class="mb-0 small muted" style="cursor:pointer">Rester connecté</label>
          </div>
          <button type="submit" name="signup_form" class="btn btn-cyan w-100 btn-lg" data-loading-text="Création...">
            <i class="fas fa-user-plus"></i> Créer un compte
          </button>
        </form>
      </div>
    </div>
  </div>
</div>

<div class="ambient" aria-hidden="true">
  <div class="halo halo-1"></div>
  <div class="halo halo-2"></div>
  <div class="halo halo-3"></div>
</div>

<div class="app">
  <?php include 'core/sidebar.php'; ?>

  <main class="main">

    <?php if (!$isLoggedIn): ?>
    <!-- ── Not logged in: login card ── -->
    <?php if (isset($_SESSION['noLogin'])): unset($_SESSION['noLogin']); ?>
      <div class="alert alert-warn" style="margin:16px 0 0"><i class="fas fa-lock me-2"></i>Connectez-vous pour accéder à cette page.</div>
    <?php endif; ?>
    <div class="login-wrap">
      <div class="dash-card-inner animate-up">
        <div class="logo-area">
          <div class="logo-icon"><i class="fas fa-chart-line"></i></div>
          <h1>myInterpreter</h1>
        </div>
        <div class="d-flex justify-content-center mb-4">
          <button type="button" class="btn btn-cyan" data-bs-toggle="modal" data-bs-target="#loginModal">
            <i class="fas fa-sign-in-alt"></i> Se connecter
          </button>
        </div>
        <div class="nav-cards">
          <a href="infoAction.php" class="nav-card c2">
            <div class="nav-icon emerald"><i class="fas fa-search"></i></div>
            <div class="nav-text">
              <strong>Consulter Action</strong>
              <span>Historique et ratios d'une société</span>
            </div>
            <i class="fas fa-chevron-right nav-arrow"></i>
          </a>
          <a href="screener.php" class="nav-card c4">
            <div class="nav-icon amber"><i class="fas fa-filter"></i></div>
            <div class="nav-text">
              <strong>Stock Screener</strong>
              <span>Filtrer par PER, score et ratios</span>
            </div>
            <i class="fas fa-chevron-right nav-arrow"></i>
          </a>
        </div>
      </div>
    </div>

    <?php else: ?>
    <!-- ── Dashboard ── -->

    <!-- Page head -->
    <div class="page-head">
      <div>
        <div class="eyebrow"><?= htmlspecialchars(ucfirst($dateLabel)) ?> · <?= $timeLabel ?></div>
        <h1 class="page-title">Tableau de bord</h1>
      </div>
      <div class="pill-bar">
        <a href="infoAction.php" class="search-pill" style="text-decoration:none;cursor:pointer">
          <span>⌕</span>
          <span>Chercher une société…</span>
        </a>
        <?php if ($isMarketOpen): ?>
          <div class="live-pill"><span class="live-dot"></span><?= htmlspecialchars($sessionLabel ?: 'Séance ouverte') ?></div>
        <?php else: ?>
          <div class="closed-pill"><span style="width:7px;height:7px;border-radius:50%;background:var(--neg);display:inline-block"></span><?= htmlspecialchars($sessionLabel ?: 'Séance fermée') ?></div>
        <?php endif; ?>
      </div>
    </div>

    <!-- Metrics -->
    <section class="metrics">
      <div class="metric">
        <div class="glow cyan"></div>
        <div class="m-label">Sociétés suivies</div>
        <div class="m-val"><?= (int)$companyCount ?></div>
        <div class="m-delta"><?= (int)$totalCompanies ?> avec ratios</div>
      </div>
      <div class="metric">
        <div class="glow purple"></div>
        <div class="m-label">Historique de données</div>
        <div class="m-val"><?= (int)round($snapshotDays / 365, 1) ?> <span class="unit">ans</span></div>
        <div class="m-delta"><?= number_format($totalDataRows, 0, ',', ' ') ?> entrées · <?= $oldestDate ? substr($oldestDate, 0, 7) : '—' ?> → <?= $newestDate ? substr($newestDate, 0, 7) : '—' ?></div>
      </div>
      <div class="metric">
        <div class="glow pink"></div>
        <div class="m-label">PER moyen</div>
        <div class="m-val"><?= $avgPER !== null ? number_format($avgPER, 2, ',', ' ') : '—' ?></div>
        <div class="m-delta">sur <?= (int)$totalCompanies ?> sociétés</div>
      </div>
      <div class="metric">
        <div class="glow green"></div>
        <div class="m-label">Score 4/4</div>
        <div class="m-val<?= $allGreen > 0 ? ' pos' : '' ?>"><?= (int)$allGreen ?></div>
        <div class="m-delta<?= $allGreen > 0 ? ' pos' : '' ?>">● <?= $allGreen > 0 ? 'tous verts' : 'aucun' ?></div>
      </div>
    </section>

    <!-- Chart + Actions -->
    <section class="two-col">
      <!-- Market trend chart -->
      <div class="glass">
        <div class="card-head">
          <div>
            <div class="card-title"><?= !empty($masiFullSeries) ? 'Indice MASI' : 'Tendance marché' ?></div>
            <div class="masi-value">
              <?php if ($masiLast !== null): ?>
                <span class="masi-num"><?= number_format($masiLast, 2, ',', ' ') ?></span>
                <?php if ($masiChange !== null): ?>
                  <span class="masi-chg <?= $masiChange >= 0 ? 'pos' : 'neg' ?>">
                    <?= ($masiChange >= 0 ? '+' : '') . number_format($masiChange, 2, ',', ' ') ?>
                    · <?= ($masiChangePct >= 0 ? '+' : '') . number_format($masiChangePct, 2, ',', ' ') ?> %
                  </span>
                <?php endif; ?>
              <?php else: ?>
                <span class="masi-num" style="font-size:14px;color:var(--text-faint)">Données insuffisantes</span>
              <?php endif; ?>
            </div>
          </div>
          <div class="segmented" id="masi-periods">
            <span class="seg" data-period="5Y">5A</span>
            <span class="seg" data-period="1Y">1A</span>
            <span class="seg" data-period="6M">6M</span>
            <span class="seg" data-period="3M">3M</span>
            <span class="seg is-active" data-period="1M">1M</span>
          </div>
        </div>
        <div class="card-body" style="padding:0">
          <?php if (!empty($masiFullSeries)): ?>
          <svg class="chart" id="masi-svg" viewBox="0 0 700 210" preserveAspectRatio="none"
               data-sparkline
               data-full="<?= htmlspecialchars(json_encode($masiFullSeries)) ?>">
            <defs>
              <linearGradient id="grad-fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%"   stop-color="#22d3ee" stop-opacity="0.45"/>
                <stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
              </linearGradient>
              <linearGradient id="grad-line" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%"   stop-color="#67e8f9"/>
                <stop offset="100%" stop-color="#22d3ee"/>
              </linearGradient>
            </defs>
            <line x1="0" x2="700" y1="10"  y2="10"  stroke="rgba(255,255,255,0.04)"/>
            <line x1="0" x2="700" y1="80"  y2="80"  stroke="rgba(255,255,255,0.04)"/>
            <line x1="0" x2="700" y1="150" y2="150" stroke="rgba(255,255,255,0.04)"/>
            <path class="spark-area" fill="url(#grad-fill)"/>
            <path class="spark-line" fill="none" stroke="url(#grad-line)" stroke-width="2.2"
                  stroke-linecap="round" stroke-linejoin="round"
                  style="filter:drop-shadow(0 0 6px rgba(34,211,238,0.5))"/>
            <circle class="spark-dot-halo" r="10" fill="rgba(34,211,238,0.15)"/>
            <circle class="spark-dot"      r="4"  fill="#22d3ee"/>
            <!-- crosshair -->
            <line id="masi-xhair" x1="0" y1="0" x2="0" y2="210"
                  stroke="rgba(148,163,184,0.5)" stroke-width="1" stroke-dasharray="4 4"
                  style="display:none;pointer-events:none"/>
            <circle id="masi-xhair-dot" r="4" fill="#22d3ee" stroke="#0f172a" stroke-width="2"
                    style="display:none;pointer-events:none"/>
            <rect id="masi-xhair-bg" rx="4" fill="rgba(15,23,42,0.85)"
                  style="display:none;pointer-events:none"/>
            <text id="masi-xhair-txt" font-size="11" fill="#f1f5f9" font-family="JetBrains Mono,monospace"
                  style="display:none;pointer-events:none"/>
          </svg>
          <div class="masi-slider-wrap">
            <input type="range" id="masi-range-start" min="0" max="100" value="0" step="1">
            <input type="range" id="masi-range-end"   min="0" max="100" value="100" step="1">
          </div>
          <?php else: ?>
          <div style="height:210px;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:13px">
            Aucune donnée disponible
          </div>
          <?php endif; ?>
        </div>
      </div>

      <!-- Quick actions -->
      <div class="glass">
        <div class="card-head">
          <div>
            <div class="card-title">Actions rapides</div>
            <div class="card-sub">Vos outils du quotidien</div>
          </div>
        </div>
        <div class="action-grid">
          <?php if (is_admin()): ?>
          <a class="action-tile" href="Update.php">
            <div class="action-tile-top">
              <div class="action-icon cyan">+</div>
              <span class="action-arrow">→</span>
            </div>
            <div>
              <div class="action-label">Société / MAJ</div>
              <div class="action-sub">Ajouter ou MAJ</div>
            </div>
          </a>
          <?php else: ?>
          <a class="action-tile" href="screener.php">
            <div class="action-tile-top">
              <div class="action-icon cyan">▽</div>
              <span class="action-arrow">→</span>
            </div>
            <div>
              <div class="action-label">Screener</div>
              <div class="action-sub">Filtrer · <?= (int)$totalCompanies ?> résultats</div>
            </div>
          </a>
          <?php endif; ?>
          <a class="action-tile" href="infoAction.php">
            <div class="action-tile-top">
              <div class="action-icon green">⌕</div>
              <span class="action-arrow">→</span>
            </div>
            <div>
              <div class="action-label">Consulter</div>
              <div class="action-sub">Historique &amp; ratios</div>
            </div>
          </a>
          <a class="action-tile" href="portfolio.php">
            <div class="action-tile-top">
              <div class="action-icon purple">◐</div>
              <span class="action-arrow">→</span>
            </div>
            <div>
              <div class="action-label">Portefeuille</div>
              <div class="action-sub">Achats · P&amp;L</div>
            </div>
          </a>
          <a class="action-tile" href="screener.php">
            <div class="action-tile-top">
              <div class="action-icon orange">▽</div>
              <span class="action-arrow">→</span>
            </div>
            <div>
              <div class="action-label">Screener</div>
              <div class="action-sub">Filtrer · <?= (int)$totalCompanies ?> résultats</div>
            </div>
          </a>
        </div>
      </div>
    </section>

    <!-- Mouvements table -->
    <section class="glass" style="margin-bottom:24px">
      <div class="card-head">
        <div>
          <div class="card-title">Mouvements de la séance</div>
          <div class="card-sub" id="table-sub">Top hausses · <?= htmlspecialchars($dateLabel) ?> · <?= $timeLabel ?></div>
        </div>
        <div class="segmented">
          <button class="seg is-active" onclick="showTab('gainers', this, 'Top hausses')">Hausses</button>
          <button class="seg" onclick="showTab('losers', this, 'Top baisses')">Baisses</button>
          <button class="seg" onclick="showTab('scored', this, 'Score 4/4')">Score 4/4</button>
        </div>
      </div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Société</th>
              <th class="num">Prix (MAD)</th>
              <th class="num">Δ jour</th>
              <th class="num">PER</th>
              <th class="num">PEG</th>
              <th class="num">P/R</th>
              <th class="num">P/B</th>
              <th class="num" style="padding-right:24px">Score</th>
            </tr>
          </thead>
          <tbody id="tbody-gainers">
            <?php if (empty($topGainers)): ?>
              <tr><td colspan="8" style="text-align:center;color:var(--text-faint);padding:24px">Aucune donnée</td></tr>
            <?php else: foreach ($topGainers as $r): ?>
            <tr>
              <td class="name"><span class="ticker"><?= htmlspecialchars($r['abbr']) ?></span><?= htmlspecialchars($r['name']) ?></td>
              <td class="num"><?= number_format($r['PA'], 2, ',', ' ') ?></td>
              <td class="num pos">+<?= number_format($r['trend'], 2, ',', ' ') ?> %</td>
              <td class="num"><?= number_format($r['PER'], 2, ',', ' ') ?></td>
              <td class="num"><?= $r['PEG'] ? number_format($r['PEG'], 2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PR']  ? number_format($r['PR'],  2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PB']  ? number_format($r['PB'],  2, ',', ' ') : '—' ?></td>
              <td class="num" style="padding-right:24px"><span class="score-pill s-<?= $r['score'] ?>"><?= $r['score'] ?>/4</span></td>
            </tr>
            <?php endforeach; endif; ?>
          </tbody>
          <tbody id="tbody-losers" style="display:none">
            <?php if (empty($topLosers)): ?>
              <tr><td colspan="8" style="text-align:center;color:var(--text-faint);padding:24px">Aucune donnée</td></tr>
            <?php else: foreach ($topLosers as $r): ?>
            <tr>
              <td class="name"><span class="ticker"><?= htmlspecialchars($r['abbr']) ?></span><?= htmlspecialchars($r['name']) ?></td>
              <td class="num"><?= number_format($r['PA'], 2, ',', ' ') ?></td>
              <td class="num neg"><?= number_format($r['trend'], 2, ',', ' ') ?> %</td>
              <td class="num"><?= number_format($r['PER'], 2, ',', ' ') ?></td>
              <td class="num"><?= $r['PEG'] ? number_format($r['PEG'], 2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PR']  ? number_format($r['PR'],  2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PB']  ? number_format($r['PB'],  2, ',', ' ') : '—' ?></td>
              <td class="num" style="padding-right:24px"><span class="score-pill s-<?= $r['score'] ?>"><?= $r['score'] ?>/4</span></td>
            </tr>
            <?php endforeach; endif; ?>
          </tbody>
          <tbody id="tbody-scored" style="display:none">
            <?php if (empty($topScored)): ?>
              <tr><td colspan="8" style="text-align:center;color:var(--text-faint);padding:24px">Aucun score 4/4</td></tr>
            <?php else: foreach ($topScored as $r): ?>
            <tr>
              <td class="name"><span class="ticker"><?= htmlspecialchars($r['abbr']) ?></span><?= htmlspecialchars($r['name']) ?></td>
              <td class="num"><?= number_format($r['PA'], 2, ',', ' ') ?></td>
              <td class="num <?= $r['trend'] !== null ? ($r['trend'] >= 0 ? 'pos' : 'neg') : '' ?>">
                <?= $r['trend'] !== null ? (($r['trend'] >= 0 ? '+' : '') . number_format($r['trend'], 2, ',', ' ') . ' %') : '—' ?>
              </td>
              <td class="num"><?= number_format($r['PER'], 2, ',', ' ') ?></td>
              <td class="num"><?= $r['PEG'] ? number_format($r['PEG'], 2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PR']  ? number_format($r['PR'],  2, ',', ' ') : '—' ?></td>
              <td class="num"><?= $r['PB']  ? number_format($r['PB'],  2, ',', ' ') : '—' ?></td>
              <td class="num" style="padding-right:24px"><span class="score-pill s-4">4/4</span></td>
            </tr>
            <?php endforeach; endif; ?>
          </tbody>
        </table>
      </div>
    </section>

    <?php endif; ?>
  </main>
</div>

<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
<script>
// MASI sparkline with period selector + dual range slider
(function () {
  var svg = document.getElementById('masi-svg');
  if (!svg) return;
  var fullRaw = svg.getAttribute('data-full');
  if (!fullRaw) return;
  var full; try { full = JSON.parse(fullRaw); } catch(e) { return; }
  if (!full || full.length < 2) return;

  var sliderStart = document.getElementById('masi-range-start');
  var sliderEnd   = document.getElementById('masi-range-end');

  // Period → days back
  var periodDays = { '5Y': 5*365, '1Y': 365, '6M': 182, '3M': 91, '1M': 30 };

  function dateStr(daysBack) {
    var d = new Date(); d.setDate(d.getDate() - daysBack);
    return d.toISOString().slice(0,10);
  }

  function renderSeries(series) {
    if (!series || series.length < 2) return;
    renderedSeries = series;
    var s = series.map(function(p){ return p.v; });
    var vb = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    var w = vb[2], h = vb[3], pad = 14;
    var min = Math.min.apply(null, s), max = Math.max.apply(null, s);
    var rng = max - min || 1;
    var step = (w - pad*2) / (s.length - 1);
    var pts = s.map(function(v, i) {
      return { x: pad + i*step, y: pad + (h - pad*2) * (1 - (v - min) / rng) };
    });
    renderedPts = pts;
    var line = pts.map(function(p,i){ return (i===0?'M':'L')+p.x.toFixed(1)+' '+p.y.toFixed(1); }).join(' ');
    var area = line+' L'+(w-pad).toFixed(1)+' '+(h-pad)+' L'+pad+' '+(h-pad)+' Z';
    svg.querySelector('.spark-line').setAttribute('d', line);
    svg.querySelector('.spark-area').setAttribute('d', area);
    var last = pts[pts.length-1];
    svg.querySelector('.spark-dot').setAttribute('cx', last.x);
    svg.querySelector('.spark-dot').setAttribute('cy', last.y);
    svg.querySelector('.spark-dot-halo').setAttribute('cx', last.x);
    svg.querySelector('.spark-dot-halo').setAttribute('cy', last.y);
  }

  var currentSlice = full;
  var renderedPts  = [];
  var renderedSeries = [];

  // Crosshair elements
  var xhair    = document.getElementById('masi-xhair');
  var xhairDot = document.getElementById('masi-xhair-dot');
  var xhairBg  = document.getElementById('masi-xhair-bg');
  var xhairTxt = document.getElementById('masi-xhair-txt');

  svg.addEventListener('mousemove', function(e) {
    if (!renderedPts.length) return;
    var rect = svg.getBoundingClientRect();
    var vb   = svg.getAttribute('viewBox').split(/\s+/).map(Number);
    var mx   = (e.clientX - rect.left) / rect.width  * vb[2];
    var my   = (e.clientY - rect.top)  / rect.height * vb[3];
    // find closest point by x
    var best = 0, bestDist = Infinity;
    renderedPts.forEach(function(p, i) {
      var d = Math.abs(p.x - mx);
      if (d < bestDist) { bestDist = d; best = i; }
    });
    var p = renderedPts[best];
    var label = (renderedSeries[best] && renderedSeries[best].d) || '';
    var val   = (renderedSeries[best] && renderedSeries[best].v) || 0;
    var txt   = val.toFixed(2) + '  ' + label;

    xhair.setAttribute('x1', p.x); xhair.setAttribute('x2', p.x);
    xhair.setAttribute('y1', 0);   xhair.setAttribute('y2', vb[3]);
    xhairDot.setAttribute('cx', p.x); xhairDot.setAttribute('cy', p.y);

    var tw = txt.length * 6.5 + 14, th = 18;
    var bx = Math.min(p.x + 8, vb[2] - tw - 4);
    var by = Math.max(p.y - th - 4, 2);
    xhairBg.setAttribute('x', bx); xhairBg.setAttribute('y', by);
    xhairBg.setAttribute('width', tw); xhairBg.setAttribute('height', th);
    xhairTxt.setAttribute('x', bx + 7); xhairTxt.setAttribute('y', by + 13);
    xhairTxt.textContent = txt;

    xhair.style.display = xhairDot.style.display = xhairBg.style.display = xhairTxt.style.display = '';
  });
  svg.addEventListener('mouseleave', function() {
    xhair.style.display = xhairDot.style.display = xhairBg.style.display = xhairTxt.style.display = 'none';
  });

  function applySliders() {
    var n = currentSlice.length;
    var s = Math.round(parseInt(sliderStart.value) / 100 * (n - 1));
    var e = Math.round(parseInt(sliderEnd.value)   / 100 * (n - 1));
    if (s >= e) e = s + 1;
    renderSeries(currentSlice.slice(s, e + 1));
  }

  function setPeriod(period) {
    var cutoff = dateStr(periodDays[period]);
    currentSlice = full.filter(function(p){ return p.d >= cutoff; });
    if (currentSlice.length < 2) currentSlice = full;
    // reset sliders to full range
    sliderStart.value = 0;
    sliderEnd.value   = 100;
    renderSeries(currentSlice);
  }

  // Period buttons
  document.querySelectorAll('#masi-periods .seg').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('#masi-periods .seg').forEach(function(b){ b.classList.remove('is-active'); });
      btn.classList.add('is-active');
      setPeriod(btn.getAttribute('data-period'));
    });
  });

  // Sliders — keep start ≤ end
  sliderStart.addEventListener('input', function() {
    if (parseInt(sliderStart.value) >= parseInt(sliderEnd.value))
      sliderEnd.value = Math.min(100, parseInt(sliderStart.value) + 1);
    applySliders();
  });
  sliderEnd.addEventListener('input', function() {
    if (parseInt(sliderEnd.value) <= parseInt(sliderStart.value))
      sliderStart.value = Math.max(0, parseInt(sliderEnd.value) - 1);
    applySliders();
  });

  // Initial render: 1M
  setPeriod('1M');
})();

// Table tab switcher
function showTab(tab, btn, label) {
  ['gainers', 'losers', 'scored'].forEach(function (t) {
    document.getElementById('tbody-' + t).style.display = t === tab ? '' : 'none';
  });
  document.querySelectorAll('.segmented .seg').forEach(function (s) { s.classList.remove('is-active'); });
  btn.classList.add('is-active');
  document.getElementById('table-sub').textContent = label + ' · ' + btn.closest('section').querySelector('.card-sub').textContent.split(' · ').slice(1).join(' · ');
}

// Auth modal
function switchAuthTab(tab) {
  var isLogin = tab === 'login';
  document.getElementById('formLogin').style.display  = isLogin ? '' : 'none';
  document.getElementById('formSignup').style.display = isLogin ? 'none' : '';
  document.getElementById('tabLogin').style.background  = isLogin ? 'rgba(34,211,238,0.12)' : '';
  document.getElementById('tabLogin').style.color       = isLogin ? 'var(--cyan)' : '';
  document.getElementById('tabSignup').style.background = isLogin ? '' : 'rgba(34,211,238,0.12)';
  document.getElementById('tabSignup').style.color      = isLogin ? '' : 'var(--cyan)';
}
<?php if ($loginError): ?>
document.addEventListener('DOMContentLoaded', function () {
  new bootstrap.Modal(document.getElementById('loginModal')).show();
  switchAuthTab('<?= $isSignUp ? 'signup' : 'login' ?>');
});
<?php endif; ?>
document.addEventListener('DOMContentLoaded', function () { switchAuthTab('login'); });
</script>
</body>
</html>
