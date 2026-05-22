<?php
ob_start();
session_start();
require_once 'config/config.php';
require_once 'core/Database.php';

// ─── Restore session from cookie ─────────────────────────
if (!isset($_SESSION['logged_in']) && isset($_COOKIE['logged_in']) && $_COOKIE['logged_in'] === '1') {
    $_SESSION['logged_in'] = true;
    $_SESSION['ID_USER']   = (int) ($_COOKIE['ID_USER'] ?? 0);
}

// ─── Logout ───────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['logout'])) {
    session_destroy();
    setcookie('logged_in', '', time() - 3600, '/', '', false, true);
    setcookie('ID_USER',   '', time() - 3600, '/', '', false, true);
    header('Location: ' . BASE_URL . '/index.php');
    exit();
}

// ─── Login ────────────────────────────────────────────────
$loginError = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['login_form'])) {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';

    $db   = (new Database())->opendb();
    $stmt = $db->prepare('SELECT * FROM utilisateur WHERE USERNAME = ?');
    $stmt->execute([$username]);
    $user = $stmt->fetch();

    $verified = false;
    if ($user) {
        if (password_verify($password, $user['PASSWORD'])) {
            // Modern bcrypt hash — OK
            $verified = true;
        } elseif ($user['PASSWORD'] === $password) {
            // Plain-text (legacy) — verify and migrate to bcrypt immediately
            $hash = password_hash($password, PASSWORD_BCRYPT);
            $db->prepare('UPDATE utilisateur SET PASSWORD = ? WHERE ID_USER = ?')
               ->execute([$hash, $user['ID_USER']]);
            $verified = true;
        }
    }

    if ($verified) {
        $_SESSION['logged_in'] = true;
        $_SESSION['ID_USER']   = $user['ID_USER'];
        $_SESSION['USERNAME']  = $user['USERNAME'];
        // HttpOnly + SameSite cookies
        setcookie('logged_in', '1',           time() + 86400 * 30, '/', '', false, true);
        setcookie('ID_USER',   $user['ID_USER'], time() + 86400 * 30, '/', '', false, true);
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    } else {
        $loginError = 'Identifiants incorrects.';
    }
}

$isLoggedIn = isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true;
$username   = htmlspecialchars($_SESSION['USERNAME'] ?? '');

// ─── Quick stats for the dashboard ───────────────────────
$companyCount = 0; $dataCount = 0;
if ($isLoggedIn) {
    try {
        $db = (new Database())->opendb();
        $companyCount = $db->query('SELECT COUNT(*) FROM company')->fetchColumn();
        $dataCount    = $db->query('SELECT COUNT(*) FROM data')->fetchColumn();
    } catch (Exception $e) {}
}
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>myInterpreter | Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <style>
    body { display: flex; align-items: center; justify-content: center; overflow-x: hidden; }

    .home-wrap {
      display: flex;
      align-items: center;
      gap: 60px;
      padding: 40px 24px;
      width: 100%;
      max-width: 1000px;
    }

    /* Side tagline */
    .tagline {
      font-family: var(--font-display);
      font-size: 2.8rem;
      font-weight: 800;
      line-height: 1.15;
      color: var(--text);
      flex: 1;
      opacity: 0;
      transform: translateX(-30px);
      transition: opacity 1s ease, transform 1s ease;
    }
    .tagline.show { opacity: 1; transform: translateX(0); }
    .tagline span.t-cyan { display: block; }

    /* Main card */
    .dash-card {
      width: 420px;
      flex-shrink: 0;
      animation: fadeUp 0.7s 0.2s ease both;
    }

    .dash-card-inner {
      background: rgba(17,24,39,0.85);
      backdrop-filter: blur(24px);
      border: 1px solid var(--border-hi);
      border-radius: var(--radius-xl);
      padding: 2.5rem 2rem;
      box-shadow: 0 30px 60px rgba(0,0,0,0.5);
    }

    .logo-area { text-align: center; margin-bottom: 2rem; }
    .logo-icon {
      width: 60px; height: 60px;
      background: var(--cyan-dim);
      border: 1px solid rgba(34,211,238,0.25);
      border-radius: 18px;
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 1.5rem; color: var(--cyan);
      margin-bottom: 14px;
    }
    .logo-area h1 {
      font-family: var(--font-display);
      font-size: 1.7rem; font-weight: 800;
      background: linear-gradient(135deg, #fff 30%, #94a3b8);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      margin: 0;
    }

    /* Stats row */
    .dash-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 1.8rem; }
    .dash-stat {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px 16px;
      text-align: center;
    }
    .dash-stat__val {
      font-family: var(--font-display); font-weight: 700; font-size: 1.5rem;
      color: var(--cyan); line-height: 1;
    }
    .dash-stat__lbl { font-size: 0.72rem; color: var(--text-mute); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.08em; }

    /* Nav cards */
    .nav-cards { display: flex; flex-direction: column; gap: 10px; }
    .nav-card {
      display: flex; align-items: center; gap: 14px;
      padding: 14px 18px;
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      text-decoration: none; color: var(--text-dim);
      transition: var(--transition);
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

    .nav-icon {
      width: 40px; height: 40px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1rem; flex-shrink: 0;
    }
    .nav-icon.cyan    { background: var(--cyan-dim);    color: var(--cyan); }
    .nav-icon.emerald { background: var(--emerald-dim); color: var(--emerald); }
    .nav-icon.violet  { background: var(--violet-dim);  color: var(--violet); }
    .nav-icon.amber   { background: var(--amber-dim);   color: var(--amber); }
    .nav-text strong { display: block; font-family: var(--font-display); font-size: 0.9rem; font-weight: 600; }
    .nav-text span { font-size: 0.78rem; color: var(--text-mute); }
    .nav-arrow { margin-left: auto; color: var(--text-mute); font-size: 0.8rem; }

    /* Auth area */
    .auth-area { margin-bottom: 1.8rem; display: flex; justify-content: center; gap: 10px; }

    /* Login modal */
    .modal-glass .modal-content {
      background: rgba(13,17,27,0.95);
      backdrop-filter: blur(24px);
      border: 1px solid var(--border-hi);
      border-radius: var(--radius-xl);
      color: var(--text);
    }
    .modal-glass .modal-header { border-bottom: 1px solid var(--border); }
    .modal-glass .modal-title { font-family: var(--font-display); font-weight: 700; }
    .modal-glass .btn-close { filter: invert(1) brightness(0.6); }

    @media (max-width: 900px) {
      .home-wrap { flex-direction: column; align-items: center; gap: 30px; }
      .tagline { font-size: 2rem; text-align: center; transform: none; flex: none; }
      .dash-card { width: 100%; max-width: 440px; }
    }
  </style>
</head>
<body>

<!-- Login Modal — MUST be outside .page so Bootstrap's body-level backdrop
     does not sit above it in the stacking order -->
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
        <form method="POST" action="" data-loading>
          <?= csrf_field() ?>
          <input type="hidden" name="login_form" value="1">
          <div class="mb-3">
            <label class="form-label small muted">Nom d'utilisateur</label>
            <input type="text" name="username" class="form-control" placeholder="username" required autofocus>
          </div>
          <div class="mb-4">
            <label class="form-label small muted">Mot de passe</label>
            <input type="password" name="password" class="form-control" placeholder="••••••••" required>
          </div>
          <button type="submit" name="login_form" class="btn btn-cyan w-100 btn-lg" data-loading-text="Vérification...">
            <i class="fas fa-sign-in-alt"></i> Se connecter
          </button>
        </form>
      </div>
    </div>
  </div>
</div>

<div class="page">
<div class="home-wrap">
  <div class="tagline" id="tagline">
    Analyse<br>boursière<br><span class="t-cyan">intelligente.</span>
  </div>

  <div class="dash-card">
    <div class="dash-card-inner">
      <div class="logo-area">
        <div class="logo-icon"><i class="fas fa-chart-line"></i></div>
        <h1>myInterpreter</h1>
      </div>

      <div class="auth-area">
        <?php if ($isLoggedIn): ?>
          <span class="btn btn-ghost btn-sm" style="cursor:default">
            <i class="fas fa-user t-cyan"></i> <?= $username ?>
          </span>
          <form method="POST" action="" style="display:inline">
            <?= csrf_field() ?>
            <button type="submit" name="logout" class="btn btn-ghost btn-sm" style="color:var(--rose)">
              <i class="fas fa-sign-out-alt"></i> Déconnexion
            </button>
          </form>
        <?php else: ?>
          <button type="button" class="btn btn-cyan" data-bs-toggle="modal" data-bs-target="#loginModal">
            <i class="fas fa-sign-in-alt"></i> Se connecter
          </button>
        <?php endif; ?>
      </div>

      <?php if ($isLoggedIn): ?>
        <div class="dash-stats stagger-children" id="stats-row">
          <div class="dash-stat">
            <div class="dash-stat__val"><?= (int)$companyCount ?></div>
            <div class="dash-stat__lbl">Sociétés</div>
          </div>
          <div class="dash-stat">
            <div class="dash-stat__val"><?= (int)$dataCount ?></div>
            <div class="dash-stat__lbl">Snapshots</div>
          </div>
        </div>
      <?php endif; ?>

      <?php if (isset($_SESSION['noLogin'])): unset($_SESSION['noLogin']); ?>
        <div class="alert alert-warn mb-3"><i class="fas fa-lock me-2"></i>Connectez-vous pour accéder à cette page.</div>
      <?php endif; ?>

      <div class="nav-cards stagger-children">
        <a href="Update.php" class="nav-card c1">
          <div class="nav-icon cyan"><i class="fas fa-plus-circle"></i></div>
          <div class="nav-text">
            <strong>Société / MAJ</strong>
            <span>Ajouter ou mettre à jour une société</span>
          </div>
          <i class="fas fa-chevron-right nav-arrow"></i>
        </a>
        <a href="infoAction.php" class="nav-card c2">
          <div class="nav-icon emerald"><i class="fas fa-search"></i></div>
          <div class="nav-text">
            <strong>Consulter Action</strong>
            <span>Historique et ratios d'une société</span>
          </div>
          <i class="fas fa-chevron-right nav-arrow"></i>
        </a>
        <a href="portfolio.php" class="nav-card c3">
          <div class="nav-icon violet"><i class="fas fa-wallet"></i></div>
          <div class="nav-text">
            <strong>Mon Portefeuille</strong>
            <span>Achats, ventes et statistiques P&L</span>
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
</div>

</div><!-- .page -->

<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
<script>
  // Trigger tagline reveal
  window.addEventListener('load', () => {
    setTimeout(() => document.getElementById('tagline').classList.add('show'), 200);
  });

  // Auto-open modal if login error
  <?php if ($loginError): ?>
    document.addEventListener('DOMContentLoaded', () => {
      new bootstrap.Modal(document.getElementById('loginModal')).show();
    });
  <?php endif; ?>
</script>
</body>
</html>
