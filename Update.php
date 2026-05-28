<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
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
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css" rel="stylesheet">
  <link href="assets/css/update.css" rel="stylesheet">
</head>
<body>
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">

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
    <div class="mb-4" style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div>
        <h2 class="mb-1" style="font-family:var(--font-display);font-weight:700;font-size:1.5rem;">Analyser une société</h2>
        <p class="muted" style="font-size:0.85rem;">Renseignez les champs rouges pour calculer. Ajoutez les verts pour sauvegarder.</p>
      </div>
      <a href="handlers/sync_companies.php" class="btn btn-ghost btn-sm" target="_blank"
         style="align-self:center" title="Enrichir toutes les sociétés des données financières">
        <i class="fas fa-cloud-download-alt"></i> Sync toutes les sociétés
      </a>
    </div>

    <form action="handlers/operations.php" method="POST" data-loading>
      <?= csrf_field() ?>

      <!-- Company name -->
      <div class="field-group mb-4">
        <div class="field-group-title cyan" style="display:flex;align-items:center;justify-content:space-between">
          <span><i class="fas fa-building"></i> Société <span class="required-dot">requise</span></span>
          <button type="button" id="btnAutoFill" class="btn btn-ghost btn-sm" onclick="autoFill()" disabled>
            <i class="fas fa-magic"></i> Auto-remplir données financières
          </button>
        </div>
        <?php
          $companyDocs = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
          $companies   = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));
          // Build name→symbol map from format collection
          $fmtDocs    = aw_list_docs('format', [q_limit(500)]);
          $nameToSym  = [];
          foreach ($fmtDocs as $f) {
              if (!empty($f['name']) && !empty($f['symbol']))
                  $nameToSym[$f['name']] = $f['symbol'];
          }
        ?>
        <div class="form-floating">
          <input type="text" name="NAME" id="floatName" list="companyList"
                 class="form-control" placeholder=" "
                 required autocomplete="off"
                 value="<?= htmlspecialchars($old['NAME'] ?? '') ?>"
                 oninput="onNameChange(this.value)">
          <label for="floatName" style="color:var(--rose)"><i class="fas fa-building me-2"></i>Nom de l'entreprise</label>
          <datalist id="companyList">
            <?php foreach ($companies as $n): ?>
              <option value="<?= htmlspecialchars($n) ?>">
            <?php endforeach; ?>
          </datalist>
        </div>
        <div id="mkt-preview" style="display:none;margin-top:10px;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);font-size:0.82rem;color:var(--text-dim)"></div>
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

      <!-- PEG section: TC5 + DPA -->
      <div class="field-group">
        <div class="field-group-title violet"><i class="fas fa-arrow-trend-up"></i> P.E.G — Price/Earnings to Growth</div>
        <div class="row g-3">
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="TC5" id="floatTC5" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['TC5'] ?? '') ?>">
              <label for="floatTC5" class="t-violet">Taux de croissance annuel (TC5 %)</label>
            </div>
          </div>
          <div class="col-md-6">
            <div class="form-floating">
              <input type="number" name="DPA" id="floatDPA" class="form-control"
                     placeholder=" " step="any"
                     value="<?= htmlspecialchars($old['DPA'] ?? '') ?>">
              <label for="floatDPA" class="t-violet">Dividende par action (DPA)</label>
            </div>
          </div>
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
  </main>
</div>

<script src="assets/vendor/bootstrap/bootstrap.bundle.min.js"></script>
<script src="assets/js/app.js"></script>
<script>
const nameToSym = <?= json_encode($nameToSym, JSON_UNESCAPED_UNICODE) ?>;

function onNameChange(val) {
    const sym = nameToSym[val.trim()];
    const btn = document.getElementById('btnAutoFill');
    btn.disabled = !sym;
    btn._symbol = sym || null;
    document.getElementById('mkt-preview').style.display = 'none';
}

// Trigger on page load if a name is pre-filled
document.addEventListener('DOMContentLoaded', () => {
    const v = document.getElementById('floatName').value;
    if (v) onNameChange(v);
});

async function autoFill() {
    const btn = document.getElementById('btnAutoFill');
    const sym = btn._symbol;
    if (!sym) return;

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Chargement…';

    try {
        const r = await fetch('handlers/market_proxy.php?symbol=' + encodeURIComponent(sym));
        const d = await r.json();
        if (d.error) throw new Error(d.error);

        const c = d.computed || {};
        const fill = (id, val) => {
            if (val !== null && val !== undefined) {
                const el = document.getElementById(id);
                if (el && !el.value) el.value = val;
            }
        };

        fill('floatBPA', c.bpa);
        fill('floatDPA', c.dpa);
        fill('floatTC5', c.tc5);
        fill('floatROE', c.roe);
        fill('floatNA',  c.na);
        fill('floatCP',  c.cp);

        // Show preview
        const prev = document.getElementById('mkt-preview');
        const lines = [];
        if (d.sector)       lines.push('<b>Secteur:</b> ' + d.sector);
        if (c.revenue)      lines.push('<b>CA 2024:</b> ' + c.revenue + ' MMAD');
        if (c.net_profit)   lines.push('<b>RNPG:</b> ' + c.net_profit + ' MMAD');
        if (c.beta_3y)      lines.push('<b>Béta 3Y:</b> ' + c.beta_3y);
        if (c.profit_margin)lines.push('<b>Marge nette:</b> ' + c.profit_margin + '%');
        if (d.description)  lines.push('<b>Desc:</b> ' + d.description.substring(0, 120) + '…');
        prev.innerHTML = lines.join(' &nbsp;·&nbsp; ');
        prev.style.display = 'block';

        btn.innerHTML = '<i class="fas fa-check t-emerald"></i> Données financières récupérées';
        window.showToast('Données financières récupérées (' + (d.ext_name || sym) + ')', 'success');

        // Save enrichment data (description, sector, beta, etc.) to Appwrite silently
        const companyName = document.getElementById('floatName').value.trim();
        if (companyName) {
            const fd = new FormData();
            fd.append('name', companyName);
            fd.append('symbol', sym);
            fd.append('_csrf', document.querySelector('meta[name="csrf-token"]').content);
            fetch('handlers/save_enrichment.php', { method: 'POST', body: fd })
              .then(r => r.json())
              .then(res => { if (res.ok && res.description) window.showToast('Fiche société sauvegardée', 'success'); })
              .catch(() => {});
        }
    } catch (e) {
        btn.innerHTML = '<i class="fas fa-magic"></i> Auto-remplir données financières';
        btn.disabled  = false;
        window.showToast('Erreur : ' + e.message, 'error');
    }
}
</script>
</body>
</html>
