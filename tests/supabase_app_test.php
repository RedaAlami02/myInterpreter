<?php
require_once __DIR__ . '/../core/SupabaseApp.php';
require_once __DIR__ . '/../core/Appwrite.php';

function checkApp(bool $condition, string $description): void {
    if (!$condition) throw new RuntimeException($description);
}
$url = 'https://abcdefghijklmnopqrst.supabase.co';
$key = 'sb_publishable_fixture_only';
$jwt = 'fixture.user.signature';
$calls = [];
$client = new SupabaseAppClient($url, $key, static function ($method, $url, $headers, $body) use (&$calls, $jwt): array {
    $payload = $body === null ? null : json_decode($body, true);
    $calls[] = [$method, $url, $headers, $payload];
    checkApp(!str_contains(implode(' ', $headers), 'sb_secret_'), 'Elevated key sent by client.');
    if (str_contains($url, '/signup')) {
        if (isset($payload['code_challenge'])) {
            checkApp($payload['code_challenge'] === str_repeat('c', 43)
                && $payload['code_challenge_method'] === 's256'
                && str_ends_with($url, '?redirect_to=' . rawurlencode('https://example.invalid/auth_callback.php'))
                && !isset($payload['redirect_to']),
                'PKCE signup changed.');
        }
        return ['status' => 200, 'body' => '{"id":"fixture-user"}'];
    }
    if (str_contains($url, '/token')) {
        if (str_contains($url, 'grant_type=pkce')) {
            checkApp(($payload['auth_code'] ?? null) === 'fixture-code', 'Auth code changed.');
            checkApp(($payload['code_verifier'] ?? null) === str_repeat('b', 43), 'Verifier changed.');
        }
        return ['status' => 200, 'body' => '{"access_token":"fixture.user.signature","refresh_token":"refresh-fixture","expires_in":3600,"user":{"id":"fixture-user","email":"fixture@example.invalid"}}'];
    }
    if (str_contains($url, '/recover')) {
        checkApp(!isset($payload['password']), 'Reset request must not carry a password.');
        checkApp(str_ends_with($url, '?redirect_to=' . rawurlencode('https://example.invalid/auth_callback.php')) && !isset($payload['redirect_to']), 'Reset redirect changed.');
        checkApp(($payload['code_challenge'] ?? null) === str_repeat('a', 43), 'Reset challenge changed.');
        return ['status' => 200, 'body' => '{}'];
    }
    if (str_contains($url, '/resend')) {
        checkApp(($payload['type'] ?? null) === 'signup', 'Resend type changed.');
        checkApp(str_ends_with($url, '?redirect_to=' . rawurlencode('https://example.invalid/auth_callback.php')) && !isset($payload['redirect_to']), 'Resend redirect changed.');
        checkApp(($payload['code_challenge'] ?? null) === str_repeat('d',43) && $payload['code_challenge_method'] === 's256', 'Resend challenge missing.');
        return ['status' => 200, 'body' => '{}'];
    }
    checkApp(in_array('Authorization: Bearer ' . $jwt, $headers, true), 'User JWT missing.');
    if ($method === 'PUT' && str_contains($url, '/auth/v1/user')) {
        checkApp(($payload['password'] ?? null) === 'new-password-123', 'Password changed.');
        return ['status' => 200, 'body' => '{"id":"fixture-user","email":"fixture@example.invalid"}'];
    }
    if (str_contains($url, '/rpc/record_trade')) {
        checkApp(!isset($payload['user_id']) && !isset($payload['p_user_id']), 'Trade ownership must be derived by database.');
        checkApp($payload['p_quantity'] === '2.5' && $payload['p_price'] === '100.15', 'Decimal input changed.');
        return ['status' => 200, 'body' => json_encode($payload['p_request_id'])];
    }
    if (str_contains($url, '/rpc/record_official_close_valuation')) {
        checkApp($payload === [], 'Valuation must not accept caller-supplied input.');
        return ['status' => 200, 'body' => '{"status":"CREATED","date":"2026-10-26","value":-12.5,"basis":"OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION"}'];
    }
    if (str_contains($url, '/portefeuille')) return ['status' => 200, 'body' => '[{"id":"holding-fixture","quantity":2.5,"total_cost":250.375}]'];
    if (str_contains($url, '/logout')) return ['status' => 204, 'body' => ''];
    return ['status' => 200, 'body' => '{"id":"fixture-user","email":"fixture@example.invalid"}'];
});
$signup = $client->signUp('fixture@example.invalid', 'fixture-password', 'Fixture');
checkApp(!isset($signup['access_token']), 'Confirmation signup must not manufacture a session.');
$tokens = $client->signIn('fixture@example.invalid', 'fixture-password');
checkApp($tokens['user']['id'] === 'fixture-user', 'Login identity changed.');
$pkceSignup = $client->signUp(
    'fixture@example.invalid', 'fixture-password', 'Fixture',
    str_repeat('c', 43), 'https://example.invalid/auth_callback.php'
);
checkApp($pkceSignup['id'] === 'fixture-user', 'PKCE signup response changed.');
$client->recover(
    'fixture@example.invalid',
    'https://example.invalid/auth_callback.php',
    str_repeat('a', 43)
);
$client->resendConfirmation('fixture@example.invalid', 'https://example.invalid/auth_callback.php', str_repeat('d',43));
$pkce = $client->exchangeCode('fixture-code', str_repeat('b', 43));
checkApp($pkce['user']['id'] === 'fixture-user', 'PKCE exchange changed.');
$updated = $client->updatePassword($jwt, 'new-password-123');
checkApp($updated['id'] === 'fixture-user', 'Password update changed.');
$client->refresh('refresh-fixture');
checkApp($client->user($jwt)['id'] === 'fixture-user', 'User validation changed.');
$id = 'a0000000-0000-4000-8000-000000000001';
checkApp($client->recordTrade($jwt,$id,'buy','FIXTURE','2.5','100.15') === $id, 'Trade receipt changed.');
$rows = $client->listDocuments('portefeuille', [q_equal('user_id','fixture-user'),q_limit(200)], $jwt);
checkApp($rows[0]['$id'] === 'holding-fixture' && $rows[0]['quantity'] === 2.5, 'Private document mapping changed.');
$valuation = $client->recordDailyValuation($jwt);
checkApp($valuation === ['status' => 'CREATED', 'date' => '2026-10-26', 'value' => -12.5, 'basis' => 'OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION'], 'Valuation receipt changed.');
foreach ([
    '{"status":"UNDERWATER","date":"2026-10-26"}',
    '{"status":"CREATED","date":"26/10/2026"}',
    '{"status":"CREATED","date":"2026-10-26","value":"1"}',
    '{"status":"CREATED"}',
    '{"status":"CREATED","date":"2026-10-26","value":1}',
    '{"status":"CREATED","date":"2026-10-26","value":1,"basis":"INTRADAY"}',
] as $receipt) {
    $bad = new SupabaseAppClient($url, $key, fn() => ['status' => 200, 'body' => $receipt]);
    $rejected = false;
    try { $bad->recordDailyValuation($jwt); } catch (RuntimeException $error) { $rejected = true; }
    checkApp($rejected, 'Invalid valuation receipt was accepted.');
}
$client->signOut($jwt);
foreach ([
    fn() => new SupabaseAppClient($url, 'sb_secret_fixture'),
    fn() => $client->user("bad\r\nHeader: injection"),
    fn() => $client->listDocuments('migration_stage.documents', [], $jwt),
    fn() => $client->listDocuments('portefeuille', [q_limit(501)], $jwt),
    fn() => $client->recover('fixture@example.invalid', 'http://insecure.invalid/cb'),
    fn() => $client->recover('fixture@example.invalid', null, 'short'),
    fn() => $client->exchangeCode('x', 'short'),
    fn() => $client->updatePassword($jwt, 'short'),
    fn() => $client->signUp('fixture@example.invalid', 'fixture-password', 'Fixture', 'bad'),
] as $operation) {
    $failed = false;
    try { $operation(); } catch (InvalidArgumentException $error) { $failed = true; }
    checkApp($failed, 'Unsafe request was accepted.');
}
$failed = false;
$failure = new SupabaseAppClient($url, $key, fn() => ['status' => 400, 'body' => '{"error_code":"invalid_credentials","message":"fixture-secret-diagnostic"}']);
try { $failure->signIn('fixture@example.invalid','fixture-password'); }
catch (SupabaseRequestException $error) {
    $failed = true;
    checkApp($error->reason === 'invalid_credentials' && !str_contains($error->getMessage(), 'fixture-secret'), 'Remote diagnostic leaked.');
}
checkApp($failed, 'Failed login accepted.');
echo "Supabase Auth/portfolio adapter tests passed.\n";
