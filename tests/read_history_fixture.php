<?php
// CLI harness only. Does not load site configuration, credentials or transports.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require_once __DIR__ . '/../core/RecoveredHistory.php';
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
try {
    $reader = new RecoveredHistoryReader($input['directory'], $input['pin']);
    $result = ($input['operation'] ?? '') === 'instruments'
        ? $reader->instruments()
        : $reader->series($input['symbol'], $input['from'] ?? null, $input['through'] ?? null);
    echo json_encode(['ok' => true, 'result' => $result], JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    echo json_encode(['ok' => false, 'error_category' => get_class($error)], JSON_THROW_ON_ERROR);
}
