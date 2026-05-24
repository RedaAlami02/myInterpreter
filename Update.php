<?php
session_start();
require_once 'config/config.php';
require_once 'core/auth.php';
requireAdmin();

$old = $_SESSION['old_post'] ?? [];
unset($_SESSION['old_post']);
$saved = isset($_GET['saved']);
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="<?= csrf_token() ?>">
  <title>myInterpreter | Update Stock</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/update.css" rel="stylesheet">
</head>
<body>
<div class="page">

  <!-- Top bar -->
  <nav class="topbar">
    <a href="index.php" class="topbar-brand"><i class="fas fa-chart-line"></i> myInterpreter</a>
    <span class="topbar-sep">/</span>
    <span class="topbar-title">Update Stock</span>
    <div class="topbar-spacer"></div>
    <a href="index.php" class="btn btn-ghost btn-sm"><i class="fas fa-arrow-left"></i> Accueil</a>
  </nav>

  <div class="update-wrap animate-up">

    <?php if (!empty($_SESSION['erreurs'])): ?>
      <div class="alert alert-danger mb-4">
        <i class="fas fa-exclamation-triangle me-2"></i>
        <?= implode('<br>', $_SESSION['erreurs']) ?>
      </div>
      <?php unset($_SESSION['erreurs']); ?>
    <?php endif; ?>

    <?php if ($saved): ?>
      <div class="alert alert-success mb-4"><i class="fas fa-check-circle me-2"></i>Données sauvegardées avec succès !</div>
    <?php endif; ?>

    <!-- Header -->
    <div class="mb-4">
      <h2 class="mb-1" style="font-family:var(--font-display);font-weight:700;font-size:1.5rem;">Analyser une société</h2>
      <p class="muted" style="font-size:0.85rem;">Renseignez les champs rouges pour calculer. Ajoutez les verts pour sauvegarder.</p>
    </div>

    <form action="handlers/operations.php" method="POST" data-loading>
      <?= csrf_field() ?>

      <!-- Company name -->
      <div class="field-group mb-4">
        <div class="field-group-title cyan"><i class="fas fa-building"></i> Société <span class="required-dot">requise</span></div>
        <?php
          require_once 'core/Appwrite.php';
          $companyDocs = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
          $companies   = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));
        ?>
        <div class="form-floating">
          <input type="text" name="NAME" id="floatName" list="companyList"
                 class="form-control" placeholder=" "
                 required autocomplete="off"
                 value="<?= htmlspecialchars($old['NAME'] ?? '') ?>">
          <label for="floatName" style="color:var(--rose)"><i class="fas fa-building me-2"></i>Nom de l'entreprise</label>
          <datalist id="companyList">
            <?php foreach ($companies as $n): ?>
              <option value="<?= htmlspecialchars($n) ?>">
            <?php endforeach; ?>
          </datalist>
        </div>
      </div>

      <!-- PER section: PA + BPA -->
      <div class="field-group">
        <div class="field-group-title cyan"><i class="fas fa-chart-pie"></i> P.E.R — Price Earning Ratio</div>
        <div class="row g-3">
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="PA" id="floatPA" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['PA'] ?? '') ?>">
              <label for="floatPA" style="color:var(--rose)">Prix de l'action (PA) <span class="required-dot"></span></label>
            </div>
          </div>
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="BPA" id="floatBPA" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['BPA'] ?? '') ?>">
              <label for="floatBPA" class="t-emerald">Bénéfice par action (BPA)</label>
            </div>
          </div>
        </div>
      </div>

      <!-- PEG section: TC5 -->
      <div class="field-group">
        <div class="field-group-title violet"><i class="fas fa-arrow-trend-up"></i> P.E.G — Price/Earnings to Growth</div>
        <div class="form-floating">
          <input type="number" name="TC5" id="floatTC5" class="form-control"
                 placeholder=" " step="any"
                 value="<?= htmlspecialchars($old['TC5'] ?? '') ?>">
          <label for="floatTC5" class="t-violet">Taux de croissance annuel (TC5 %)</label>
        </div>
      </div>

      <!-- PR section: ROE -->
      <div class="field-group">
        <div class="field-group-title emerald"><i class="fas fa-coins"></i> P/R — Price / ROE</div>
        <div class="form-floating">
          <input type="number" name="ROE" id="floatROE" class="form-control"
                 placeholder=" " step="any"
                 value="<?= htmlspecialchars($old['ROE'] ?? '') ?>">
          <label for="floatROE" class="t-emerald">Rentabilité des capitaux propres (ROE %)</label>
        </div>
      </div>

      <!-- PB section: NA + CP -->
      <div class="field-group">
        <div class="field-group-title amber"><i class="fas fa-landmark"></i> P/B — Price to Book Value</div>
        <div class="row g-3">
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="NA" id="floatNA" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['NA'] ?? '') ?>">
              <label for="floatNA" class="t-amber">Nombre d'actions (NA)</label>
            </div>
          </div>
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="CP" id="floatCP" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['CP'] ?? '') ?>">
              <label for="floatCP" class="t-amber">Capitaux propres (CP)</label>
            </div>
          </div>
        </div>
      </div>

      <div class="action-bar">
        <button type="submit" name="action" value="big_update" class="btn btn-violet">
          <i class="fas fa-sync-alt"></i> Full Update
        </button>
        <button type="submit" name="action" value="save_changes" class="btn btn-cyan" data-loading-text="Calcul...">
          <i class="fas fa-calculator"></i> Calculer
        </button>
        <button type="submit" name="action" value="save_immediately" class="btn btn-emerald">
          <i class="fas fa-save"></i> Sauvegarder
        </button>
      </div>
    </form>
  </div><!-- .update-wrap -->
</div><!-- .page -->

<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
</body>
</html>
