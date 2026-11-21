<?php
/**
 * Dividend calendar — every issuer's distribution for one payment year,
 * ordered by payment date so "what lands next" is the first thing visible.
 *
 * Data comes from the `dividends` collection, filled weekly by the cloud
 * function from the external calendar source. Entries the AGM has not yet
 * voted are marked
 * "prévu" and styled differently — they must never read as commitments.
 */
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/core/i18n.php';
require_once 'config/config.php';
require_once 'core/Appwrite.php';
require_once 'core/dividends.php';
require_once 'core/current_prices.php';
require_once 'core/auth.php';
// Only index.php and infoAction.php are public; this calendar needs an account.
requireLogin();

$today   = date('Y-m-d');
$thisYr  = (int)date('Y');
$year    = isset($_GET['year']) ? max(2022, min($thisYr + 1, (int)$_GET['year'])) : $thisYr;
$dbError = null;
$rows    = [];
$priceMap = [];
$priceDateMap = [];

try {
    $calendarData = aw_multi_list_docs([
        'year' => ['dividends', [q_equal('year', $year), q_limit(200)], null],
        'prices' => ['latest_prices', [q_limit(200)], null],
    ]);
    $rows = array_map('div_review_row', $calendarData['year']);
    foreach ($calendarData['prices'] as $d) {
        $n = $d['c_name'] ?? '';
        if ($n !== '') { $priceMap[$n] = (float)($d['pa'] ?? 0); $priceDateMap[$n] = $d['date'] ?? null; }
    }
} catch (Throwable $e) {
    $dbError = $e->getMessage();
}

// Same-day reported quotes, when the preview feed is available. Yields fall back
// to the recorded reference for companies without a current quote.
try {
    foreach (current_market_prices(sb_market_preview()) as $name => $quote) {
        $priceMap[$name] = (float)$quote['pa'];
        $priceDateMap[$name] = gmdate('c');
    }
} catch (Throwable $e) { /* keep recorded references */ }

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

// Payment-month distribution, measured over every row we hold. Drives the
// banner so the stated season reflects our own data rather than folklore.
$monthCount = array_fill(1, 12, 0);
$monthTotal = 0;
try {
    foreach (aw_list_docs('dividends', [q_limit(500)]) as $r) {
        if (div_verification_issue($r) !== null) continue;
        if (!empty($r['pay_date'])) { $monthCount[(int)substr($r['pay_date'], 5, 2)]++; $monthTotal++; }
    }
} catch (Throwable $e) { /* the banner is decoration; never break the page for it */ }
$peakMonth = $monthTotal ? array_search(max($monthCount), $monthCount, true) : null;
$seasonPct = $monthTotal
    ? (int)round(($monthCount[5] + $monthCount[6] + $monthCount[7] + $monthCount[8] + $monthCount[9]) / $monthTotal * 100)
    : 0;
$MONTHS_FR = [1 => 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
              'août', 'septembre', 'octobre', 'novembre', 'décembre'];

// Estimated ex-dates for the issuers whose date is not yet announced.
$predictions = [];
$historyRequests = [];
foreach ($rows as $r) {
    $n = $r['c_name'] ?? '';
    if ($n === '' || div_confirmed($r)) continue;
    $historyRequests[$n] = ['dividends', [q_equal('c_name', $n), q_order_desc('year'), q_limit(50)], null];
}
// Preserve each issuer's full prediction input, but avoid a serial network
// round trip per issuer (including repeated requests when no prediction exists).
foreach (array_chunk($historyRequests, 6, true) as $batch) {
    try {
        $histories = aw_multi_list_docs($batch);
    } catch (Throwable $e) {
        // Keep the existing per-company graceful degradation on network failure.
        $histories = [];
        foreach ($batch as $n => $_request) $histories[$n] = div_for_company($n);
    }
    foreach ($histories as $n => $history) {
        $p = div_predict($history, $year);
        if ($p) $predictions[$n] = $p;
    }
}

/** One table body, shared by the three sections. */
function div_price_is_today($date): bool
{
    if (!$date) return false;
    try { $stamp = new DateTimeImmutable((string)$date); }
    catch (Throwable $error) { return false; }
    $tz = new DateTimeZone('Africa/Casablanca');
    return $stamp->setTimezone($tz)->format('Y-m-d')
        === (new DateTimeImmutable('now', $tz))->format('Y-m-d');
}

function div_rows_table(array $list, array $priceMap, array $priceDateMap, bool $dim = false, array $predictions = []): void
{
    if (!$list) return; ?>
    <div class="card-glass overflow-x-auto mb-4">
      <table class="tbl">
        <thead><tr>
          <th><?= te('Société') ?></th>
          <th class="num"><?= te('MAD/action') ?></th>
          <th class="num"><?= te('Rendement') ?></th>
          <th><?= te('Détachement') ?></th>
          <th><?= te('Paiement') ?></th>
          <th><?= te('Statut') ?></th>
        </tr></thead>
        <tbody>
        <?php foreach ($list as $r):
            $name  = $r['c_name'] ?? '';
            $amt   = (float)($r['amount'] ?? 0);
            // The footer promises a yield on today's price. When the stored
            // price is older, show no yield instead of an unlabelled one.
            $priceDate = $priceDateMap[$name] ?? null;
            $yieldFresh = div_price_is_today($priceDate);
            $yield = $yieldFresh ? div_yield($r, $priceMap[$name] ?? null) : null;
            $yieldNote = $yieldFresh ? '' : ($priceDate ? te('Cours du ') . fmt_date($priceDate) : te('Cours indisponible'));
            $isQ   = strcasecmp((string)($r['frequency'] ?? ''), 'Trimestriel') === 0;
        ?>
          <tr<?= $dim ? ' class="div-done"' : '' ?>>
            <td>
              <a href="infoAction.php?name=<?= urlencode($name) ?>" class="t-cyan"><?= htmlspecialchars($name) ?></a>
              <?php if ($isQ): ?><span class="div-badge quarterly"><?= te('trim.') ?></span><?php endif; ?>
              <?php if (!empty($r['type']) && stripos($r['type'], 'exceptionnel') !== false): ?>
                <span class="div-badge exceptional"><?= htmlspecialchars($r['type']) ?></span>
              <?php endif; ?>
            </td>
            <td class="num mono"><?= $amt > 0 ? number_format($amt, 2, ',', ' ') : '—' ?></td>
            <td class="num mono"<?= $yieldNote !== '' ? ' title="' . htmlspecialchars($yieldNote) . '"' : '' ?>><?= $yield === null ? '—' : number_format($yield, 2, ',', ' ') . '&nbsp;%' ?></td>
            <td class="date">
              <?php if (!empty($r['ex_date'])): ?>
                <?= fmt_date($r['ex_date']) ?>
              <?php elseif (isset($predictions[$name])): ?>
                <span class="is-est" title="Estimation calculée sur <?= $predictions[$name]['years'] ?> années">
                  ≈ <?= div_fmt_window($predictions[$name]) ?></span>
              <?php else: ?>—<?php endif; ?>
            </td>
            <td class="date"><?= div_fmt_date($r) ?></td>
            <td>
              <?php if (div_verification_issue($r) !== null): ?>
                <span class="div-badge estimated"><?= te('à vérifier') ?></span>
              <?php elseif (div_confirmed($r)): ?>
                <span class="div-badge confirmed"><i class="fas fa-check me-1"></i><?= te('confirmé') ?></span>
              <?php elseif (isset($predictions[$name])): ?>
                <span class="div-badge forecast"><i class="fas fa-wand-magic-sparkles me-1"></i><?= te('estimé') ?></span>
              <?php else: ?>
                <span class="div-badge estimated"><i class="fas fa-clock me-1"></i><?= te('prévu') ?></span>
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
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title><?= te('myInterpreter | Calendrier des dividendes') ?></title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/dividendes.css?v=20261115-2" rel="stylesheet">
  <?php require 'core/theme.php'; ?>
</head>
<body class="workspace workspace-dividends">
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">
    <div class="div-page">

      <div class="div-hero">
        <h1><i class="fas fa-coins t-emerald me-2"></i><?= te('Calendrier des dividendes') ?></h1>
        <p><?= te('Qui verse, quand, et combien — pour l\'année de paiement') ?> <?= $year ?>.</p>
      </div>

      <!-- ── Le cycle marocain du dividende ──────────────── -->
      <div class="div-cycle">
        <div class="div-cycle-title">
          <i class="fas fa-calendar-check me-2 t-emerald"></i>
          <?= te('Quand attendre un dividende au Maroc') ?>
        </div>
        <div class="div-cycle-steps">
          <div class="div-step">
            <span class="div-step-when"><?= te('31 déc.') ?></span>
            <span class="div-step-what"><?= te('Clôture de l\'exercice') ?></span>
          </div>
          <div class="div-step">
            <span class="div-step-when"><?= te('mars – avril') ?></span>
            <span class="div-step-what"><?= te('Le conseil d\'administration propose le dividende') ?></span>
          </div>
          <div class="div-step">
            <span class="div-step-when"><?= te('avril – mai') ?></span>
            <span class="div-step-what"><?= te('L\'assemblée générale (AGO) le vote') ?></span>
          </div>
          <div class="div-step is-pay">
            <span class="div-step-when"><?= te('mai – septembre') ?></span>
            <span class="div-step-what"><?= te('Détachement puis paiement') ?></span>
          </div>
        </div>
        <?php if ($monthTotal): ?>
        <p class="div-cycle-note"><?= te('Depuis 2022, {percentage} % des versements ont lieu entre mai et septembre.', ['percentage' => $seasonPct]) ?></p>
        <?php endif; ?>
      </div>

      <?php if ($dbError): ?>
        <div class="alert alert-danger">
          <strong><i class="fas fa-bug me-2"></i><?= te('Erreur :') ?></strong>
          <?= htmlspecialchars($dbError) ?>
        </div>
      <?php elseif (!$rows): ?>
        <div class="alert alert-info">
          <i class="fas fa-info-circle me-2"></i>
          <?= te('Aucun dividende enregistré pour') ?> <?= $year ?>.
        </div>
      <?php else: ?>

        <div class="div-summary">
          <div class="div-stat">
            <span class="div-stat-val"><?= count($rows) ?></span>
            <span class="div-stat-lbl"><?= te('sociétés distributrices') ?></span>
          </div>
          <div class="div-stat">
            <span class="div-stat-val t-cyan"><?= count($upcoming) ?></span>
            <span class="div-stat-lbl"><?= te('versements à venir') ?></span>
          </div>
          <div class="div-stat">
            <span class="div-stat-val t-emerald"><?= $confirmedCount ?></span>
            <span class="div-stat-lbl"><?= te('dates confirmées') ?></span>
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
            <i class="fas fa-arrow-right me-2 t-cyan"></i><?= te('À venir') ?>
            <span class="muted"><?= count($upcoming) ?></span>
          </h5>
          <?php div_rows_table($upcoming, $priceMap, $priceDateMap, false, $predictions); ?>
        <?php endif; ?>

        <?php if ($undated): ?>
          <h5 class="div-sec-title">
            <i class="fas fa-question-circle me-2 t-amber"></i><?= te('Date non communiquée') ?>
            <span class="muted"><?= count($undated) ?></span>
          </h5>
          <?php div_rows_table($undated, $priceMap, $priceDateMap, false, $predictions); ?>
        <?php endif; ?>

        <?php if ($past): ?>
          <h5 class="div-sec-title">
            <i class="fas fa-check me-2"></i><?= te('Déjà versés') ?>
            <span class="muted"><?= count($past) ?></span>
          </h5>
          <?php div_rows_table($past, $priceMap, $priceDateMap, true, $predictions); ?>
        <?php endif; ?>

        <p class="fund-source">
          <i class="fas fa-calendar-alt me-1"></i>
          <span class="muted"><?= te('Un dividende versé en') ?> <?= $year ?> <?= te('provient de l\'exercice') ?> <?= $year - 1 ?>
          <?= te('· les rendements ne sont calculés que sur un cours du jour · montants bruts') ?></span>
        </p>

      <?php endif; ?>
    </div>
  </main>
</div>
<script src="assets/js/app.js?v=3"></script>
</body>
</html>
