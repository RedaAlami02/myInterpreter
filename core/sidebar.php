<?php
require_once __DIR__ . '/i18n.php';
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
  <a class="brand" href="index.php" aria-label="<?= te('Retour au tableau de bord') ?>">
    <img class="brand-logo" src="favicon.svg" width="36" height="36" alt="">
    <div>
      <div class="brand-name">myInterpreter</div>
      <div class="brand-sub"><?= te('Bourse de Casablanca') ?></div>
    </div>
  </a>

  <nav class="nav-group nav-group--primary" aria-label="<?= te('Navigation principale') ?>">
    <div class="nav-label"><?= te('Navigation') ?></div>
    <a class="nav-item<?= _sb_active('index.php') ?>" href="index.php">
      <span class="nav-icon">◆</span>
      <span><?= te('Marché') ?></span>
    </a>
    <?php if ($_sbIsAdmin): ?>
    <a class="nav-item<?= _sb_active('Update.php') ?>" href="Update.php">
      <span class="nav-icon">+</span>
      <span><?= te('Société / MAJ') ?></span>
    </a>
    <?php endif; ?>
    <a class="nav-item<?= _sb_active('infoAction.php') ?>" href="infoAction.php">
      <span class="nav-icon">⌕</span>
      <span><?= te('Sociétés') ?></span>
    </a>
    <a class="nav-item<?= _sb_active('portfolio.php') ?>" href="portfolio.php">
      <span class="nav-icon">◐</span>
      <span><?= te('Portefeuille') ?></span>
      <span class="nav-badge"><?= te('P&amp;L') ?></span>
    </a>
    <a class="nav-item<?= _sb_active('screener.php') ?>" href="screener.php">
      <span class="nav-icon">▽</span>
      <span><?= te('Sélection') ?></span>
      <?php if (!empty($screenerCount)): ?>
        <span class="nav-badge"><?= (int)$screenerCount ?></span>
      <?php endif; ?>
    </a>
    <a class="nav-item<?= _sb_active('dividendes.php') ?>" href="dividendes.php">
      <span class="nav-icon">◈</span>
      <span><?= te('Dividendes') ?></span>
    </a>
  </nav>

  <div class="workspace-actions">
  <form method="GET" class="language-switch">
    <?php foreach ($_GET as $key => $value): if ($key === 'lang' || !is_scalar($value)) continue; ?>
      <input type="hidden" name="<?= htmlspecialchars($key) ?>" value="<?= htmlspecialchars((string)$value) ?>">
    <?php endforeach; ?>
    <label class="visually-hidden" for="uiLanguage"><?= te('Langue') ?></label>
    <select id="uiLanguage" name="lang" data-language-select aria-label="<?= te('Langue') ?>">
      <?php foreach (['fr' => 'Français', 'en' => 'English', 'ar' => 'العربية', 'ary' => 'الدارجة المغربية'] as $code => $label): ?>
        <option value="<?= $code ?>" lang="<?= $code ?>" <?= ui_locale() === $code ? 'selected' : '' ?>><?= $label ?></option>
      <?php endforeach; ?>
    </select>
    <noscript><button type="submit"><?= te('Appliquer') ?></button></noscript>
  </form>
  <button type="button" class="theme-toggle" data-theme-toggle aria-label="<?= te('Changer de thème') ?>">
    <span aria-hidden="true">◐</span><span data-theme-label><?= te('Thème') ?></span>
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
          <?= te('Déconnexion →') ?>
        </button>
      </form>
    </div>
  </div>
  <?php endif; ?>
  </div>
  </div>
</header>
