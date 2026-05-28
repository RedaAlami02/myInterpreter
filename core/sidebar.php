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
<aside class="sidebar">
  <div class="brand">
    <div class="brand-mark">m</div>
    <div>
      <div class="brand-name">myInterpreter</div>
      <div class="brand-sub">Bourse de Casablanca</div>
    </div>
  </div>

  <nav class="nav-group nav-group--primary">
    <div class="nav-label">Navigation</div>
    <a class="nav-item<?= _sb_active('index.php') ?>" href="index.php">
      <span class="nav-icon">◆</span>
      <span>Tableau de bord</span>
    </a>
    <?php if ($_sbIsAdmin): ?>
    <a class="nav-item<?= _sb_active('Update.php') ?>" href="Update.php">
      <span class="nav-icon">+</span>
      <span>Société / MAJ</span>
    </a>
    <?php endif; ?>
    <a class="nav-item<?= _sb_active('infoAction.php') ?>" href="infoAction.php">
      <span class="nav-icon">⌕</span>
      <span>Consulter Action</span>
    </a>
    <a class="nav-item<?= _sb_active('portfolio.php') ?>" href="portfolio.php">
      <span class="nav-icon">◐</span>
      <span>Mon Portefeuille</span>
      <span class="nav-badge">P&amp;L</span>
    </a>
    <a class="nav-item<?= _sb_active('screener.php') ?>" href="screener.php">
      <span class="nav-icon">▽</span>
      <span>Stock Screener</span>
      <?php if (!empty($screenerCount)): ?>
        <span class="nav-badge"><?= (int)$screenerCount ?></span>
      <?php endif; ?>
    </a>
  </nav>

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
</aside>
