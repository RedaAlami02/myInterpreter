<?php
function app_session_start(): void {
    if (session_status() !== PHP_SESSION_ACTIVE) {
        // With session.auto_start the session is already running (and the
        // limiter already applied) before this file is reached, so the header
        // below is what actually decides cacheability on both hosts.
        session_cache_limiter('private, max-age=60');
        ini_set('session.use_strict_mode', '1');
        session_set_cookie_params([
            'httponly' => true, 'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
            'samesite' => 'Lax', 'path' => '/',
        ]);
        session_start();
    }
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET' && !headers_sent()) {
        // Prefetching the next page only helps if the browser may reuse it.
        // Private keeps it to one browser and never a shared cache; 60 s is
        // shorter than a quote publication, so a page cannot outlive its data.
        // Pages that must not be cached overwrite this with no-store.
        header('Cache-Control: private, max-age=60');
        header('Expires: ' . gmdate('D, d M Y H:i:s', time() + 60) . ' GMT');
        header_remove('Pragma');
    }
}
