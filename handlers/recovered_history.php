<?php
/** Opt-in sanitized history endpoint; disabled without a pinned local export. */
require_once __DIR__ . '/../core/RecoveredHistory.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    http_response_code(405);
    header('Allow: GET');
    echo '{"error":"Method not allowed."}';
    exit;
}
try {
    $reader = recovered_history_reader();
    if (array_diff(array_keys($_GET), ['symbol', 'from', 'through'])
        || (!isset($_GET['symbol']) && (isset($_GET['from']) || isset($_GET['through'])))) {
        throw new InvalidArgumentException('Invalid historical query.');
    }
    foreach (['symbol', 'from', 'through'] as $key) {
        if (isset($_GET[$key]) && !is_string($_GET[$key])) throw new InvalidArgumentException('Invalid historical query.');
    }
    $result = isset($_GET['symbol'])
        ? $reader->series($_GET['symbol'], $_GET['from'] ?? null, $_GET['through'] ?? null)
        : ['contract' => 'daily-close-preview-v1', 'not_live' => true, 'instruments' => $reader->instruments()];
    echo json_encode($result, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
} catch (InvalidArgumentException $error) {
    http_response_code(400);
    echo '{"error":"Invalid historical query."}';
} catch (Throwable $error) {
    // Do not emit paths, native metadata, exception text or private diagnostics.
    http_response_code(503);
    echo '{"error":"Historical preview is unavailable."}';
}
