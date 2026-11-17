<?php
// A transient remote failure must preserve retry credentials, not authenticate the page.
$_SESSION = ['logged_in' => true];
$_SERVER['REQUEST_METHOD'] = 'GET';
$_POST = $_GET = [];
function sb_restore_session(): bool {
    throw new RuntimeException('Synthetic unavailable service');
}
require __DIR__ . '/../handlers/supabase_auth.php';
if ($sessionValidated !== false || $loginError === '' || $_SESSION['logged_in'] !== true) {
    throw new RuntimeException('Transient authentication failure handled incorrectly.');
}
echo "Homepage authentication outage regression passed.\n";
