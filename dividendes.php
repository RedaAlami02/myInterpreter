<?php
/**
 * Dividend calendar — every issuer's distribution for one payment year,
 * ordered by payment date so "what lands next" is the first thing visible.
 *
 * Data comes from the `dividends` collection, filled weekly by the cloud
 * function from calendar.example. Entries the AGM has not yet voted are marked
 * "prévu" and styled differently — they must never read as commitments.
 */
session_start();
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/dividends.php';

$today   = date('Y-m-d');
$thisYr  = (int)date('Y');
$year    = isset($_GET['year']) ? max(2022, min($thisYr + 1, (int)$_GET['year'])) : $thisYr;
$dbError = null;
$rows    = [];
$priceMap = [];

try {
    $rows = div_for_year($year);
    foreach (aw_list_docs('latest_prices', [q_limit(200)]) as $d) {
        $n = $d['c_name'] ?? '';
        if ($n !== '') $priceMap[$n] = (float)($d['pa'] ?? 0);
    }
} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// Undated rows sort last rather than first — an unknown date is not January.
usort($rows, fn($a, $b) => strcmp(div_date($a) ?: '9999-99-99', div_date($b) ?: '9999-99-99'));

$upcoming = $past = $undated = [];
foreach ($rows as $r) {
    $d = div_date_end($r) ?: div_date($r);
    if (!$d)                    $undated[] = $r;
    elseif ($d >= $today)       $upcoming[] = $r;
    else                        $past[] = $r;
}

$totalAmount = 0.0; $confirmedCount = 0;
foreach ($rows as $r) {
    $totalAmount += (float)($r['amount'] ?? 0);
    if (div_confirmed($r)) $confirmedCount++;
}

/** One table body, shared by the three sections. */
function div_rows_table(array $list, array $priceMap, bool $dim = false): void
{
    if (!$list) return; ?>
    <div class="card-glass overflow-x-auto mb-4">
      <table class="tbl">
        <thead><tr>
          <th>Société</th>
          <th class="num">MAD/action</th>
          <th class="num">Rendement</th>
          <th>Détachement</th>
          <th>Paiement</th>
          <th>Statut</th>
        </tr></thead>
        <tbody>
        <?php foreach ($list as $r):
            $name  = $r['c_name'] ?? '';
            $amt   = (float)($r['amount'] ?? 0);
            $yield = div_yield($r, $priceMap[$name] ?? null);
            $isQ   = strcasecmp((string)($r['frequency'] ?? ''), 'Trimestriel') === 0;
        ?>
          <tr<?= $dim ? ' class="div-done"' : '' ?>>
            <td>
              <a href="infoAction.php?name=<?= urlencode($name) ?>" class="t-cyan"><?= htmlspecialchars($name) ?></a>
              <?php if ($isQ): ?><span class="div-badge quarterly">trim.</span><?php endif; ?>
              <?php if (!empty($r['type']) && stripos($r['type'], 'exceptionnel') !== false): ?>
                <span class="div-badge exceptional"><?= htmlspecialchars($r['type']) ?></span>
              <?php endif; ?>
            </td>
            <td class="num mono"><?= $amt > 0 ? number_format($amt, 2, ',', ' ') : '—' ?></td>
            <td class="num mono"><?= $yield === null ? '—' : number_format($yield, 2, ',', ' ') . '&nbsp;%' ?></td>
            <td class="date"><?= fmt_date($r['ex_date'] ?? '', '—') ?></td>
            <td class="date"><?= div_fmt_date($r) ?></td>
            <td>
              <?php if (div_confirmed($r)): ?>
                <span class="div-badge confirmed"><i class="fas fa-check me-1"></i>confirmé</span>
              <?php else: ?>
                <span class="div-badge estimated"><i class="fas fa-clock me-1"></i>prévu</span>
              <?php endif; ?>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
<?php }
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>myInterpreter | Calendrier des dividendes</title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=3" rel="stylesheet">
  <link href="assets/css/dividendes.css?v=1" rel="stylesheet">
</head>
<body>
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">
    <div class="div-page">

      <div class="div-hero">
        <h1><i class="fas fa-coins t-emerald me-2"></i>Calendrier des dividendes</h1>
        <p>Qui verse, quand, et combien — pour l'année de paiement <?= $year ?>.</p>
      </div>

      <?php if ($dbError): ?>
        <div class="alert alert-danger">
          <strong><i class="fas fa-bug me-2"></i>Erreur :</strong>
          <?= htmlspecialchars($dbError) ?>
        </div>
      <?php elseif (!$rows): ?>
        <div class="alert alert-info">
          <i class="fas fa-info-circle me-2"></i>
          Aucun dividende enregistré pour <?= $year ?>.
        </div>
      <?php else: ?>

        <div class="div-summary">
          <div class="div-stat">
            <span class="div-stat-val"><?= count($rows) ?></span>
            <span class="div-stat-lbl">sociétés distributrices</span>
          </div>
          <div class="div-stat">
            <span class="div-stat-val t-cyan"><?= count($upcoming) ?></span>
            <span class="div-stat-lbl">versements à venir</span>
          </div>
          <div class="div-stat">
            <span class="div-stat-val t-emerald"><?= $confirmedCount ?></span>
            <span class="div-stat-lbl">dates confirmées</span>
          </div>
          <div class="div-years">
            <?php for ($y = $thisYr + 1; $y >= $thisYr - 4; $y--): ?>
              <a class="div-year-btn<?= $y === $year ? ' active' : '' ?>"
                 href="dividendes.php?year=<?= $y ?>"><?= $y ?></a>
            <?php endfor; ?>
          </div>
        </div>

        <?php if ($upcoming): ?>
          <h5 class="div-sec-title">
            <i class="fas fa-arrow-right me-2 t-cyan"></i>À venir
            <span class="muted"><?= count($upcoming) ?></span>
          </h5>
          <?php div_rows_table($upcoming, $priceMap); ?>
        <?php endif; ?>

        <?php if ($undated): ?>
          <h5 class="div-sec-title">
            <i class="fas fa-question-circle me-2 t-amber"></i>Date non communiquée
            <span class="muted"><?= count($undated) ?></span>
          </h5>
          <?php div_rows_table($undated, $priceMap); ?>
        <?php endif; ?>

        <?php if ($past): ?>
          <h5 class="div-sec-title">
            <i class="fas fa-check me-2"></i>Déjà versés
            <span class="muted"><?= count($past) ?></span>
          </h5>
          <?php div_rows_table($past, $priceMap, true); ?>
        <?php endif; ?>

        <p class="fund-source">
          <i class="fas fa-calendar-alt me-1"></i>
          Source <strong>calendar.example</strong>, actualisé chaque semaine
          <span class="muted">· un dividende versé en <?= $year ?> provient de l'exercice <?= $year - 1 ?>
          · les rendements sont calculés sur le cours du jour · montants bruts</span>
        </p>

      <?php endif; ?>
    </div>
  </main>
</div>
</body>
</html>
