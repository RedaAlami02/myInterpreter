<?php
/**
 * Call requireLogin() at the top of every protected page.
 * Redirects to the app's index.php if the session is not authenticated.
 */
function requireLogin(): void {
    if (!isset($_SESSION['logged_in']) || $_SESSION['logged_in'] !== true) {
        $_SESSION['noLogin'] = true;
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    }
}
