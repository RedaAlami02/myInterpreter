<?php
$_sbPage    = basename($_SERVER['PHP_SELF']);
$_sbLogged  = isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true;
$_sbEmail   = $_SESSION['USER_EMAIL'] ?? '';
$_sbInitial = strtoupper(substr($_sbEmail, 0, 1)) ?: 'U';
$_sbIsAdmin = (defined('ADMIN_USER_ID') && isset($_SESSION['USER_ID']) && $_SESSION['USER_ID'] === ADMIN_USER_ID);
function _sb_active(string $page): string {
    global $_sbPage;
    return $page === $_sbPage ? ' is-active' : '';
}
?>
<header class="sidebar">
  <div class="workspace-header-inner">
  <a class="brand" href="index.php" aria-label="Retour au tableau de bord">
    <img class="brand-logo" src="favicon.svg" width="36" height="36" alt="">
    <div>
      <div class="brand-name">myInterpreter</div>
      <div class="brand-sub">Bourse de Casablanca</div>
    </div>
  </a>

  <nav class="nav-group nav-group--primary" aria-label="Navigation principale">
    <div class="nav-label">Navigation</div>
    <a class="nav-item<?= _sb_active('index.php') ?>" href="index.php">
      <span class="nav-icon">◆</span>
      <span>Marché</span>
    </a>
    <?php if ($_sbIsAdmin): ?>
    <a class="nav-item<?= _sb_active('Update.php') ?>" href="Update.php">
      <span class="nav-icon">+</span>
      <span>Société / MAJ</span>
    </a>
    <?php endif; ?>
    <a class="nav-item<?= _sb_active('infoAction.php') ?>" href="infoAction.php">
      <span class="nav-icon">⌕</span>
      <span>Sociétés</span>
    </a>
    <a class="nav-item<?= _sb_active('portfolio.php') ?>" href="portfolio.php">
      <span class="nav-icon">◐</span>
      <span>Portefeuille</span>
      <span class="nav-badge">P&amp;L</span>
    </a>
    <a class="nav-item<?= _sb_active('screener.php') ?>" href="screener.php">
      <span class="nav-icon">▽</span>
      <span>Sélection</span>
      <?php if (!empty($screenerCount)): ?>
        <span class="nav-badge"><?= (int)$screenerCount ?></span>
      <?php endif; ?>
    </a>
    <a class="nav-item<?= _sb_active('dividendes.php') ?>" href="dividendes.php">
      <span class="nav-icon">◈</span>
      <span>Dividendes</span>
    </a>
  </nav>

  <div class="workspace-actions">
  <button type="button" class="theme-toggle" data-theme-toggle aria-label="Changer de thème">
    <span aria-hidden="true">◐</span><span data-theme-label>Thème</span>
  </button>
  <?php if ($_sbLogged): ?>
  <div class="user-pill">
    <div class="user-avatar"><?= htmlspecialchars($_sbInitial) ?></div>
    <div style="flex:1;min-width:0;overflow:hidden;">
      <div class="user-name"><?= htmlspecialchars($_sbEmail) ?></div>
      <form method="POST" action="index.php" style="margin:0">
        <?= csrf_field() ?>
        <button type="submit" name="logout"
          style="font-size:10px;color:var(--neg);background:none;border:none;cursor:pointer;padding:0;line-height:1.6">
          Déconnexion →
        </button>
      </form>
    </div>
  </div>
  <?php endif; ?>
  </div>
  </div>
</header>
