<?php
/**
 * Call requireLogin() at the top of every protected page.
 * Restores Appwrite session from cookie if aw_secret is missing.
 * Redirects to index.php if not authenticated.
 */
function requireLogin(): void {
    // Restore aw_cookie from browser cookie if session exists but cookie string is missing
    if (isset($_SESSION['logged_in']) && empty($_SESSION['aw_cookie']) && isset($_COOKIE['aw_session'])) {
        $_SESSION['aw_cookie'] = $_COOKIE['aw_session'];
    }

    // Full restore: PHP session was wiped but browser cookie still exists
    if (!isset($_SESSION['logged_in']) && isset($_COOKIE['aw_session'])) {
        $_SESSION['aw_cookie'] = $_COOKIE['aw_session'];
        $me = aw_get('/account', $_SESSION['aw_cookie']);
        if (isset($me['body']['$id'])) {
            $_SESSION['logged_in']  = true;
            $_SESSION['USER_ID']    = $me['body']['$id'];
            $_SESSION['USER_EMAIL'] = $me['body']['email'] ?? '';
        } else {
            setcookie('aw_session', '', time() - 3600, '/', '', false, true);
            unset($_SESSION['aw_cookie']);
        }
    }

    if (!isset($_SESSION['logged_in']) || $_SESSION['logged_in'] !== true) {
        $_SESSION['noLogin'] = true;
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    }
}

function requireAdmin(): void {
    requireLogin();
    if (aw_user_id() !== ADMIN_USER_ID) {
        http_response_code(403);
        die('<div style="font-family:sans-serif;padding:3rem;text-align:center;color:#f43f5e"><h2>403 — Accès refusé</h2><p>Cette page est réservée à l\'administrateur.</p><a href="' . BASE_URL . '/index.php">Retour</a></div>');
    }
}

function is_admin(): bool {
    return aw_user_id() === ADMIN_USER_ID;
}
