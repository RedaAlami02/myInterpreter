<?php
// ─── Appwrite connection constants are defined in core/Appwrite.php ───────────

// ─── App base URL — derived from the HTTP request, never from __FILE__ ────────
// Using __FILE__ or realpath() follows symlinks, giving the real filesystem path
// (e.g. /home/user/project) instead of the URL path (/myInterpreter).
// $_SERVER['SCRIPT_NAME'] is always the URL path of the originally-called script
// and is completely unaffected by symlinks.
//
// Known one-level subdirectories of the project root:
$_subdirs = ['handlers', 'core', 'config', 'assets', 'scrapping'];
$_snDir   = dirname($_SERVER['SCRIPT_NAME']); // URL dir of calling script
// e.g. /myInterpreter  (for root pages)
// e.g. /myInterpreter/handlers  (for handler pages)
if (in_array(basename($_snDir), $_subdirs, true)) {
    $_root = dirname($_snDir); // go up one more level
} else {
    $_root = $_snDir;
}
define('BASE_URL', $_root === '/' ? '' : rtrim($_root, '/'));
unset($_subdirs, $_snDir, $_root);

// ─── Admin ────────────────────────────────────────────────────────────────────
define('ADMIN_USER_ID', '6a124b8900257649d4c1');

// ─── Portfolio ────────────────────────────────────────────────────────────────
define('TAX_RATE', 0.10);   // 10 % tax applied to gross profit

// ─── Ratio thresholds (green / orange; above orange = red) ───────────────────
define('PER_GREEN',  20);   define('PER_ORANGE',  25);
define('PEG_GREEN',   1);   define('PEG_ORANGE',   2);
define('PR_GREEN',  1.5);   define('PR_ORANGE',  2.0);
define('PB_GREEN',  2.0);   define('PB_ORANGE',  3.0);

// ─── Date formatting ──────────────────────────────────────────────────────────
// Converts Appwrite ISO timestamps (2026-05-22T00:00:00.000+00:00) to dd/mm/yyyy
function fmt_date(?string $iso, string $fallback = '—'): string {
    if (!$iso) return $fallback;
    try {
        return (new DateTime($iso))->format('d/m/Y');
    } catch (Exception $e) {
        return $fallback;
    }
}

// ─── CSRF helpers ─────────────────────────────────────────────────────────────
function csrf_token(): string {
    if (session_status() === PHP_SESSION_NONE) session_start();
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function csrf_verify(): void {
    $token = $_POST['csrf_token'] ?? '';
    if (!hash_equals($_SESSION['csrf_token'] ?? '', $token)) {
        http_response_code(403);
        die('Invalid request (CSRF token mismatch).');
    }
}

function csrf_field(): string {
    return '<input type="hidden" name="csrf_token" value="'
        . htmlspecialchars(csrf_token(), ENT_QUOTES) . '">';
}
