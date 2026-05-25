<?php
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/auth.php';
require_once 'core/Action.php';
session_start();
require_once 'handlers/storing.php';
requireAdmin();

if (!isset($_SESSION['company'])) {
    header('Location: ' . BASE_URL . '/Update.php');
    exit();
}

/** @var Company $company */
$company = $_SESSION['company'];
$company->calcul();
$colors  = $company->test();

// ─── Auto-save if flagged ─────────────────────────────────
$autoSaved  = false;
$saveError  = null;
if (!empty($_SESSION['save'])) {
    unset($_SESSION['save']);
    try {
        store($company);
        $autoSaved = true;
    } catch (Throwable $e) {
        $saveError = $e->getMessage();
    }
}

// ─── Manual save via form ─────────────────────────────────────────────────
$manualSaved = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['confirm_save'])) {
    csrf_verify();
    try {
        store($company);
        $manualSaved = true;
    } catch (Throwable $e) {
        $saveError = $e->getMessage();
    }
}

function contrastFor(string $color): string {
    return $color === 'orange' ? '#000' : '#fff';
}

$icons = ['PER' => 'fa-chart-pie', 'PEG' => 'fa-balance-scale', 'PR' => 'fa-coins', 'PB' => 'fa-building'];
$labels = ['PER' => 'P.E.R', 'PEG' => 'PEG', 'PR' => 'P/R', 'PB' => 'P/B'];
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>Analyse — <?= htmlspecialchars($company->NAME) ?></title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/results.css" rel="stylesheet">
</head>
<body>
<div class="page">

  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Résultats</span>
    <div class="topbar-spacer"></div>
    <a href="Update.php" class="btn btn-ghost btn-sm"><i class="fas fa-edit"></i> Modifier</a>
    <a href="index.php" class="btn btn-ghost btn-sm"><i class="fas fa-home"></i></a>
  </nav>

  <div class="results-wrap animate-up">

    <?php if ($manualSaved || $autoSaved): ?>
      <div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>Rapport sauvegardé dans l'historique !</div>
    <?php elseif ($saveError): ?>
      <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i><?= htmlspecialchars($saveError) ?></div>
    <?php endif; ?>

    <!-- Company headline -->
    <div class="company-headline">
      <h2><?= htmlspecialchars($company->NAME) ?></h2>
      <p>Analyse des indicateurs de performance · PA <strong class="t-cyan mono"><?= number_format($company->PA, 2) ?></strong>
        · CB <strong class="t-violet mono"><?= number_format($company->CB, 0, ',', ' ') ?></strong></p>
    </div>

    <!-- Ratio cards -->
    <div class="ratio-grid stagger-children">
      <?php foreach (['PER','PEG','PR','PB'] as $key):
        $val   = $company->$key;
        $color = $colors[$key];
        $icon  = $icons[$key];
        $label = $labels[$key];
      ?>
      <div class="ratio-card <?= $color ?>">
        <div class="ratio-icon"><i class="fas <?= $icon ?>"></i></div>
        <div class="ratio-label"><?= $label ?></div>
        <div class="ratio-value"><?= number_format($val, 2) ?></div>
        <div class="mt-2">
          <span class="pill pill-<?= $color === 'green' ? 'green' : ($color === 'orange' ? 'orange' : 'red') ?>">
            <?= $color === 'green' ? 'Attractif' : ($color === 'orange' ? 'Neutre' : 'Surévalué') ?>
          </span>
        </div>
      </div>
      <?php endforeach; ?>
    </div>

    <!-- Save confirmation -->
    <?php if (!$manualSaved && !$autoSaved): ?>
    <div class="card-glass">
      <div class="save-card">
        <div class="save-card__info">
          <h4><i class="fas fa-database me-2 t-cyan"></i>Validation Finale</h4>
          <p>Souhaitez-vous enregistrer ce snapshot dans l'historique ? Les ratios calculés seront liés à la date d'aujourd'hui.</p>
        </div>
        <div class="save-card__actions">
          <form method="POST" action="" data-loading>
            <?= csrf_field() ?>
            <button type="submit" name="confirm_save" class="btn btn-cyan btn-lg w-100" data-loading-text="Sauvegarde...">
              <i class="fas fa-save"></i> Enregistrer
            </button>
          </form>
          <a href="Update.php" class="btn btn-ghost w-100">
            <i class="fas fa-edit"></i> Modifier
          </a>
          <a href="infoAction.php?name=<?= urlencode($company->NAME) ?>" class="btn btn-ghost w-100">
            <i class="fas fa-history"></i> Historique
          </a>
        </div>
      </div>
    </div>
    <?php else: ?>
    <div style="text-align:center;margin-top:2rem">
      <a href="infoAction.php?name=<?= urlencode($company->NAME) ?>" class="btn btn-cyan"><i class="fas fa-history me-2"></i>Voir l'historique</a>
      <a href="Update.php" class="btn btn-ghost ms-2"><i class="fas fa-plus me-2"></i>Nouvelle analyse</a>
    </div>
    <?php endif; ?>

  </div>
</div>

<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
</body>
</html>
