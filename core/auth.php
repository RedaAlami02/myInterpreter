<?php
/**
 * Call requireLogin() at the top of every protected page.
 * Restores and validates the Supabase session.
 * Redirects to index.php if not authenticated.
 */
function requireLogin(): void {
    try {
        if (sb_restore_session()) return;
    } catch (Throwable $error) {
        http_response_code(503);
        exit('Authentication service is temporarily unavailable. Please retry.');
    }
    header('Location: ' . BASE_URL . '/index.php');
    exit();
}

function requireAdmin(): void {
    require_once __DIR__ . '/i18n.php';
    requireLogin();
    if (aw_user_id() !== ADMIN_USER_ID) {
        http_response_code(403);
        die('<div lang="' . ui_locale() . '" dir="' . ui_direction() . '" style="font-family:sans-serif;padding:3rem;text-align:center;color:#f43f5e"><h2>403 — ' . te('Accès refusé') . '</h2><p>' . te('Cette page est réservée à l\'administrateur.') . '</p><a href="' . BASE_URL . '/index.php">' . te('Retour') . '</a></div>');
    }
}

function is_admin(): bool {
    return aw_user_id() === ADMIN_USER_ID;
}
