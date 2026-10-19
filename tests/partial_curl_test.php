<?php
// Run: php -d disable_functions=curl_multi_exec tests/partial_curl_test.php
require __DIR__ . '/../core/Appwrite.php';
require __DIR__ . '/../handlers/market_proxy.php';
if (function_exists('curl_multi_exec')) throw new RuntimeException('Disable curl_multi_exec for this regression');
if (aw_multi_list_docs([]) !== [] || mkt_batch([]) !== []) throw new RuntimeException('Sequential fallback failed');
echo "PASS partially disabled parallel-cURL fallback\n";
