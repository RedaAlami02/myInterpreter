<?php
// Independent child processes reset function-local validation caches.
if (!isset($argv[1])) {
    foreach (['login','refresh','invalid','unavailable','remember','logout'] as $scenario) {
        passthru(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(__FILE__) . ' ' . escapeshellarg($scenario), $status);
        if ($status !== 0) exit($status);
    }
    echo "Supabase session lifecycle tests passed.\n";
    exit();
}
require_once __DIR__ . '/../core/SupabaseApp.php';
require_once __DIR__ . '/../core/session.php';
require_once __DIR__ . '/../core/supabase_session.php';
ini_set('session.save_path', sys_get_temp_dir());
app_session_start();
$scenario = $argv[1];
$refreshes = 0;
$token = [
    'access_token' => 'fixture.user.signature', 'refresh_token' => 'fixture-refresh',
    'expires_in' => 3600, 'user' => ['id'=>'fixture-user','email'=>'fixture@example.invalid'],
];
$fixtureClient = new SupabaseAppClient('https://abcdefghijklmnopqrst.supabase.co', 'sb_publishable_fixture',
    static function ($method, $url, $headers, $body) use (&$refreshes, $scenario, $token) {
        if ($scenario === 'unavailable') return ['status'=>503,'body'=>'{}'];
        if ($scenario === 'invalid') return ['status'=>401,'body'=>'{}'];
        if (str_contains($url, '/token')) { $refreshes++; return ['status'=>200,'body'=>json_encode($token)]; }
        return ['status'=>200,'body'=>json_encode($token['user'])];
    });
function sb_app(): SupabaseAppClient { global $fixtureClient; return $fixtureClient; }
function expectSession(bool $condition): void { if (!$condition) throw new RuntimeException('Session regression: ' . $GLOBALS['scenario']); }
$_SESSION['aw_cookie'] = 'legacy-fixture';
$_SESSION['csrf_token'] = 'old-csrf-fixture';
sb_store_session($token, $scenario === 'remember');
expectSession(!isset($_SESSION['aw_cookie'], $_SESSION['csrf_token']));
if ($scenario === 'refresh') $_SESSION['sb_auth']['expires_at'] = 0;
if ($scenario === 'remember') { $_SESSION = []; $_COOKIE['mi_sb_refresh'] = 'fixture-refresh'; }
if ($scenario === 'invalid') {
    expectSession(!sb_restore_session() && empty($_SESSION['sb_auth']) && empty($_SESSION['logged_in']));
} elseif ($scenario === 'unavailable') {
    $failed = false;
    try { sb_restore_session(); } catch (SupabaseRequestException $error) { $failed = true; }
    expectSession($failed && !empty($_SESSION['sb_auth']));
} elseif ($scenario === 'logout') {
    sb_clear_session();
    expectSession(empty($_SESSION['logged_in']) && empty($_SESSION['sb_auth']));
} else {
    expectSession(sb_restore_session() && sb_access_token() === 'fixture.user.signature');
    expectSession($refreshes === (in_array($scenario, ['refresh','remember'], true) ? 1 : 0));
    expectSession(($_SESSION['USER_ID'] ?? '') === 'fixture-user');
}
$_SESSION = [];
session_destroy();
