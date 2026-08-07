<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';
require_once 'core/dividends.php';

$allCompanies = [];
$company      = null;
$history      = [];
$sparkLabels  = [];
$sparkData    = [];
$searched     = false;
$dbError      = null;
$divRows      = [];
$divNext      = null;
$divWhen      = null;
$divHistory   = [];
$divUsualMonth = null;
$divPredict   = null;
$fyEst        = 0;
$rnpgEst      = 0.0;
$perEst       = null;
$perRep       = null;
$fyStale      = false;
$divPrice     = 0.0;
$suggestions  = [];
$symbolTo     = [];   // ticker symbol => stored company name

// ─── Initial company list ─────────────────────────────────
try {
    $companyDocs  = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
    $allCompanies = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));

    // Readable label per company, for the search dropdown only — never a key.
    $labelOf = [];
    foreach ($companyDocs as $c) {
        $n = trim($c['name'] ?? '');
        if ($n !== '') $labelOf[$n] = display_name($n, $c['ext_name'] ?? null);
    }

    // Symbols power ticker lookup ("ATW") and the datalist hints.
    foreach (aw_list_docs('format', [q_limit(500)]) as $f) {
        if (!empty($f['symbol']) && !empty($f['name'])) $symbolTo[$f['symbol']] = $f['name'];
    }
} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// ─── Handle search ────────────────────────────────────────
if (!$dbError && isset($_GET['name']) && !empty($_GET['name']) && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $_POST['NAME'] = trim($_GET['name']);
    $_SERVER['REQUEST_METHOD'] = 'POST';
}

if (!$dbError && $_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['NAME'])) {
    $searched = true;
    $typed    = trim($_POST['NAME']);

    // Resolve what the user typed to a stored name before querying. A bare
    // exact match here used to reject "Maroc Telecom", "ITM" and "attijari"
    // alike, which made the whole page look broken.
    $resolved    = resolve_company($typed, $allCompanies, $symbolTo);
    $name        = $resolved['name'] ?? $typed;
    $suggestions = $resolved['suggestions'];

    try {
        $companyRes = $resolved['name'] === null ? [] : aw_list_docs('company', [
            q_equal('name', $name),
            q_limit(1),
        ]);
        $company = !empty($companyRes) ? $companyRes[0] : null;

        if ($company) {
            // Paginate to get full history (can exceed 500 after backfill)
            $historyAll = []; $histOffset = 0;
            do {
                $page = aw_list_docs('data', [
                    q_equal('c_name', $name),
                    q_order_desc('date'),
                    q_limit(500),
                    q_offset($histOffset),
                ]);
                $historyAll = array_merge($historyAll, $page);
                $histOffset += 500;
            } while (count($page) === 500);

            // Deduplicate: keep one snapshot per calendar day (latest first = first seen)
            $seenDates = []; $histUniq = [];
            foreach ($historyAll as $row) {
                $d = substr($row['date'] ?? '', 0, 10);
                if (!isset($seenDates[$d])) { $seenDates[$d] = true; $histUniq[] = $row; }
            }
            $history = $histUniq;

            foreach (array_reverse($history) as $row) {
                $sparkLabels[] = substr($row['date'] ?? '', 0, 10);
                $sparkData[]   = (float)($row['pa'] ?? 0);
            }

            // Get symbol for financial enrichment
            // Try from latest history doc first (has symbol since scraper update)
            $symbol = null;
            foreach ($history as $row) {
                if (!empty($row['symbol'])) { $symbol = $row['symbol']; break; }
            }
            // Fallback: format collection
            if (!$symbol) {
                $fmtRes = aw_list_docs('format', [q_equal('name', $name), q_limit(1)]);
                if (!empty($fmtRes)) $symbol = $fmtRes[0]['symbol'] ?? null;
            }

            // ─── Dividends ───────────────────────────────────
            $divRows            = div_for_company($name);
            [$divNext, $divWhen] = div_next($divRows);
            $divHistory         = div_history($divRows, (int)date('Y'));
            $divUsualMonth      = ($divNext && !div_confirmed($divNext))
                                    ? div_usual_month($divRows, (int)date('Y')) : null;
            // Estimated ex-date, only for companies whose own history is regular
            // enough to support one. Shown as a window, never as a date.
            $divPredict         = ($divNext && !div_confirmed($divNext))
                                    ? div_predict($divRows, (int)date('Y')) : null;
            $divPrice           = (float)($history[0]['pa'] ?? 0);

            // ─── Projected year ──────────────────────────────
            // A reported year can be unrepresentative while the market prices
            // something else. IAM's 2024 is its Inwi-settlement year: PER 48
            // reported, ~12 on the 2025 projection. Both honest; showing only
            // the first, unlabelled, is what misleads. Computed from market cap
            // so the share count cannot poison it.
            $fyEst   = (int)($company['fy_est'] ?? 0);
            $rnpgEst = (float)($company['rnpg_est'] ?? 0);
            $perEst  = null;
            if ($fyEst && $rnpgEst > 0 && $divPrice > 0 && !empty($company['na'])) {
                $mcap   = $divPrice * (float)$company['na'];
                $perEst = $mcap / ($rnpgEst * 1e6);
                // Same ceiling the scraper applies: beyond it the number is an
                // artefact of a bad input, not a valuation worth showing.
                if ($perEst <= 0 || $perEst > MAX_PER) $perEst = null;
            }
            $perRep = null;
            if (!empty($company['net_profit']) && $divPrice > 0 && !empty($company['na'])) {
                $p = $divPrice * (float)$company['na'] / ((float)$company['net_profit'] * 1e6);
                if ($p > 0 && $p <= MAX_PER) $perRep = $p;
            }

            // Fundamentals older than this are a hazard on a live, trading stock.
            $fyStale = !empty($company['fiscal_year'])
                       && (int)$company['fiscal_year'] < (int)date('Y') - 2;
        }
    } catch (Throwable $e) {
        $dbError = $e->getMessage();
    }
}

// ─── Buy markers (shown when user is logged in) ───────────
$buyMarkers = [];
$awSession  = $_SESSION['aw_cookie'] ?? null;
if ($awSession && !empty($name ?? '')) {
    try {
        $uid = aw_user_id();
        if ($uid) {
            $achatsDocs = aw_list_docs('achats', [
                q_equal('c_name', $name),
                q_equal('user_id', $uid),
                q_order_asc('date'),
                q_limit(50),
            ], $awSession);
            foreach ($achatsDocs as $a) {
                $buyMarkers[] = [
                    'date'     => substr($a['date'] ?? '', 0, 10),
                    'price'    => (float)($a['price'] ?? 0),
                    'quantity' => (int)($a['quantity'] ?? 0),
                ];
            }
        }
    } catch (Throwable $e) { /* silently ignore — markers are optional */ }
}
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>myInterpreter | Consulter Action</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=4" rel="stylesheet">
  <link href="assets/css/infoAction.css?v=9" rel="stylesheet">
</head>
<body>
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">

  <div class="search-wrap">

    <?php if ($dbError): ?>
      <div class="alert alert-danger">
        <strong><i class="fas fa-bug me-2"></i>Erreur PHP/DB :</strong>
        <pre style="margin-top:8px;font-size:0.8rem;white-space:pre-wrap"><?= htmlspecialchars($dbError) ?></pre>
        <p class="mb-0 mt-2" style="font-size:0.82rem">
          Vérifiez que <code>stock.sql</code> a bien été importé et que les identifiants DB dans
          <code>config/config.php</code> sont corrects.
        </p>
      </div>
    <?php else: ?>

    <div class="search-hero">
      <h1><i class="fas fa-search t-emerald me-2"></i>Recherche Société</h1>
      <p>Consultez les ratios fondamentaux et l'historique des prix.</p>
    </div>

    <form method="POST" action="" data-loading>
      <div class="search-bar-wrap">
        <div class="form-floating flex-grow-1">
          <input type="text" name="NAME" id="nameInput" list="companyList"
                 class="form-control" placeholder=" " required autocomplete="off"
                 value="<?= htmlspecialchars($_POST['NAME'] ?? '') ?>">
          <label for="nameInput"><i class="fas fa-building me-2"></i>Nom de l'entreprise</label>
          <datalist id="companyList">
            <?php
              // Label = readable name + ticker, always in that order so the
              // symbol is where the eye expects it. The option's *value* stays
              // the stored name so selection still resolves exactly.
              // The only case worth suppressing is a label identical to the
              // symbol, which is what produced the useless "IAM — IAM"; a
              // substring test instead would strip the ticker from "CIH BANK".
              $symbolOf = array_flip($symbolTo);
              foreach ($allCompanies as $n):
                $sy    = $symbolOf[$n] ?? '';
                $label = $labelOf[$n] ?? $n;
                if ($sy && strcasecmp($label, $sy) !== 0) $label .= " — $sy";
            ?>
              <option value="<?= htmlspecialchars($n) ?>" label="<?= htmlspecialchars($label) ?>">
            <?php endforeach; ?>
          </datalist>
        </div>
        <button type="submit" class="btn btn-emerald" style="height:58px;padding:0 28px"
                data-loading-text="Recherche...">
          <i class="fas fa-search"></i> Afficher
        </button>
      </div>
    </form>

    <?php if ($searched): ?>
      <?php if (!$company): ?>
        <div class="alert alert-<?= $suggestions ? 'warning' : 'danger' ?>">
          <i class="fas fa-<?= $suggestions ? 'question-circle' : 'times-circle' ?> me-2"></i>
          <?php if ($suggestions): ?>
            Aucune correspondance exacte pour
            « <strong><?= htmlspecialchars($typed) ?></strong> ».
            Vouliez-vous dire :
            <div class="suggestion-list">
              <?php foreach ($suggestions as $s): ?>
                <a class="suggestion-chip" href="infoAction.php?name=<?= urlencode($s) ?>">
                  <?= htmlspecialchars($s) ?>
                  <?php if (!empty(array_flip($symbolTo)[$s])): ?>
                    <span class="mono muted"><?= htmlspecialchars(array_flip($symbolTo)[$s]) ?></span>
                  <?php endif; ?>
                </a>
              <?php endforeach; ?>
            </div>
          <?php else: ?>
            Entreprise introuvable pour
            « <strong><?= htmlspecialchars($typed) ?></strong> ».
            Essayez le nom complet ou le symbole boursier (ex.&nbsp;<span class="mono">ATW</span>).
          <?php endif; ?>
        </div>
      <?php else: ?>
        <div class="search-result">

          <!-- Company header -->
          <div class="company-header mb-4">
            <div class="company-title-row">
              <div>
                <h4 class="company-name">
                  <?php if ($symbol): ?>
                    <span class="ticker-badge"><?= htmlspecialchars($symbol) ?></span>
                  <?php endif; ?>
                  <?= htmlspecialchars(display_name($company['name'] ?? $name, $company['ext_name'] ?? null)) ?>
                  <?php if (!empty($company['sector'])): ?>
                    <span class="sector-badge"><?= htmlspecialchars($company['sector']) ?></span>
                  <?php endif; ?>
                  <?php if (!empty($company['fiscal_year'])): ?>
                    <?php // Every figure below comes from this one financial year.
                          // Shown once rather than repeated on each metric. ?>
                    <span class="fy-badge"
                          data-tooltip="Tous les chiffres financiers ci-dessous proviennent de l'exercice <?= (int)$company['fiscal_year'] ?>. Les ratios (PER, PEG, P/R, P/B) combinent ces comptes avec le cours actuel.">
                      Exercice <?= (int)$company['fiscal_year'] ?>
                    </span>
                  <?php endif; ?>
                </h4>
                <?php if (!empty($company['description'])): ?>
                  <?php $desc = $company['description']; $descShort = mb_substr($desc, 0, 280); $hasMore = mb_strlen($desc) > 280; ?>
                  <p class="company-desc" id="companyDescText">
                    <span class="desc-short"><?= htmlspecialchars($descShort) ?><?= $hasMore ? '…' : '' ?></span>
                    <?php if ($hasMore): ?>
                      <span class="desc-full" hidden><?= htmlspecialchars($desc) ?></span>
                      <button class="desc-more-btn" onclick="toggleDesc(this)" aria-expanded="false">
                        <span class="desc-more-label">Lire la suite</span>
                        <i class="fas fa-chevron-down desc-more-icon"></i>
                      </button>
                    <?php endif; ?>
                  </p>
                <?php endif; ?>
              </div>
            </div>

            <!-- Fundamentals grid -->
            <?php if (!empty($company['fiscal_year'])): ?>
              <p class="fund-source">
                <i class="fas fa-calendar-alt me-1"></i>
                Chiffres financiers : <strong>exercice <?= (int)$company['fiscal_year'] ?></strong>
                <span class="muted">· source fundamentals.example · les ratios combinent ces comptes avec le cours du jour</span>
              </p>
            <?php endif; ?>

            <?php if ($fyStale): ?>
              <div class="fy-stale">
                <i class="fas fa-triangle-exclamation me-2"></i>
                <div>
                  <strong>Comptes vieux de <?= (int)date('Y') - (int)$company['fiscal_year'] ?> ans.</strong>
                  Cette société est toujours cotée, mais n'a rien publié depuis
                  l'exercice <?= (int)$company['fiscal_year'] ?>.
                  <span class="muted">Les ratios ci-dessous rapprochent le cours d'aujourd'hui
                  de comptes périmés — traitez-les comme indicatifs, pas comme une valorisation.</span>
                </div>
              </div>
            <?php endif; ?>

            <?php if ($perEst !== null && $fyEst): ?>
              <div class="per-est">
                <div class="per-est-row">
                  <div class="per-est-cell">
                    <span class="per-est-lbl">PER publié <?= (int)$company['fiscal_year'] ?></span>
                    <span class="per-est-val"><?= $perRep !== null ? number_format($perRep, 1, ',', ' ') : '—' ?></span>
                  </div>
                  <i class="fas fa-arrow-right per-est-arrow"></i>
                  <div class="per-est-cell">
                    <span class="per-est-lbl">PER sur prévision <?= $fyEst ?></span>
                    <span class="per-est-val is-est"><?= number_format($perEst, 1, ',', ' ') ?></span>
                  </div>
                </div>
                <p class="per-est-note">
                  <i class="fas fa-info-circle me-1"></i>
                  <?= $fyEst ?> est une <strong>prévision</strong> d'the fundamentals provider, pas un résultat publié
                  (<?= number_format($rnpgEst, 0, ',', ' ') ?> MMAD de bénéfice attendu).
                  <span class="muted">Elle n'entre dans aucun ratio du site — les colonnes PER, PEG, P/R et P/B
                  restent calculées sur l'exercice <?= (int)$company['fiscal_year'] ?>.
                  Affichée ici parce qu'une année publiée peut être atypique&nbsp;: un litige, une cession
                  ou une provision exceptionnelle déforme le PER sans rien dire de l'activité.</span>
                </p>
              </div>
            <?php endif; ?>
            <div class="fundamentals-grid">
              <?php
              $funds = [
                  'BPA'  => ['key' => 'BPA',   'tip' => 'Bénéfice Par Action',             'val' => $company['bpa'] ?? null,          'unit' => 'MAD'],
                  'DPA'  => ['key' => 'DPA',   'tip' => 'Dividende Par Action',             'val' => $company['dpa'] ?? null,          'unit' => 'MAD'],
                  'TC5'  => ['key' => 'TC5',   'tip' => 'Croissance CA sur 5 ans (TCAC)',   'val' => $company['tc5'] ?? null,          'unit' => '%'],
                  'ROE'  => ['key' => 'ROE',   'tip' => 'Rentabilité des capitaux propres', 'val' => $company['roe'] ?? null,          'unit' => '%'],
                  'NA'   => ['key' => 'NA',    'tip' => "Nombre d'actions en circulation",  'val' => $company['na'] ?? null,           'unit' => ''],
                  'β3Y'  => ['key' => 'β3Y',   'tip' => 'Bêta sur 3 ans (volatilité rel.)', 'val' => $company['beta_3y'] ?? null,     'unit' => ''],
                  'CA'   => ['key' => 'CA',    'tip' => "Chiffre d'Affaires (dernière année)",'val' => $company['revenue'] ?? null,    'unit' => 'M'],
                  'RNPG' => ['key' => 'RNPG',  'tip' => 'Résultat Net Part du Groupe',      'val' => $company['net_profit'] ?? null,   'unit' => 'M'],
                  'DN'   => ['key' => 'DN',    'tip' => 'Dette Nette (dettes – trésorerie)', 'val' => $company['net_debt'] ?? null,    'unit' => 'M'],
                  'Marge'=> ['key' => 'Marge', 'tip' => 'Marge Nette (RNPG / CA)',          'val' => $company['profit_margin'] ?? null,'unit' => '%'],
              ];
              foreach ($funds as $f):
                  if ($f['val'] === null) continue;
                  $v = is_numeric($f['val']) ? number_format((float)$f['val'], 2, ',', ' ') : $f['val'];
              ?>
              <div class="fund-chip" data-tooltip="<?= htmlspecialchars($f['tip']) ?>">
                <span class="fund-label"><?= $f['key'] ?></span>
                <span class="fund-val"><?= $v ?><?= $f['unit'] ? '<span class="fund-unit"> '.$f['unit'].'</span>' : '' ?></span>
              </div>
              <?php endforeach; ?>
            </div>
          </div>

          <?php if (!empty($history)): ?>

            <?php if (count($sparkData) > 1): ?>
            <div class="sparkline-wrap mb-4">
              <div class="spark-header">
                <h5><i class="fas fa-chart-line me-2 t-cyan"></i>Évolution du prix (PA)</h5>
                <div class="spark-hover-val" id="sparkHoverVal"></div>
                <div class="spark-period-btns">
                  <?php foreach (['5A'=>'5A','1A'=>'1A','6M'=>'6M','3M'=>'3M','1M'=>'1M'] as $k=>$v): ?>
                    <button class="spark-period-btn<?= $k==='1A'?' active':'' ?>" data-period="<?= $k ?>"><?= $v ?></button>
                  <?php endforeach; ?>
                </div>
              </div>
              <div class="spark-canvas-wrap">
                <canvas id="sparklineChart" height="200"></canvas>
              </div>
              <div class="masi-slider-wrap">
                <input type="range" id="sliderStart" min="0" max="100" value="0">
                <input type="range" id="sliderEnd"   min="0" max="100" value="100">
              </div>
            </div>
            <?php endif; ?>

            <?php if ($symbol): ?>
            <!-- Financial enrichment (JS-loaded) -->
            <div id="mkt-enrichment" class="mb-4">
              <div id="mkt-loading" style="padding:24px;text-align:center;color:var(--text-faint);font-size:13px">
                <i class="fas fa-circle-notch fa-spin me-2"></i>Chargement données financières…
              </div>
            </div>
            <?php endif; ?>

            <?php
              // The snapshot table used to render every stored day — 795 rows for
              // IAM, a 564 KB page. The chart above already covers the same ground
              // with period buttons, so the table now shows a recent window and
              // says so rather than pretending to be the full record.
              $SNAP_WINDOW  = 60;
              $historyShown = array_slice($history, 0, $SNAP_WINDOW);
            ?>
            <div class="panel-tabs" role="tablist">
              <button class="panel-tab active" data-panel="snapshots" role="tab" aria-selected="true">
                <i class="fas fa-history me-2"></i>Historique des snapshots
              </button>
              <button class="panel-tab" data-panel="dividendes" role="tab" aria-selected="false">
                <i class="fas fa-coins me-2"></i>Dividendes
                <?php if ($divNext && !empty($divNext['amount'])): ?>
                  <span class="tab-badge"><?= number_format((float)$divNext['amount'], 2, ',', ' ') ?></span>
                <?php endif; ?>
              </button>
            </div>

            <!-- ── Dividendes ─────────────────────────────── -->
            <div class="panel-body" id="panel-dividendes" hidden>
              <?php if (!$divRows): ?>
                <div class="alert alert-info mb-0">
                  <i class="fas fa-info-circle me-2"></i>
                  Aucun dividende connu pour cette société.
                  <span class="muted">Elle ne figure pas au calendrier de distribution.</span>
                </div>
              <?php else: ?>
                <?php if ($divNext): ?>
                  <?php
                    $amt   = (float)($divNext['amount'] ?? 0);
                    $yield = div_yield($divNext, $divPrice);
                    $conf  = div_confirmed($divNext);
                    $isQ   = strcasecmp((string)($divNext['frequency'] ?? ''), 'Trimestriel') === 0;
                  ?>
                  <div class="div-card <?= $divWhen === 'past' ? 'is-past' : '' ?>">
                    <div class="div-head">
                      <div>
                        <div class="div-label">
                          <?= $divWhen === 'past' ? 'Dernier dividende versé' : 'Prochain dividende' ?>
                          <?php if ($divNext['type'] && stripos($divNext['type'], 'exceptionnel') !== false): ?>
                            <span class="div-tag-exc"><?= htmlspecialchars($divNext['type']) ?></span>
                          <?php endif; ?>
                        </div>
                        <div class="div-amount">
                          <?= $amt > 0 ? number_format($amt, 2, ',', ' ') : '—' ?>
                          <span class="div-unit">MAD<?= $isQ ? '/an' : '/action' ?></span>
                        </div>
                      </div>
                      <?php if ($yield !== null): ?>
                        <div class="div-yield">
                          <div class="div-yield-val"><?= number_format($yield, 2, ',', ' ') ?>&nbsp;%</div>
                          <div class="div-yield-lbl">rendement</div>
                        </div>
                      <?php endif; ?>
                    </div>

                    <div class="div-dates">
                      <div class="div-date-cell">
                        <span class="div-date-lbl">Détachement</span>
                        <?php if (!empty($divNext['ex_date'])): ?>
                          <span class="div-date-val"><?= fmt_date($divNext['ex_date']) ?></span>
                        <?php elseif ($divPredict): ?>
                          <span class="div-date-val is-est"><?= div_fmt_window($divPredict) ?></span>
                        <?php else: ?>
                          <span class="div-date-val">—</span>
                        <?php endif; ?>
                      </div>
                      <div class="div-date-cell">
                        <span class="div-date-lbl">Paiement</span>
                        <span class="div-date-val"><?= div_fmt_date($divNext) ?></span>
                      </div>
                      <div class="div-date-cell">
                        <span class="div-date-lbl">Statut</span>
                        <?php if ($conf): ?>
                          <span class="div-badge confirmed"><i class="fas fa-check me-1"></i>Confirmé</span>
                        <?php else: ?>
                          <span class="div-badge estimated"><i class="fas fa-clock me-1"></i>Prévu</span>
                        <?php endif; ?>
                      </div>
                    </div>

                    <?php if (!$conf): ?>
                      <?php if ($divPredict): ?>
                        <div class="div-forecast">
                          <div class="div-forecast-head">
                            <i class="fas fa-wand-magic-sparkles me-2"></i>
                            Détachement estimé :
                            <strong><?= div_fmt_window($divPredict) ?></strong>
                            <span class="div-badge <?= $divPredict['tight'] ? 'confirmed' : 'estimated' ?>">
                              <?= $divPredict['tight'] ? 'très régulier' : 'régulier' ?>
                            </span>
                          </div>
                          <p class="div-forecast-body">
                            Calculé sur <strong><?= $divPredict['years'] ?> années</strong> de versements,
                            dont les dates n'ont varié que de <strong><?= $divPredict['spread'] ?> jours</strong>.
                            Paiement attendu vers le <strong><?= fmt_date($divPredict['pay']) ?></strong>
                            (environ 10 jours après le détachement).
                            <span class="muted">Estimation, pas un engagement : testée sur l'an dernier,
                            elle tombe dans la fenêtre annoncée 8 fois sur 10. Une société peut toujours
                            déplacer son assemblée générale.</span>
                          </p>
                        </div>
                      <?php else: ?>
                        <p class="div-note">
                          <i class="fas fa-info-circle me-1"></i>
                          Date non encore votée en assemblée générale — l'estimation vient de la source.
                          <?php if ($divUsualMonth): ?>
                            Cette société verse habituellement en <strong><?= htmlspecialchars($divUsualMonth) ?></strong>,
                            mais ses dates varient trop d'une année à l'autre pour aller plus loin.
                          <?php else: ?>
                            Son historique est trop irrégulier pour estimer une date.
                          <?php endif; ?>
                        </p>
                      <?php endif; ?>
                    <?php endif; ?>
                    <?php if ($isQ): ?>
                      <p class="div-note">
                        <i class="fas fa-repeat me-1"></i>
                        Versement <strong>trimestriel</strong> — le montant indiqué est le total annuel.
                      </p>
                    <?php endif; ?>
                  </div>
                <?php endif; ?>

                <?php if ($divHistory): ?>
                  <h6 class="div-hist-title">Historique des versements</h6>
                  <div class="card-glass overflow-x-auto">
                    <table class="tbl">
                      <thead><tr>
                        <th>ANNÉE</th><th class="num">MONTANT</th>
                        <th class="num">VARIATION</th><th>DÉTACHEMENT</th><th>PAIEMENT</th>
                      </tr></thead>
                      <tbody>
                      <?php
                        $byYear = [];
                        foreach ($divRows as $r) $byYear[(int)$r['year']][] = $r;
                        krsort($byYear);
                        $prevAmt = null;
                        // Oldest-first pass to compute year-on-year change, then render newest-first.
                        $ordered = array_reverse($byYear, true);
                        $delta = [];
                        foreach ($ordered as $y => $rs) {
                            $tot = 0; foreach ($rs as $r) $tot += (float)($r['amount'] ?? 0);
                            $delta[$y] = ($prevAmt !== null && $prevAmt > 0 && $tot > 0)
                                       ? ($tot - $prevAmt) / $prevAmt * 100 : null;
                            if ($tot > 0) $prevAmt = $tot;
                        }
                        foreach ($byYear as $y => $rs):
                          $tot = 0; foreach ($rs as $r) $tot += (float)($r['amount'] ?? 0);
                          $r0  = $rs[0];
                          $dv  = $delta[$y] ?? null;
                      ?>
                        <tr<?= $y === (int)date('Y') ? ' class="div-row-current"' : '' ?>>
                          <td class="mono"><?= $y ?><?= $y === (int)date('Y') ? ' <span class="muted">(en cours)</span>' : '' ?></td>
                          <td class="num mono"><?= $tot > 0 ? number_format($tot, 2, ',', ' ') : '—' ?></td>
                          <td class="num mono <?= $dv === null ? '' : ($dv >= 0 ? 'c-green' : 'c-red') ?>">
                            <?= $dv === null ? '—' : ($dv >= 0 ? '+' : '') . number_format($dv, 1, ',', ' ') . '&nbsp;%' ?>
                          </td>
                          <td class="date"><?= fmt_date($r0['ex_date'] ?? '', '—') ?></td>
                          <td class="date"><?= div_fmt_date($r0) ?></td>
                        </tr>
                      <?php endforeach; ?>
                      </tbody>
                    </table>
                  </div>
                <?php endif; ?>

                <p class="fund-source mt-3">
                  <i class="fas fa-calendar-alt me-1"></i>
                  Calendrier de distribution · <strong>source calendar.example</strong>
                  <span class="muted">· le dividende versé en <?= date('Y') ?> provient de l'exercice <?= date('Y') - 1 ?></span>
                </p>
              <?php endif; ?>
            </div>

            <!-- ── Snapshots ──────────────────────────────── -->
            <div class="panel-body" id="panel-snapshots">
            <p class="fund-source">
              <i class="fas fa-clock-rotate-left me-1"></i>
              <?= count($historyShown) ?> derniers jours
              <span class="muted">sur <?= number_format(count($history), 0, ',', ' ') ?> enregistrés ·
              l'évolution complète est dans le graphique ci-dessus</span>
            </p>
            <div class="card-glass overflow-x-auto">
              <table class="tbl">
                <thead><tr>
                  <th>DATE</th>
                  <th class="num">PA</th>
                  <th class="num">CB</th>
                  <th class="num col-per">PER</th>
                  <th class="num col-peg">PEG</th>
                  <th class="num col-pr">P/R</th>
                  <th class="num col-pb">P/B</th>
                </tr></thead>
                <tbody>
                  <?php foreach ($historyShown as $row):
                    $per = (float)($row['per'] ?? 0);
                    $peg = (float)($row['peg'] ?? 0);
                    $pr  = (float)($row['pr']  ?? 0);
                    $pb  = (float)($row['pb']  ?? 0);
                    $perColor = $per == 0 ? 'none' : ($per < PER_GREEN ? 'green' : ($per < PER_ORANGE ? 'orange' : 'red'));
                    $pegColor = $peg <= 0 ? 'none' : ($peg < PEG_GREEN ? 'green' : ($peg < PEG_ORANGE ? 'orange' : 'red'));
                    $prColor  = $pr  == 0 ? 'none' : ($pr  < PR_GREEN  ? 'green' : ($pr  < PR_ORANGE  ? 'orange' : 'red'));
                    $pbColor  = $pb  == 0 ? 'none' : ($pb  < PB_GREEN  ? 'green' : ($pb  < PB_ORANGE  ? 'orange' : 'red'));
                  ?>
                  <tr>
                    <td class="date"><?= fmt_date($row['date'] ?? '') ?></td>
                    <td class="num mono"><?= number_format((float)($row['pa'] ?? 0), 2) ?></td>
                    <td class="num mono"><?= number_format((float)($row['cb'] ?? 0), 0, ',', ' ') ?></td>
                    <td class="num mono col-per c-<?= $perColor ?>">
                      <?= $per == 0 ? '—' : number_format($per, 2) ?>
                    </td>
                    <td class="num mono col-peg c-<?= $pegColor ?>">
                      <?= $peg == 0 ? '—' : number_format($peg, 2) ?>
                    </td>
                    <td class="num mono col-pr c-<?= $prColor ?>">
                      <?= $pr == 0 ? '—' : number_format($pr, 2) ?>
                    </td>
                    <td class="num mono col-pb c-<?= $pbColor ?>">
                      <?= $pb == 0 ? '—' : number_format($pb, 2) ?>
                    </td>
                  </tr>
                  <?php endforeach; ?>
                </tbody>
              </table>
            </div>
            </div><!-- /panel-snapshots -->

          <?php else: ?>
            <div class="alert alert-info">
              <i class="fas fa-info-circle me-2"></i>
              Aucun snapshot pour cette société. Utilisez
              <a href="Update.php" class="t-cyan">Update Stock</a> pour en créer un.
            </div>
          <?php endif; ?>

        </div>
      <?php endif; ?>
    <?php endif; ?>

    <?php endif; ?>

  </div>
  </main>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="assets/js/app.js"></script>

<?php if ($symbol ?? null): ?>
<script>
(async function() {
  const sym = <?= json_encode($symbol) ?>;
  const container = document.getElementById('mkt-enrichment');
  if (!container) return;

  try {
    const r   = await fetch('handlers/market_proxy.php?symbol=' + encodeURIComponent(sym));
    const d   = await r.json();
    const c   = d.computed || {};
    const ch  = d.charts   || {};

    let html = '';

    // Description
    if (d.description) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-info-circle me-2 t-cyan"></i>À propos</div>
        <p class="mkt-desc">${d.description.replace(/\r\n|\n/g,'<br>')}</p>
      </div>`;
    }

    // Financial charts
    const caData = ch.ca || {}; const rnpgData = ch.rnpg || {}; const ebeData = ch.ebe || {};
    const allYears = [...new Set([...Object.keys(caData), ...Object.keys(rnpgData), ...Object.keys(ebeData)])].sort();
    if (allYears.length > 0) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-chart-bar me-2 t-violet"></i>Résultats annuels (MMAD)</div>
        <div class="mkt-chart-wrap"><canvas id="finChart"></canvas></div>
      </div>`;
    }

    // Quarterly CA
    const trim = d.trim;
    if (trim) {
      const qKeys = Object.keys(trim).filter(k => /^T\d\d{4}$/.test(k)).sort();
      if (qKeys.length > 0) {
        html += `<div class="mkt-section">
          <div class="mkt-section-title"><i class="fas fa-calendar-alt me-2 t-amber"></i>Chiffre d'affaires trimestriel (MMAD)</div>
          <div class="mkt-chart-wrap"><canvas id="trimChart"></canvas></div>
        </div>`;
      }
    }

    // Shareholders
    if (d.shareholders && d.shareholders.length > 0) {
      html += `<div class="mkt-section">
        <div class="mkt-section-title"><i class="fas fa-users me-2 t-emerald"></i>Actionnariat</div>
        <div class="mkt-two-col">
          <canvas id="holdersChart" style="max-height:220px"></canvas>
          <div class="holders-list" id="holders-list"></div>
        </div>
      </div>`;
    }

    container.innerHTML = html || '<div style="color:var(--text-faint);font-size:13px;padding:12px">Aucune donnée financière disponible pour cette société.</div>';

    // Shared crosshair plugin for bar/line charts
    const barCrosshair = {
      id: 'barCrosshair',
      afterDraw(chart) {
        const active = chart.tooltip && chart.tooltip._active;
        if (!active || !active.length) return;
        const x = active[0].element.x;
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.strokeStyle = 'rgba(148,163,184,0.4)';
        ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.restore();
      }
    };

    // Draw financial chart
    if (allYears.length > 0) {
      const projYears = allYears.filter(y => y.endsWith('p'));
      const colors = y => projYears.includes(y) ? 'rgba(34,211,238,0.4)' : '#22d3ee';
      new Chart(document.getElementById('finChart').getContext('2d'), {
        type: 'bar',
        plugins: [barCrosshair],
        data: {
          labels: allYears,
          datasets: [
            { label: 'CA', data: allYears.map(y => caData[y]   ?? null), backgroundColor: allYears.map(y => projYears.includes(y) ? 'rgba(34,211,238,0.25)' : 'rgba(34,211,238,0.6)'), borderRadius: 4, order: 2 },
            { label: 'EBE', data: allYears.map(y => ebeData[y] ?? null), backgroundColor: allYears.map(y => projYears.includes(y) ? 'rgba(129,140,248,0.25)' : 'rgba(129,140,248,0.55)'), borderRadius: 4, order: 2 },
            { label: 'RNPG', data: allYears.map(y => rnpgData[y] ?? null), type: 'line', borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.12)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#10b981', tension: 0.3, fill: true, order: 1 },
          ]
        },
        options: {
          responsive: true,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 12 } } },
            tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw !== null ? c.raw.toFixed(2) : '—'} M` } }
          },
          scales: {
            x: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } },
            y: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } }
          }
        }
      });
    }

    // Draw quarterly chart
    if (trim) {
      const qKeys = Object.keys(trim).filter(k => /^T\d\d{4}$/.test(k)).sort().slice(-12);
      if (qKeys.length > 0 && document.getElementById('trimChart')) {
        new Chart(document.getElementById('trimChart').getContext('2d'), {
          type: 'bar',
          plugins: [barCrosshair],
          data: {
            labels: qKeys.map(k => k.replace('T','Q').replace(/(\d)(\d{4})/, '$1 $2')),
            datasets: [{ label: 'CA', data: qKeys.map(k => trim[k] ?? null), backgroundColor: 'rgba(245,158,11,0.55)', borderRadius: 4 }]
          },
          options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } },
              y: { ticks: { color: '#475569' }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
          }
        });
      }
    }

    // Shareholders chart
    if (d.shareholders && d.shareholders.length > 0 && document.getElementById('holdersChart')) {
      const colors = ['#22d3ee','#818cf8','#10b981','#f59e0b','#f43f5e','#6ee7b7','#fb7185','#fbbf24'];
      new Chart(document.getElementById('holdersChart').getContext('2d'), {
        type: 'doughnut',
        data: {
          labels: d.shareholders.map(h => h.name),
          datasets: [{ data: d.shareholders.map(h => h.pct), backgroundColor: colors.slice(0, d.shareholders.length), borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false } }
        }
      });
      const list = document.getElementById('holders-list');
      list.innerHTML = d.shareholders.map((h, i) =>
        `<div class="holder-row"><span class="holder-dot" style="background:${colors[i % colors.length]}"></span><span class="holder-name">${h.name}</span><span class="holder-pct">${h.pct.toFixed(1)}%</span></div>`
      ).join('');
    }

  } catch (e) {
    document.getElementById('mkt-enrichment').innerHTML =
      `<div style="color:var(--text-faint);font-size:13px;padding:12px">Données financières indisponibles.</div>`;
  }
})();
</script>
<?php endif; ?>

<?php if (!empty($sparkData) && count($sparkData) > 1): ?>
<script>
(function() {
  var fullLabels = <?= json_encode($sparkLabels) ?>;
  var fullData   = <?= json_encode($sparkData) ?>;
  var buyMarkers = <?= json_encode($buyMarkers) ?>;

  var currentSlice = fullLabels.map((d, i) => ({ d, v: fullData[i] }));
  var sliderStart  = document.getElementById('sliderStart');
  var sliderEnd    = document.getElementById('sliderEnd');
  var hoverVal     = document.getElementById('sparkHoverVal');

  // ── period filter ─────────────────────────────────────────
  var periodDays = { '5A': 5*365, '1A': 365, '6M': 182, '3M': 91, '1M': 30 };

  function dateStr(daysAgo) {
    var d = new Date(); d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  }

  function setPeriod(period) {
    var cutoff = dateStr(periodDays[period]);
    var filtered = fullLabels.map((d, i) => ({ d, v: fullData[i] })).filter(p => p.d >= cutoff);
    currentSlice = filtered.length >= 2 ? filtered : fullLabels.map((d, i) => ({ d, v: fullData[i] }));
    sliderStart.value = 0; sliderEnd.value = 100;
    renderChart(currentSlice);
  }

  document.querySelectorAll('.spark-period-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.spark-period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      setPeriod(btn.dataset.period);
    });
  });

  // ── sliders ───────────────────────────────────────────────
  function slicedData() {
    var s = parseInt(sliderStart.value), e = parseInt(sliderEnd.value);
    if (s > e - 2) { s = Math.max(0, e - 2); sliderStart.value = s; }
    var n = currentSlice.length;
    var from = Math.floor(s / 100 * (n - 1));
    var to   = Math.ceil(e  / 100 * (n - 1));
    return currentSlice.slice(from, to + 1);
  }

  [sliderStart, sliderEnd].forEach(function(sl) {
    sl.addEventListener('input', function() { renderChart(slicedData()); });
  });

  // ── crosshair plugin ──────────────────────────────────────
  // Snap to the active tooltip data point x so it's always aligned.
  var crosshairPlugin = {
    id: 'crosshair',
    afterDraw: function(chart) {
      var active = chart.tooltip && chart.tooltip._active;
      if (!active || !active.length) return;
      var x = active[0].element.x;
      var c = chart.ctx, ca = chart.chartArea;
      c.save();
      c.strokeStyle = 'rgba(148,163,184,0.5)';
      c.lineWidth = 1;
      c.setLineDash([4, 4]);
      c.beginPath(); c.moveTo(x, ca.top); c.lineTo(x, ca.bottom); c.stroke();
      c.restore();
    },
    afterEvent: function(chart, args) {
      if (args.event.type === 'mouseout') {
        hoverVal.textContent = '';
        chart.draw();
      }
    }
  };

  // ── buy-pin plugin ────────────────────────────────────────
  var buyPinPlugin = {
    id: 'buyPin',
    afterDraw: function(chart) {
      if (!buyMarkers.length) return;
      var c = chart.ctx, ca = chart.chartArea, scales = chart.scales;
      var chartLabels = chart.data.labels;
      buyMarkers.forEach(function(marker) {
        var idx = chartLabels.indexOf(marker.date);
        if (idx === -1) return;
        var x = scales.x.getPixelForValue(idx);
        c.save();
        c.setLineDash([4, 3]);
        c.strokeStyle = 'rgba(6,182,212,0.65)'; c.lineWidth = 1.5;
        c.beginPath(); c.moveTo(x, ca.top); c.lineTo(x, ca.bottom); c.stroke();
        c.setLineDash([]);
        c.fillStyle = '#06b6d4';
        c.beginPath(); c.moveTo(x, ca.top+3); c.lineTo(x-5, ca.top-6); c.lineTo(x+5, ca.top-6); c.closePath(); c.fill();
        c.fillStyle = '#06b6d4'; c.font = 'bold 9px sans-serif'; c.textAlign = 'center';
        c.fillText('Achat', x, ca.top - 9);
        c.restore();
      });
    }
  };

  // ── chart instance ────────────────────────────────────────
  var chartInst = null;

  function renderChart(slice) {
    var lbls = slice.map(p => p.d);
    var vals = slice.map(p => p.v);
    var first = vals[0], last = vals[vals.length - 1];
    var color = last >= first ? '#10b981' : '#f43f5e';
    var gradColor = last >= first ? 'rgba(16,185,129,' : 'rgba(244,63,94,';

    if (chartInst) {
      chartInst.data.labels = lbls;
      chartInst.data.datasets[0].data = vals;
      chartInst.data.datasets[0].borderColor = color;
      chartInst.data.datasets[0].pointBackgroundColor = color;
      chartInst.data.datasets[0].pointRadius = vals.length < 25 ? 4 : 0;
      chartInst.data.datasets[0].backgroundColor = function(ctx) {
        var g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
        g.addColorStop(0, gradColor + '0.18)');
        g.addColorStop(1, 'rgba(0,0,0,0)');
        return g;
      };
      chartInst.update('none');
      return;
    }

    var ctxEl = document.getElementById('sparklineChart').getContext('2d');
    chartInst = new Chart(ctxEl, {
      type: 'line',
      plugins: [crosshairPlugin, buyPinPlugin],
      data: {
        labels: lbls,
        datasets: [{
          data: vals,
          borderColor: color,
          borderWidth: 2,
          pointRadius: vals.length < 25 ? 4 : 0,
          pointHoverRadius: 5,
          pointBackgroundColor: color,
          fill: true,
          backgroundColor: function(ctx) {
            var g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
            g.addColorStop(0, gradColor + '0.18)');
            g.addColorStop(1, 'rgba(0,0,0,0)');
            return g;
          },
          tension: 0.35,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(15,23,42,0.92)',
            titleColor: '#94a3b8',
            bodyColor: '#f1f5f9',
            borderColor: 'rgba(148,163,184,0.15)',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              title: function(items) { return items[0].label; },
              label: function(c) {
                hoverVal.textContent = c.raw.toFixed(2) + ' MAD  •  ' + c.label;
                var line = ' PA : ' + c.raw.toFixed(2) + ' MAD';
                var m = buyMarkers.find(b => b.date === lbls[c.dataIndex]);
                if (m) line += '   •   Achat ' + m.quantity + ' × ' + m.price.toFixed(2) + ' MAD';
                return line;
              }
            }
          }
        },
        scales: {
          x: { ticks: { color: '#475569', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { ticks: { color: '#475569' },                   grid: { color: 'rgba(255,255,255,0.04)' } }
        }
      }
    });
  }

  // ── init with 1Y ─────────────────────────────────────────
  setPeriod('1A');
})();
</script>
<?php endif; ?>
<script>
// Panel tabs: snapshots vs dividends. Both panels are in the DOM already, so
// switching is instant and needs no request.
document.querySelectorAll('.panel-tab').forEach(function (tab) {
  tab.addEventListener('click', function () {
    var want = tab.dataset.panel;
    document.querySelectorAll('.panel-tab').forEach(function (t) {
      var on = t === tab;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.panel-body').forEach(function (p) {
      p.hidden = (p.id !== 'panel-' + want);
    });
  });
});

function toggleDesc(btn) {
  const p     = btn.closest('.company-desc');
  const short = p.querySelector('.desc-short');
  const full  = p.querySelector('.desc-full');
  const open  = btn.getAttribute('aria-expanded') === 'true';
  short.hidden = !open;
  full.hidden  = open;
  btn.setAttribute('aria-expanded', String(!open));
}
</script>
</body>
</html>
