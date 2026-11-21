<?php
require_once __DIR__ . '/../core/SupabaseMarket.php';
require_once __DIR__ . '/../core/Appwrite.php';

function checkMarket(bool $condition, string $description): void {
    if (!$condition) throw new RuntimeException($description);
}
function rejectsMarket(callable $operation): void {
    try { $operation(); } catch (InvalidArgumentException | RuntimeException $error) { return; }
    throw new RuntimeException('Expected market request rejection.');
}
$url = 'https://abcdefghijklmnopqrst.supabase.co';
$key = 'sb_publishable_fixture_only';
$reader = new SupabaseMarketReader($url, $key, static function ($url, $headers) use ($key): array {
    checkMarket(in_array('apikey: ' . $key, $headers, true), 'Public API key header is missing.');
    checkMarket(in_array('Authorization: Bearer fixture.user.signature', $headers, true), 'Verified user JWT must accompany the public project key.');
    return ['status' => 200, 'headers' => ['content-range' => '0-0/350'],
            'body' => '[{"id":"legacy-id","pa":123.45,"per":-70.97,"pb":null}]'];
}, 'fixture.user.signature');
$params = $reader->queryParameters('data', [q_equal('c_name', 'A,"B\\C'), q_order_desc('date'), q_limit(500), q_offset(500)]);
checkMarket($params['c_name'] === 'eq.A,"B\\C', 'Plain comparison values must remain literal.');
checkMarket($params['order'] === 'date.desc,id.desc', 'History pagination must have a stable tie breaker.');
checkMarket($params['limit'] === 500 && $params['offset'] === 500, 'Pagination changed.');
$rows = $reader->listDocuments('data', [q_greater_equal('date', '2026-01-01T00:00:00Z')]);
checkMarket($rows[0]['$id'] === 'legacy-id' && $rows[0]['per'] === -70.97 && $rows[0]['pb'] === null, 'Identity, negative ratios and missing values must survive.');
checkMarket($reader->countDocuments('dividends', [q_equal('year', 2026)]) === 350, 'Exact count changed.');
$inParams = $reader->queryParameters('latest_prices', [q_in('c_name', ['ADDOHA', 'A"B'])]);
checkMarket($inParams['c_name'] === 'in.("ADDOHA","A\"B")', 'Key list must be quoted for PostgREST.');
rejectsMarket(fn() => $reader->queryParameters('latest_prices', [q_in('c_name', [])]));
rejectsMarket(fn() => $reader->queryParameters('latest_prices', [q_in('c_name', [''])]));
$profileParams = $reader->queryParameters('company_profiles', [q_equal('id', 'FIX'), q_limit(1)]);
checkMarket($profileParams['select'] === 'id,c_name,captured_at,profile', 'Profile public columns changed.');
checkMarket($profileParams['id'] === 'eq.FIX', 'Symbol lookup changed.');
checkMarket(!str_contains($params['select'], 'source') && !str_contains($params['select'], 'permissions'), 'Internal metadata must not be selected.');
foreach (['achats', 'ventes', 'portefeuille', 'benefits', 'migration_stage.documents'] as $private) {
    rejectsMarket(fn() => $reader->listDocuments($private));
}
rejectsMarket(fn() => $reader->listDocuments('recovery_archive.files'));
rejectsMarket(fn() => $reader->queryParameters('company_profiles', [q_equal('raw_responses', 'fixture')]));
rejectsMarket(fn() => new SupabaseMarketReader($url, 'sb_secret_fixture_only'));
rejectsMarket(fn() => new SupabaseMarketReader($url . '/rest/v1', $key));
rejectsMarket(fn() => $reader->queryParameters('data', [q_limit(501)]));
rejectsMarket(fn() => $reader->queryParameters('data', [q_equal('secret', 'fixture')]));
$failure = new SupabaseMarketReader($url, $key, fn() => ['status' => 403, 'body' => 'fixture-secret-response'], 'fixture.user.signature');
rejectsMarket(fn() => (new SupabaseMarketReader($url, $key))->listDocuments('company'));
$anonymous = new SupabaseMarketReader($url, $key, static function ($url, $headers): array {
    checkMarket(!array_filter($headers, fn($header) => str_starts_with($header, 'Authorization:')), 'Anonymous mode must not send a bearer token.');
    return ['status' => 200, 'headers' => [], 'body' => '[]'];
}, null, false, true);
checkMarket($anonymous->listDocuments('company') === [], 'Opt-in anonymous read must use the public key only.');
$failed = false;
try {
    $failure->listDocuments('company');
} catch (RuntimeException $error) {
    $failed = true;
    checkMarket(!str_contains($error->getMessage(), 'fixture-secret-response'), 'Remote diagnostics must not leak.');
}
checkMarket($failed, 'HTTP errors must not silently become empty data.');
$closeReader = new SupabaseMarketReader($url, $key, static function ($url, $headers): array {
    checkMarket(str_contains($url, '/rpc/read_latest_price_references_v1?'), 'Closing references must use the versioned read-only RPC.');
    checkMarket(str_contains($url, 'c_name=eq.SGTM'), 'Reference filters must survive.');
    return ['status'=>200,'body'=>'[{"id":"close:fixture","c_name":"SGTM","pa":524,"date":"2026-11-03T19:23:21Z"}]'];
}, 'fixture.user.signature', true);
checkMarket($closeReader->listDocuments('latest_prices', [q_equal('c_name','SGTM')])[0]['pa'] === 524, 'Verified closing reference must retain its actual price.');
echo "Supabase market adapter tests passed.\n";

$batch = new SupabaseMarketReader($url, $key, static function ($url, $headers): array {
    checkMarket(in_array('Authorization: Bearer fixture.user.signature', $headers, true), 'Batch lost user scope.');
    if (str_contains($url, '/dividends?')) return ['status'=>503,'body'=>'private-diagnostic'];
    return ['status'=>200,'body'=>'[{"id":"fixture","name":"Alpha"}]'];
}, 'fixture.user.signature');
$requests = ['company'=>['company', [q_limit(1)]], 'dividends'=>['dividends', [q_limit(1)]]];
$partial = $batch->listDocumentsBatch($requests, true);
checkMarket($partial['company'][0]['$id'] === 'fixture' && $partial['dividends'] === null, 'Optional failure hid valid panels.');
rejectsMarket(fn() => $batch->listDocumentsBatch($requests));
rejectsMarket(fn() => $batch->listDocumentsBatch(['bad'=>['portefeuille',[]]], true));
checkMarket($batch->listDocumentsBatch([]) === [], 'Empty batch changed.');
echo "Market batch scope, validation and optional-failure checks passed.\n";
