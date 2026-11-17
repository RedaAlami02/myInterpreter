<?php
require_once __DIR__ . '/../core/SupabaseAdmin.php';

function checkAdmin(bool $condition, string $description): void {
    if (!$condition) throw new RuntimeException($description);
}
$url = 'https://abcdefghijklmnopqrst.supabase.co';
$key = 'sb_publishable_fixture_only';
$jwt = 'fixture.user.signature';
$calls = [];
$client = new SupabaseAdminClient($url, $key, static function ($method, $url, $headers, $body) use (&$calls): array {
    $payload = json_decode($body, true);
    $calls[] = [$method, $url, $headers, $payload];
    checkAdmin(!str_contains(implode(' ', $headers), 'sb_secret_'), 'Elevated key sent by client.');
    if (str_contains($url, '/rpc/admin_update_company')) {
        return ['status' => 200, 'body' => json_encode(['status' => 'UPDATED', 'name' => $payload['p_name'], 'fields' => 2])];
    }
    if (str_contains($url, '/rpc/admin_record_operator_snapshot')) {
        return ['status' => 200, 'body' => json_encode(str_repeat('a', 32))];
    }
    return ['status' => 500, 'body' => '{}'];
});
$holders = '[{"name":"Holder","pct":51}]';
$receipt = $client->updateCompany($jwt, 'Alpha', ['bpa' => 12.5, 'shareholders' => $holders]);
checkAdmin($receipt === ['status' => 'UPDATED', 'name' => 'Alpha', 'fields' => 2], 'Company receipt changed.');
$call = $calls[0];
checkAdmin($call[0] === 'POST' && str_ends_with($call[1], '/rest/v1/rpc/admin_update_company'), 'Wrong update endpoint.');
checkAdmin(in_array('Authorization: Bearer ' . $jwt, $call[2], true), 'User JWT missing.');
checkAdmin(in_array('apikey: ' . $key, $call[2], true), 'Publishable key missing.');
checkAdmin($call[3]['p_name'] === 'Alpha', 'Company name changed.');
checkAdmin($call[3]['p_fields'] === ['bpa' => 12.5, 'shareholders' => $holders], 'Field payload changed.');
checkAdmin(!isset($call[3]['user_id']) && !isset($call[3]['p_user_id']), 'Ownership must be database-derived.');
$snapshot = $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => 12.5, 'per' => 8.2, 'pb' => null]);
checkAdmin($snapshot === str_repeat('a', 32), 'Snapshot receipt changed.');
checkAdmin(str_ends_with($calls[1][1], '/rest/v1/rpc/admin_record_operator_snapshot'), 'Wrong snapshot endpoint.');
checkAdmin($calls[1][3]['p_fields'] === ['c_name' => 'Alpha', 'pa' => 12.5, 'per' => 8.2, 'pb' => null], 'Snapshot payload changed.');
$missing = new SupabaseAdminClient($url, $key, fn() => ['status' => 200, 'body' => '{"status":"MISSING","name":"Alpha"}']);
checkAdmin($missing->updateCompany($jwt, 'Alpha', ['bpa' => 1])['status'] === 'MISSING', 'Missing company not reported.');

foreach ([
    fn() => $client->updateCompany($jwt, ' Alpha', ['bpa' => 1]),
    fn() => $client->updateCompany($jwt, 'Alpha', ['id' => 'forged']),
    fn() => $client->updateCompany($jwt, 'Alpha', ['name' => 'Renamed']),
    fn() => $client->updateCompany($jwt, 'Alpha', ['date' => '2026-10-28T00:00:00Z']),
    fn() => $client->updateCompany($jwt, 'Alpha', []),
    fn() => $client->updateCompany($jwt, 'Alpha', ['bpa' => '12.5']),
    fn() => $client->updateCompany($jwt, 'Alpha', ['bpa' => INF]),
    fn() => $client->updateCompany($jwt, 'Alpha', ['bpa' => true]),
    fn() => $client->updateCompany($jwt, 'Alpha', ['fiscal_year' => 2024.5]),
    fn() => $client->updateCompany($jwt, 'Alpha', ['fiscal_year' => 1800]),
    fn() => $client->updateCompany($jwt, 'Alpha', ['description' => 5]),
    fn() => $client->updateCompany("bad\r\nHeader", 'Alpha', ['bpa' => 1]),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha']),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => 0]),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => -1]),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => '12']),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => ' Alpha', 'pa' => 12]),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => 12, 'symbol' => 'A']),
    fn() => $client->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => 12, 'per' => '8']),
] as $operation) {
    $failed = false;
    try { $operation(); } catch (InvalidArgumentException $error) { $failed = true; }
    checkAdmin($failed, 'Unsafe admin input was accepted.');
}
$failed = false;
$failure = new SupabaseAdminClient($url, $key, fn() => ['status' => 403, 'body' => '{"message":"fixture-secret-diagnostic"}']);
try { $failure->updateCompany($jwt, 'Alpha', ['bpa' => 1]); }
catch (SupabaseRequestException $error) {
    $failed = true;
    checkAdmin($error->httpStatus === 403 && !str_contains($error->getMessage(), 'fixture-secret'), 'Remote diagnostic leaked.');
}
checkAdmin($failed, 'Denied write was accepted.');
$failed = false;
$badReceipt = new SupabaseAdminClient($url, $key, fn() => ['status' => 200, 'body' => '{"status":"CREATED","name":"Alpha"}']);
try { $badReceipt->updateCompany($jwt, 'Alpha', ['bpa' => 1]); } catch (RuntimeException $error) { $failed = true; }
checkAdmin($failed, 'Invalid company receipt was accepted.');
$failed = false;
$badSnapshot = new SupabaseAdminClient($url, $key, fn() => ['status' => 200, 'body' => '"not-an-id"']);
try { $badSnapshot->recordOperatorSnapshot($jwt, ['c_name' => 'Alpha', 'pa' => 1]); } catch (RuntimeException $error) { $failed = true; }
checkAdmin($failed, 'Invalid snapshot receipt was accepted.');
echo "Supabase admin maintenance adapter tests passed.\n";

// Hosting precision must not expand decimal payloads rejected by SQL scale checks.
$priorPrecision = ini_get('serialize_precision');
ini_set('serialize_precision', '17');
$precisionClient = new SupabaseAdminClient($url, $key, static function ($method, $url, $headers, $body): array {
    checkAdmin(str_contains($body, '"beta_3y":0.57'), 'Canonical decimal changed.');
    checkAdmin(!str_contains($body, '569999999'), 'Binary float expansion escaped.');
    return ['status'=>200,'body'=>'{"status":"UPDATED","name":"Alpha","fields":1}'];
});
$precisionClient->updateCompany($jwt, 'Alpha', ['beta_3y'=>0.57]);
checkAdmin(ini_get('serialize_precision') === '17', 'Host precision setting was not restored.');
ini_set('serialize_precision', $priorPrecision);

$profileClient = new SupabaseAdminClient($url,$key,static function($method,$url,$headers,$body): array {
    checkAdmin(str_ends_with($url,'/rpc/admin_apply_profile_biographies'),'Wrong safe profile endpoint.');
    $data=json_decode($body,true);
    checkAdmin(count($data['p_changes'])===1,'Batch changed.');
    return ['status'=>200,'body'=>'{"results":[{"status":"UNCHANGED","name":"Alpha"}]}'];
});
checkAdmin($profileClient->applyProfileBiographies($jwt,[['name'=>'Alpha','symbol'=>'ALP',
    'captured_at'=>'2026-11-15T12:00:00Z','fields'=>(object)['description'=>'Saved'],
    'expected'=>(object)['description'=>null]]])[0]['status']==='UNCHANGED','Safe profile receipt changed.');
