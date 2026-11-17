<?php
// Run the actual request controller in isolated processes, without network or writes.
if (isset($argv[1])) {
    $_POST = ['name' => 'Example', 'symbol' => 'EX'];
    $_SERVER['REQUEST_METHOD'] = $argv[1] === 'get' ? 'GET' : 'POST';
    $_SERVER['HTTP_X_CSRF_TOKEN'] = 'fixture-token';
    if ($argv[1] === 'array') $_POST['name'] = [];
    if ($argv[1] === 'bad-token') $_POST['csrf_token'] = 'wrong';
    function app_session_start() {}
    function requireAdmin() {}
    function csrf_verify() {
        if (($_POST['csrf_token'] ?? '') !== 'fixture-token') {
            http_response_code(403); exit;
        }
    }
    function mkt_fetch_symbol($symbol) { return ['computed' => []]; }
    register_shutdown_function(function () { echo '\nSTATUS:' . (http_response_code() ?: 200); });
    $source = file_get_contents(__DIR__ . '/../handlers/save_enrichment.php');
    $source = preg_replace('/^require_once .*$/m', '', $source);
    eval('?>' . $source);
    exit;
}
foreach (['header' => 200, 'get' => 405, 'array' => 400, 'bad-token' => 403] as $case => $status) {
    $output = shell_exec(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(__FILE__) . ' ' . escapeshellarg($case));
    if (!str_contains($output ?? '', 'STATUS:' . $status)) {
        throw new RuntimeException('Unexpected enrichment response: ' . $case);
    }
}
echo "Enrichment request regression passed.\n";
