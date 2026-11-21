<?php
/**
 * Current quotes for a signed-in page, polled in the background.
 *
 * Reads the same recorded prices the pages render, so a poll can never show a
 * number the server would not have shown on a reload. The response is small
 * on purpose: two short maps, not the full rows.
 */
require_once __DIR__ . '/../core/session.php';
app_session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/auth.php';
require_once __DIR__ . '/../core/Appwrite.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: private, no-store');

if (!sb_restore_session()) {
    http_response_code(401);
    echo json_encode(['error' => 'auth']);
    exit;
}

$ttl = (int) ($_SESSION['live_quotes_ttl'] ?? 40);
try {
    // One poll per user per window: several open tabs share the answer.
    $rows = app_cache('live_quotes', max(10, min($ttl, 300)),
        fn(): array => aw_list_docs('latest_prices', [q_limit(500)]));
} catch (Throwable $error) {
    http_response_code(503);
    echo json_encode(['error' => 'unavailable']);
    exit;
}

$quotes = [];
$stamp = null;
foreach ($rows as $row) {
    $name = trim((string) ($row['c_name'] ?? ''));
    $price = $row['pa'] ?? null;
    if ($name === '' || !is_numeric($price) || (float) $price <= 0) continue;
    $quotes[$name] = (float) $price;
    $date = $row['date'] ?? null;
    if (is_string($date) && ($stamp === null || $date > $stamp)) $stamp = $date;
}

// Release the session lock before the body is written: a poll must never make
// the next page request wait.
session_write_close();
echo json_encode(['stamp' => $stamp, 'quotes' => $quotes], JSON_UNESCAPED_UNICODE);
