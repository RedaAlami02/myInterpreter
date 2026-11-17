<?php
/** Separate daily-close preview. Never loads authentication or a market transport. */
require_once __DIR__ . '/core/RecoveredHistory.php';
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header("Content-Security-Policy: default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");
function history_escape($value): string { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
$error = null; $series = null; $instruments = []; $segments = []; $dots = [];
$symbol = 'MASI'; $from = ''; $through = '';
try {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') throw new InvalidArgumentException('Invalid request.');
    foreach (['symbol', 'from', 'through'] as $key) {
        if (isset($_GET[$key]) && !is_string($_GET[$key])) throw new InvalidArgumentException('Invalid query.');
    }
    $reader = recovered_history_reader();
    $instruments = $reader->instruments();
    $symbol = $_GET['symbol'] ?? 'MASI';
    $from = $_GET['from'] ?? '';
    $through = $_GET['through'] ?? '';
    $series = $reader->series($symbol, $from === '' ? null : $from, $through === '' ? null : $through);
    $points = $series['points'];
    $available = array_values(array_filter($points, static fn(array $point): bool => $point['status'] === 'AVAILABLE'));
    $last = $points ? $points[array_key_last($points)] : null;
    $lastClose = $last && $last['status'] === 'AVAILABLE' ? $last['close_decimal'] : null;
    $rangeDuplicates = count(array_filter($points, static fn(array $point): bool => $point['status'] !== 'AVAILABLE'));
    if ($available) {
        $values = array_map(static fn(array $point): float => (float)$point['close_decimal'], $available);
        $minimum = min($values); $maximum = max($values);
        $padding = max(($maximum - $minimum) * 0.1, $maximum * 0.005, 0.01);
        $bottom = $minimum - $padding; $top = $maximum + $padding;
        $firstTime = strtotime($points[0]['date'] . 'T00:00:00Z');
        $lastTime = strtotime($points[array_key_last($points)]['date'] . 'T00:00:00Z');
        $span = max(86400, $lastTime - $firstTime);
        $segment = [];
        foreach ($points as $point) {
            if ($point['status'] !== 'AVAILABLE') {
                if ($segment) $segments[] = $segment;
                $segment = [];
                continue;
            }
            $x = 20 + 960 * (strtotime($point['date'] . 'T00:00:00Z') - $firstTime) / $span;
            $y = 270 - 240 * ((float)$point['close_decimal'] - $bottom) / ($top - $bottom);
            $segment[] = number_format($x, 3, '.', '') . ',' . number_format($y, 3, '.', '');
            $dots[] = ['x' => number_format($x, 3, '.', ''), 'y' => number_format($y, 3, '.', ''), 'date' => $point['date'], 'close' => $point['close_decimal']];
        }
        if ($segment) $segments[] = $segment;
    }
} catch (InvalidArgumentException $exception) {
    http_response_code(400); $error = 'Choose an available instrument and a valid date range.';
} catch (Throwable $exception) {
    http_response_code(503); $error = 'Historical preview is unavailable.';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Daily history · Casablanca</title>
  <link rel="stylesheet" href="assets/css/history-preview.css">
</head>
<body>
<main class="history-shell">
  <header class="history-header">
    <span class="eyebrow">Casablanca / Historical data</span>
    <span class="history-badge">Not live</span>
  </header>
  <section class="history-intro">
    <h1>Daily closes</h1>
    <p>A separate view of recovered daily history. These prices do not change your portfolio valuations.</p>
  </section>
  <?php if ($error !== null): ?>
    <div class="history-empty" role="alert"><?= history_escape($error) ?></div>
  <?php else: ?>
    <form method="get" class="history-filters" aria-label="Historical date range">
      <label>Instrument
        <select name="symbol">
          <?php foreach ($instruments as $instrument): ?>
            <option value="<?= history_escape($instrument['symbol']) ?>"<?= $symbol === $instrument['symbol'] ? ' selected' : '' ?>><?= history_escape($instrument['symbol']) ?><?= $instrument['kind'] === 'INDEX' ? ' · Index' : '' ?></option>
          <?php endforeach; ?>
        </select>
      </label>
      <label>From<input type="date" name="from" value="<?= history_escape($from) ?>"></label>
      <label>Through<input type="date" name="through" value="<?= history_escape($through) ?>"></label>
      <button type="submit">Show history</button>
    </form>
    <section class="history-stats" aria-label="Selected historical range">
      <div><span>Last recorded close</span><strong><?= $lastClose !== null ? history_escape($lastClose) : 'Unavailable' ?><?= $lastClose !== null ? ($series['kind'] === 'INDEX' ? '<small>pts</small>' : '<small>MAD</small>') : '' ?></strong><span><?= $last ? history_escape($last['date']) : 'No records in range' ?></span></div>
      <div><span>Available history through</span><strong><?= history_escape($series['last_date']) ?></strong><span>Retrieved <?= history_escape(substr($series['captured_at'], 0, 10)) ?></span></div>
      <div><span>Dates with multiple observations</span><strong><?= $rangeDuplicates ?></strong><span>Shown as gaps in this range</span></div>
    </section>
    <section class="history-chart" aria-labelledby="chart-title">
      <div class="history-chart-heading"><h2 id="chart-title"><?= history_escape($symbol) ?> <span>Daily close history</span></h2><span><?= count($points) ?> recorded dates</span></div>
      <?php if ($dots): ?>
        <svg viewBox="0 0 1000 300" role="img" aria-label="<?= history_escape($symbol) ?> historical daily closes; gaps indicate ambiguous observations">
          <line class="chart-grid" x1="20" y1="30" x2="980" y2="30" />
          <line class="chart-grid" x1="20" y1="150" x2="980" y2="150" />
          <line class="chart-grid" x1="20" y1="270" x2="980" y2="270" />
          <?php foreach ($segments as $segment): ?>
            <polyline class="history-line" points="<?= history_escape(implode(' ', $segment)) ?>" />
          <?php endforeach; ?>
          <?php foreach ($dots as $dot): ?>
            <circle class="history-dot" cx="<?= $dot['x'] ?>" cy="<?= $dot['y'] ?>" r="2"><title><?= history_escape($dot['date'] . ': ' . $dot['close']) ?></title></circle>
          <?php endforeach; ?>
        </svg>
        <div class="history-axis"><span><?= history_escape($points[0]['date']) ?></span><span><?= history_escape($points[array_key_last($points)]['date']) ?></span></div>
      <?php else: ?>
        <div class="history-empty">No unambiguous daily closes are available in this range.</div>
      <?php endif; ?>
      <p class="history-chart-note">Dates with multiple observations are left as gaps. Missing prices are never filled with older values. Inconsistent daily range details are marked for review in the records.</p>
    </section>
    <section class="history-records" aria-labelledby="records-title">
      <h2 id="records-title">Recent recorded dates</h2>
      <div class="history-table-scroll"><table>
        <thead><tr><th>Date</th><th>Daily close</th><th>Record status</th></tr></thead>
        <tbody>
        <?php foreach (array_slice(array_reverse($points), 0, 20) as $point): ?>
          <tr><td><?= history_escape($point['date']) ?></td><td><?= $point['close_decimal'] === null ? 'Unavailable' : history_escape($point['close_decimal']) ?></td><td><?= $point['status'] === 'AVAILABLE' ? ($point['candidates'][0]['quality_warnings'] ? 'Daily range needs review' : 'One observation') : history_escape(count($point['candidates']) . ' observations · review needed') ?></td></tr>
        <?php endforeach; ?>
        <?php if (!$points): ?><tr><td colspan="3">No records for the selected range.</td></tr><?php endif; ?>
        </tbody>
      </table></div>
    </section>
  <?php endif; ?>
  <footer>Historical daily closes only. This view does not provide a current market quote.</footer>
</main>
</body>
</html>
