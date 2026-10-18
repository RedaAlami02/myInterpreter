<?php
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/Action.php';
require_once 'core/dividends.php';
require_once 'core/sector_allocation.php';

$companyDocs = [];
$allCompanies = [];
$labelOf = [];
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
    $directoryRequests = [
        'companies' => ['company', [q_order_asc('name'), q_limit(500)], null],
        'symbols' => ['format', [q_limit(500)], null],
    ];
    // The directory needs prices, but a company detail request does not.
    if (empty($_GET['name']) && empty($_POST['NAME'])) {
        $directoryRequests['prices'] = ['latest_prices', [q_limit(200)], null];
    }
    $directoryData = aw_multi_list_docs($directoryRequests);
    $companyDocs = $directoryData['companies'];
    $allCompanies = array_values(array_unique(array_filter(array_column($companyDocs, 'name'))));

    // Readable label per company, for the search dropdown only — never a key.
    $labelOf = [];
    foreach ($companyDocs as $c) {
        $n = trim($c['name'] ?? '');
        if ($n !== '') $labelOf[$n] = display_name($n, $c['ext_name'] ?? null);
    }

    // Symbols power ticker lookup ("ATW") and the datalist hints.
    foreach ($directoryData['symbols'] as $f) {
        if (!empty($f['symbol']) && !empty($f['name'])) $symbolTo[$f['symbol']] = $f['name'];
    }
} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

$symbolOf = array_flip($symbolTo);
$directoryBySector = market_sector_directory($allCompanies);
$sectorParam = $_GET['sector'] ?? '';
$selectedSector = is_string($sectorParam) ? strtoupper(trim($sectorParam)) : '';
if (!isset($directoryBySector[$selectedSector])) $selectedSector = '';
$directoryCount = $selectedSector === '' ? count($allCompanies) : count($directoryBySector[$selectedSector]);
$directoryFilterParams = [];
if ($selectedSector !== '') $directoryFilterParams['sector'] = $selectedSector;
foreach (['price_min', 'price_max'] as $param) {
    if (isset($_GET[$param]) && is_scalar($_GET[$param]) && is_numeric($_GET[$param])) {
        $directoryFilterParams[$param] = max(0, (float)$_GET[$param]);
    }
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
        $companyRes = $resolved['name'] === null ? [] : array_values(array_filter(
            $companyDocs, fn($doc) => ($doc['name'] ?? '') === $name
        ));
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
                $symbol = array_flip($symbolTo)[$name] ?? null;
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

$directoryPrices = [];
$directoryPriceCeiling = 100;
if (!$searched && !$dbError) {
    try {
        $companySet = array_fill_keys($allCompanies, true);
        foreach (($directoryData['prices'] ?? aw_list_docs('latest_prices', [q_limit(200)])) as $priceDoc) {
            $priceName = $priceDoc['c_name'] ?? '';
            $price = (float)($priceDoc['pa'] ?? 0);
            if (isset($companySet[$priceName]) && $price > 0) $directoryPrices[$priceName] = $price;
        }
        if ($directoryPrices) {
            $directoryPriceCeiling = max(100, (int)(ceil(max($directoryPrices) / 100) * 100));
        }
    } catch (Throwable $e) {
        error_log('[myInterpreter] directory latest_prices error: ' . $e->getMessage());
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
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/infoAction.css?v=11" rel="stylesheet">
  <?php require 'core/theme.php'; ?>
</head>
<body class="workspace workspace-company">
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
      <h1><i class="fas fa-building t-emerald me-2"></i>Sociétés cotées</h1>
      <p>Parcourez les sociétés par secteur, ou recherchez une fiche et son historique.</p>
    </div>

    <?php if (!$searched): ?>
      <section class="directory-filters" id="companyDirectory" aria-label="Filtres des sociétés">
        <div class="directory-filters__head">
          <div><span class="directory-filters__eyebrow">EXPLORER LE MARCHÉ</span><h2>Affiner les sociétés</h2></div>
          <span class="directory-count" id="directoryCount"><?= $directoryCount ?> société<?= $directoryCount > 1 ? 's' : '' ?></span>
        </div>
        <div class="directory-filters__grid">
          <div class="filter-field sector-picker" id="sectorPicker">
            <label id="sectorPickerLabel">Secteur</label>
            <button class="sector-picker__trigger" id="sectorTrigger" type="button" aria-expanded="false" aria-controls="sectorMenu" aria-labelledby="sectorPickerLabel sectorTriggerText">
              <span id="sectorTriggerText"><?= $selectedSector === '' ? 'Tous les secteurs' : htmlspecialchars($selectedSector === 'OTHER' ? 'Hors classement officiel' : MARKET_SECTORS[$selectedSector]) ?></span>
              <i class="fas fa-chevron-down" aria-hidden="true"></i>
            </button>
            <div class="sector-picker__menu" id="sectorMenu" hidden>
              <div class="sector-picker__search"><i class="fas fa-search" aria-hidden="true"></i><input type="search" id="sectorSearch" placeholder="Chercher un secteur" aria-label="Chercher un secteur"></div>
              <div class="sector-picker__options">
                <button type="button" class="sector-option" data-code="" data-label="Tous les secteurs" aria-pressed="<?= $selectedSector === '' ? 'true' : 'false' ?>"><span>Tous les secteurs</span><em><?= count($allCompanies) ?></em></button>
                <?php foreach (MARKET_SECTORS as $code => $label):
                  if (empty($directoryBySector[$code])) continue;
                ?>
                  <button type="button" class="sector-option" data-code="<?= htmlspecialchars($code) ?>" data-label="<?= htmlspecialchars($label) ?>" aria-pressed="<?= $selectedSector === $code ? 'true' : 'false' ?>"><span><?= htmlspecialchars($label) ?></span><em><?= count($directoryBySector[$code]) ?></em></button>
                <?php endforeach; ?>
                <?php if ($directoryBySector['OTHER']): ?>
                  <button type="button" class="sector-option" data-code="OTHER" data-label="Hors classement officiel" aria-pressed="<?= $selectedSector === 'OTHER' ? 'true' : 'false' ?>"><span>Hors classement officiel</span><em><?= count($directoryBySector['OTHER']) ?></em></button>
                <?php endif; ?>
              </div>
              <p class="sector-picker__empty" id="sectorSearchEmpty" hidden>Aucun secteur trouvé.</p>
            </div>
          </div>
          <div class="filter-field price-filter" id="priceFilter" data-ceiling="<?= $directoryPriceCeiling ?>">
            <label for="priceMin">Cours actuel <span>(MAD par action)</span></label>
            <?php if ($directoryPrices): ?>
              <div class="price-filter__slider">
                <div class="price-filter__rail"><div class="price-filter__selection" id="priceSelection"></div></div>
                <input type="range" id="priceMinSlider" min="0" max="1000" value="0" aria-label="Cours minimum">
                <input type="range" id="priceMaxSlider" min="0" max="1000" value="1000" aria-label="Cours maximum">
              </div>
              <div class="price-filter__inputs">
                <label>Min. <input type="number" id="priceMin" min="0" max="<?= $directoryPriceCeiling ?>" step="0.01" value="0"></label>
                <span aria-hidden="true">→</span>
                <label>Max. <input type="number" id="priceMax" min="0" max="<?= $directoryPriceCeiling ?>" step="0.01" value="<?= $directoryPriceCeiling ?>"></label>
              </div>
              <p class="price-filter__hint">Glissez les bornes ou saisissez un cours exact.</p>
            <?php else: ?>
              <p class="price-filter__hint">Cours indisponibles pour le moment.</p>
            <?php endif; ?>
          </div>
          <button class="filter-reset" id="resetDirectoryFilters" type="button"><i class="fas fa-rotate-left" aria-hidden="true"></i> Réinitialiser</button>
        </div>
      </section>
    <?php endif; ?>

    <form method="POST" action="" data-loading>
      <div class="search-bar-wrap">
        <div class="form-floating flex-grow-1">
          <input type="search" name="NAME" id="nameInput" list="companyList"
                 class="form-control" placeholder=" " required autocomplete="off"
                 value="<?= htmlspecialchars($_POST['NAME'] ?? '') ?>">
          <label for="nameInput"><i class="fas fa-search me-2"></i>Filtrer la liste ou ouvrir une fiche</label>
          <datalist id="companyList">
            <?php
              // Label = readable name + ticker, always in that order so the
              // symbol is where the eye expects it. The option's *value* stays
              // the stored name so selection still resolves exactly.
              // The only case worth suppressing is a label identical to the
              // symbol, which is what produced the useless "IAM — IAM"; a
              // substring test instead would strip the ticker from "CIH BANK".
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

    <?php if (!$searched): ?>
      <div class="directory-grid" id="directoryGrid">
        <?php foreach ($allCompanies as $n):
          $sectorCode = market_sector_for_company($n);
          $sectorLabel = $sectorCode ? MARKET_SECTORS[$sectorCode] : 'Hors classement officiel';
          $companyLabel = $labelOf[$n] ?? $n;
          $ticker = $symbolOf[$n] ?? '';
          $currentPrice = $directoryPrices[$n] ?? null;
          $detailParams = ['name' => $n];
          $detailParams = array_merge($detailParams, $directoryFilterParams);
        ?>
          <a class="directory-card" href="infoAction.php?<?= htmlspecialchars(http_build_query($detailParams)) ?>"
             data-name="<?= htmlspecialchars($n) ?>"
             data-search="<?= htmlspecialchars($n . ' ' . $companyLabel . ' ' . $ticker . ' ' . $sectorLabel) ?>"
             data-sector="<?= htmlspecialchars($sectorCode ?? 'OTHER') ?>"
             data-price="<?= $currentPrice !== null ? htmlspecialchars((string)$currentPrice) : '' ?>">
            <span class="directory-card__top"><strong><?= htmlspecialchars($companyLabel) ?></strong><?php if ($ticker): ?><span class="mono"><?= htmlspecialchars($ticker) ?></span><?php endif; ?></span>
            <span class="directory-card__bottom"><span class="directory-card__sector"><?= htmlspecialchars($sectorLabel) ?></span><span class="directory-card__price"><?= $currentPrice !== null ? number_format($currentPrice, 2, ',', ' ') . ' MAD' : 'Cours indisponible' ?></span></span>
          </a>
        <?php endforeach; ?>
      </div>
      <p class="directory-empty" id="directoryEmpty" <?= $directoryCount > 0 ? 'hidden' : '' ?>>Aucune société ne correspond à ce filtre.</p>
    <?php else: ?>
      <a class="directory-back" href="infoAction.php<?= $directoryFilterParams ? '?' . htmlspecialchars(http_build_query($directoryFilterParams)) : '' ?>#companyDirectory"><i class="fas fa-arrow-left me-1"></i>Retour à la liste<?= $selectedSector !== '' ? ' du secteur' : '' ?></a>
    <?php endif; ?>

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
                  <?php $detailSector = market_sector_for_company($company['name'] ?? $name); ?>
                  <?php if ($detailSector): ?>
                    <a class="sector-badge" href="infoAction.php?sector=<?= urlencode($detailSector) ?>#companyDirectory"><?= htmlspecialchars(MARKET_SECTORS[$detailSector]) ?></a>
                  <?php elseif (!empty($company['sector'])): ?>
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
                <span class="muted">· les ratios combinent ces comptes avec le cours du jour</span>
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
                  <?= $fyEst ?> est une <strong>prévision</strong>, pas un résultat publié
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

            <h2 class="section-label">Dividendes</h2>

            <!-- ── Dividendes ─────────────────────────────── -->
            <div class="panel-body" id="panel-dividendes">
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
                  Calendrier de distribution
                  <span class="muted">· le dividende versé en <?= date('Y') ?> provient de l'exercice <?= date('Y') - 1 ?></span>
                </p>
              <?php endif; ?>
            </div>


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

    // Keep the primary company description above; do not repeat it here.

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
        plugins: [barCrosshair, window.WorkspaceCharts.financialLegend],
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
            legend: { display: false },
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
const directoryCards = [...document.querySelectorAll('.directory-card')];
const directoryCount = document.getElementById('directoryCount');
const directoryEmpty = document.getElementById('directoryEmpty');
const normalizeDirectoryText = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
const directorySearch = document.getElementById('nameInput');
if (directoryCards.length) {
  const picker = document.getElementById('sectorPicker');
  const trigger = document.getElementById('sectorTrigger');
  const triggerText = document.getElementById('sectorTriggerText');
  const menu = document.getElementById('sectorMenu');
  const sectorSearch = document.getElementById('sectorSearch');
  const sectorOptions = [...document.querySelectorAll('.sector-option')];
  const priceFilter = document.getElementById('priceFilter');
  const priceCeiling = Number(priceFilter.dataset.ceiling);
  const minInput = document.getElementById('priceMin');
  const maxInput = document.getElementById('priceMax');
  const minSlider = document.getElementById('priceMinSlider');
  const maxSlider = document.getElementById('priceMaxSlider');
  const initialParams = new URLSearchParams(location.search);
  let selectedSector = <?= json_encode($selectedSector) ?>;
  const clamp = value => Math.max(0, Math.min(priceCeiling, Number.isFinite(value) ? value : 0));
  let minPrice = minInput ? clamp(Number(initialParams.get('price_min') || 0)) : 0;
  let maxPrice = maxInput ? clamp(Number(initialParams.get('price_max') || priceCeiling)) : priceCeiling;
  if (minPrice > maxPrice) minPrice = maxPrice;

  // A logarithmic slider keeps ordinary share prices adjustable even when one
  // expensive stock stretches the market range into five digits.
  const sliderPosition = value => Math.round(Math.log1p(value) / Math.log1p(priceCeiling) * 1000);
  const sliderPrice = position => Math.round(Math.expm1(Number(position) / 1000 * Math.log1p(priceCeiling)) * 100) / 100;
  function updatePriceControls() {
    if (!minInput) return;
    minInput.value = minPrice.toFixed(2);
    maxInput.value = maxPrice.toFixed(2);
    minSlider.value = sliderPosition(minPrice);
    maxSlider.value = sliderPosition(maxPrice);
    const left = Number(minSlider.value) / 10;
    const right = Number(maxSlider.value) / 10;
    const selection = document.getElementById('priceSelection');
    selection.style.left = left + '%';
    selection.style.width = Math.max(0, right - left) + '%';
  }
  function closeSectorMenu() {
    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  }
  function filterDirectory(updateUrl = false) {
    const query = normalizeDirectoryText(directorySearch.value.trim());
    const usePrice = minInput && (minPrice > 0 || maxPrice < priceCeiling);
    let visible = 0;
    for (const card of directoryCards) {
      const price = card.dataset.price === '' ? null : Number(card.dataset.price);
      const matches = (!selectedSector || card.dataset.sector === selectedSector)
        && normalizeDirectoryText(card.dataset.search).includes(query)
        && (!usePrice || (price !== null && price >= minPrice && price <= maxPrice));
      card.hidden = !matches;
      if (matches) visible++;
    }
    directoryCount.textContent = visible + (visible === 1 ? ' société' : ' sociétés');
    directoryEmpty.hidden = visible !== 0;
    directoryEmpty.textContent = 'Aucune société ne correspond à ces filtres.';

    const params = new URLSearchParams();
    if (selectedSector) params.set('sector', selectedSector);
    if (usePrice) {
      if (minPrice > 0) params.set('price_min', minPrice.toFixed(2));
      if (maxPrice < priceCeiling) params.set('price_max', maxPrice.toFixed(2));
    }
    for (const card of directoryCards) {
      const detailParams = new URLSearchParams(params);
      detailParams.set('name', card.dataset.name);
      card.href = 'infoAction.php?' + detailParams.toString();
    }
    if (updateUrl) history.replaceState(null, '', 'infoAction.php' + (params.size ? '?' + params.toString() : '') + location.hash);
  }

  trigger.addEventListener('click', () => {
    menu.hidden = !menu.hidden;
    trigger.setAttribute('aria-expanded', String(!menu.hidden));
    if (!menu.hidden) sectorSearch.focus();
  });
  document.addEventListener('pointerdown', event => { if (!picker.contains(event.target)) closeSectorMenu(); });
  picker.addEventListener('keydown', event => { if (event.key === 'Escape') { closeSectorMenu(); trigger.focus(); } });
  sectorSearch.addEventListener('input', () => {
    const query = normalizeDirectoryText(sectorSearch.value.trim());
    let visible = 0;
    for (const option of sectorOptions) {
      option.hidden = !normalizeDirectoryText(option.dataset.label).includes(query);
      if (!option.hidden) visible++;
    }
    document.getElementById('sectorSearchEmpty').hidden = visible !== 0;
  });
  sectorOptions.forEach(option => option.addEventListener('click', () => {
    selectedSector = option.dataset.code;
    triggerText.textContent = option.dataset.label;
    sectorOptions.forEach(item => item.setAttribute('aria-pressed', String(item === option)));
    sectorSearch.value = '';
    sectorSearch.dispatchEvent(new Event('input'));
    closeSectorMenu();
    filterDirectory(true);
  }));
  directorySearch.addEventListener('input', () => filterDirectory());

  if (minInput) {
    minSlider.addEventListener('input', () => {
      minPrice = Math.min(sliderPrice(minSlider.value), maxPrice);
      updatePriceControls(); filterDirectory(true);
    });
    maxSlider.addEventListener('input', () => {
      maxPrice = Math.max(sliderPrice(maxSlider.value), minPrice);
      updatePriceControls(); filterDirectory(true);
    });
    minInput.addEventListener('change', () => {
      minPrice = Math.min(clamp(Number(minInput.value)), maxPrice);
      updatePriceControls(); filterDirectory(true);
    });
    maxInput.addEventListener('change', () => {
      maxPrice = Math.max(clamp(maxInput.value === '' ? priceCeiling : Number(maxInput.value)), minPrice);
      updatePriceControls(); filterDirectory(true);
    });
    updatePriceControls();
  }
  document.getElementById('resetDirectoryFilters').addEventListener('click', () => {
    selectedSector = '';
    triggerText.textContent = 'Tous les secteurs';
    sectorOptions.forEach(option => option.setAttribute('aria-pressed', String(option.dataset.code === '')));
    minPrice = 0; maxPrice = priceCeiling;
    directorySearch.value = '';
    updatePriceControls(); filterDirectory(true);
  });
  filterDirectory();
}

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
