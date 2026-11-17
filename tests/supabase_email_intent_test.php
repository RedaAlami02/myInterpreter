<?php
require_once __DIR__ . '/../core/session.php';
require_once __DIR__ . '/../core/supabase_session.php';
ini_set('session.save_path', sys_get_temp_dir());
app_session_start();
function ensureIntent(bool $value): void { if (!$value) throw new RuntimeException('Email intent assertion failed.'); }
function rejectIntent(callable $callback): void {
    try { $callback(); } catch (RuntimeException $error) { return; }
    throw new RuntimeException('Unsafe email intent accepted.');
}
$user = ['id' => 'fixture-user', 'email' => 'fixture@example.invalid', 'email_confirmed_at' => '2026-10-01T12:00:00Z'];
$tokens = ['access_token' => 'fixture-access', 'refresh_token' => 'fixture-refresh', 'expires_in' => 3600, 'user' => $user];
$calls = 0;
$exchange = function ($code, $verifier) use (&$calls, $tokens) { $calls++; return $tokens; };
foreach (['signup', 'recovery'] as $flow) {
    $_SESSION = [];
    sb_pkce_start($flow, 'Fixture@example.invalid');
    ensureIntent(sb_pkce_pending($flow, 'fixture@example.invalid'));
    $result = sb_pkce_exchange('fixture-code', $exchange);
    ensureIntent($result['flow'] === $flow && $result['tokens'] === $tokens);
    rejectIntent(fn() => sb_pkce_exchange('fixture-code', $exchange));
}
foreach ([false, true] as $logoutFails) {
    $_SESSION = ['logged_in' => true, 'USER_ID' => 'fixture-user', 'sb_auth' => $tokens, 'csrf_token' => 'old'];
    $revoked = null;
    sb_finish_signup_confirmation($tokens, function ($token) use (&$revoked, $logoutFails) {
        $revoked = $token;
        if ($logoutFails) throw new RuntimeException('Synthetic logout failure');
    });
    ensureIntent($revoked === 'fixture-access');
    ensureIntent(!isset($_SESSION['sb_auth'], $_SESSION['logged_in'], $_SESSION['USER_ID'], $_SESSION['csrf_token']));
    ensureIntent($_SESSION['sb_auth_notice'] === 'EMAIL_CONFIRMED');
    ensureIntent(!sb_restore_session());
}
foreach (['missing', 'expired', 'future', 'wrong-email', 'unconfirmed', 'wrong-account', 'invalid-flow'] as $case) {
    $_SESSION = [];
    sb_pkce_start('signup', 'fixture@example.invalid');
    $returned = $tokens;
    if ($case === 'missing') sb_pkce_clear();
    if ($case === 'expired') $_SESSION['sb_pkce_started_at'] = time() - 3601;
    if ($case === 'future') $_SESSION['sb_pkce_started_at'] = time() + 60;
    if ($case === 'wrong-email') $returned['user']['email'] = 'other@example.invalid';
    if ($case === 'unconfirmed') $returned['user']['email_confirmed_at'] = null;
    if ($case === 'wrong-account') { $_SESSION['logged_in'] = true; $_SESSION['USER_ID'] = 'another-user'; }
    if ($case === 'invalid-flow') $_SESSION['sb_pkce_flow'] = 'attacker-input';
    rejectIntent(fn() => sb_pkce_exchange('code', fn() => $returned));
    ensureIntent(!isset($_SESSION['sb_pkce_verifier']));
}
$_SESSION = [];
sb_pkce_start('signup', 'fixture@example.invalid');
ensureIntent(!sb_pkce_pending('signup', 'other@example.invalid'));
ensureIntent(!sb_pkce_pending('recovery', 'fixture@example.invalid'));
sb_pkce_start('recovery', 'other@example.invalid');
ensureIntent(!sb_pkce_pending('signup', 'fixture@example.invalid'));
sb_begin_recovery($tokens);
ensureIntent(!isset($_SESSION['sb_auth'], $_SESSION['logged_in'], $_SESSION['USER_ID']));
ensureIntent(!sb_restore_session());
ensureIntent(sb_recovery_access_token(fn() => $user) === 'fixture-access');
ensureIntent($_SESSION['sb_recovery']['expires_at'] <= time() + 900);
$_SESSION['sb_recovery']['expires_at'] = time() - 1;
rejectIntent(fn() => sb_recovery_access_token(fn() => $user));
ensureIntent(!isset($_SESSION['sb_recovery']));
sb_begin_recovery($tokens);
rejectIntent(fn() => sb_recovery_access_token(fn() => ['id' => 'another-user']));
sb_begin_recovery($tokens);
sb_store_session($tokens, false);
ensureIntent(!isset($_SESSION['sb_recovery']));
ensureIntent($_SESSION['USER_ID'] === 'fixture-user');
// Browser fragments and posted tokens cannot be adopted by the controller.
$controller = file_get_contents(__DIR__ . '/../auth_callback.php');
ensureIntent(!str_contains($controller, "\$_POST['access_token']"));
ensureIntent(!str_contains($controller, 'form.submit()'));
ensureIntent(str_contains($controller, 'sb_pkce_exchange'));
sb_clear_session();
session_destroy();
echo "Supabase email intent and recovery isolation tests passed.\n";
