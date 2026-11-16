<?php
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
// Read-only integration check against configured public Appwrite collections.
// Run explicitly: php tests/lcp_queries_test.php
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/dividends.php';

$requests = [
    'companies' => ['company', [q_order_asc('name'), q_limit(500)], null],
    'symbols' => ['format', [q_limit(500)], null],
    'prices' => ['latest_prices', [q_limit(200)], null],
    'year' => ['dividends', [q_equal('year', (int)date('Y')), q_limit(200)], null],
];
$parallel = aw_multi_list_docs($requests);
foreach ($requests as $key => [$collection, $queries, $session]) {
    $serial = aw_list_docs($collection, $queries, $session);
    if (!$serial || $serial !== $parallel[$key]) {
        throw new RuntimeException("Empty or changed public data for {$key}; equivalence not established.");
    }
}

$historyRequests = [];
foreach ($parallel['year'] as $row) {
    $name = $row['c_name'] ?? '';
    if ($name !== '' && !div_confirmed($row)) {
        $historyRequests[$name] = ['dividends', [q_equal('c_name', $name), q_order_desc('year'), q_limit(50)], null];
    }
}
foreach (array_chunk($historyRequests, 6, true) as $batch) {
    $histories = aw_multi_list_docs($batch);
    foreach ($histories as $name => $history) {
        $serial = div_for_company($name);
        if (!$serial || $history !== $serial || div_predict($history, (int)date('Y')) !== div_predict($serial, (int)date('Y'))) {
            throw new RuntimeException('Dividend history or prediction equivalence failed.');
        }
    }
}
echo 'Public query equivalence OK; ' . count($historyRequests) . " unconfirmed issuers checked.\n";
