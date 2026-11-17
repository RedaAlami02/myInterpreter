<?php
if (!defined('BASE_URL')) define('BASE_URL', '/myInterpreter');
if (!defined('MYINTERPRETER_PUBLIC_URL')) define('MYINTERPRETER_PUBLIC_URL', 'https://example.invalid/application');
require_once __DIR__ . '/../core/supabase_session.php';

function checkPkce(bool $condition, string $description): void {
    if (!$condition) throw new RuntimeException($description);
}

$_SESSION = [];
$verifier = sb_pkce_verifier();
checkPkce(preg_match('/^[A-Za-z0-9_-]{43}$/D', $verifier) === 1, 'Verifier shape changed.');
checkPkce($verifier !== sb_pkce_verifier(), 'Verifier must be random.');
$expected = rtrim(strtr(base64_encode(hash('sha256', $verifier, true)), '+/', '-_'), '=');
checkPkce(sb_pkce_challenge($verifier) === $expected, 'Challenge is not S256.');
checkPkce(preg_match('/^[A-Za-z0-9_-]{43}$/D', $expected) === 1, 'Challenge shape changed.');

$challenge = sb_pkce_start('recovery');
$stored = $_SESSION['sb_pkce_verifier'] ?? null;
checkPkce(is_string($stored) && $challenge === sb_pkce_challenge($stored), 'Start did not store a verifier.');
checkPkce(($_SESSION['sb_pkce_flow'] ?? null) === 'recovery', 'Start did not store the flow.');
checkPkce(sb_pkce_take() === $stored, 'Take did not return the verifier.');
checkPkce(sb_pkce_take() === null, 'Take must consume the verifier.');
$_SESSION['pending_email'] = 'fixture@example.invalid';
$_SESSION['sb_pkce_flow'] = 'signup';
sb_pkce_clear();
checkPkce(!isset($_SESSION['sb_pkce_verifier'], $_SESSION['sb_pkce_flow'], $_SESSION['pending_email']),
    'Clear left OAuth state behind.');

$_SERVER['HTTP_HOST'] = 'myinterpreter.infinityfree.me';
$_SERVER['HTTPS'] = 'on';
checkPkce(sb_public_url('/auth_callback.php') === 'https://example.invalid/application/auth_callback.php',
    'Configured HTTPS redirect URL changed.');
$_SERVER['HTTPS'] = 'off';
checkPkce(sb_public_url('/auth_callback.php') === 'https://example.invalid/application/auth_callback.php',
    'Proxy HTTP connection changed the public HTTPS destination.');
$_SERVER['HTTPS'] = 'on';
foreach (['', 'localhost:3000', '127.0.0.1', 'attacker.invalid', 'bad host', 'host/evil', 'host?x=1', str_repeat('a', 260)] as $host) {
    $_SERVER['HTTP_HOST'] = $host;
    $_SERVER['HTTP_X_FORWARDED_HOST'] = $host;
    checkPkce(sb_public_url('/auth_callback.php') === 'https://example.invalid/application/auth_callback.php',
        'Untrusted request header affected an email destination.');
}
foreach (['http://example.invalid', 'https://localhost', 'https://127.0.0.1', 'https://app.localhost',
          'https://user:password@example.invalid', 'https://example.invalid?next=elsewhere',
          'https://example.invalid/#fragment', 'https://example.invalid/../other', 'https://example.invalid:444',
          "https://example.invalid\r\nInjected: value"] as $base) {
    $failed = false;
    try { sb_auth_redirect_url($base, '/auth_callback.php'); } catch (RuntimeException $error) { $failed = true; }
    checkPkce($failed, 'Invalid deployment URL accepted.');
}
foreach (['//attacker.invalid/callback', '/auth_callback.php?next=x', '/auth_callback.php#x', '/../callback.php'] as $path) {
    $failed = false;
    try { sb_auth_redirect_url('https://example.invalid', $path); } catch (RuntimeException $error) { $failed = true; }
    checkPkce($failed, 'Invalid callback path accepted.');
}
echo "Supabase PKCE helper tests passed.\n";
