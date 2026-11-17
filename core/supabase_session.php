<?php
/** Access tokens stay in server-side PHP sessions; persistent refresh cookie is HttpOnly. */
function sb_refresh_cookie(?string $token): void {
    setcookie('mi_sb_refresh', $token ?? '', [
        'expires' => $token === null ? time() - 3600 : time() + 86400 * 30,
        'path' => (defined('BASE_URL') ? BASE_URL : '') . '/',
        'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
        'httponly' => true, 'samesite' => 'Lax',
    ]);
}

function sb_clear_session(): void {
    unset($_SESSION['sb_auth'], $_SESSION['sb_recovery'], $_SESSION['logged_in'], $_SESSION['USER_ID'], $_SESSION['USER_EMAIL'], $_SESSION['auth_backend']);
    sb_refresh_cookie(null);
    unset($_COOKIE['mi_sb_refresh']);
}

function sb_store_session(array $tokens, bool $remember): void {
    $user = $tokens['user'] ?? null;
    if (!is_array($user) || !is_string($user['id'] ?? null)
        || !is_string($tokens['access_token'] ?? null) || !is_string($tokens['refresh_token'] ?? null)
        || !is_numeric($tokens['expires_in'] ?? null)) {
        throw new RuntimeException('Invalid authentication response.');
    }
    session_regenerate_id(true);
    unset($_SESSION['aw_cookie'], $_SESSION['csrf_token'], $_SESSION['sb_recovery']);
    $_SESSION['sb_auth'] = [
        'access_token' => $tokens['access_token'], 'refresh_token' => $tokens['refresh_token'],
        'expires_at' => time() + (int)$tokens['expires_in'], 'remember' => $remember,
    ];
    $_SESSION['auth_backend'] = 'supabase';
    $_SESSION['logged_in'] = true;
    $_SESSION['USER_ID'] = $user['id'];
    $_SESSION['USER_EMAIL'] = $user['email'] ?? '';
    sb_refresh_cookie($remember ? $tokens['refresh_token'] : null);
}

/** Remote /user validation on each request; no trust in locally decoded JWT fields. */
function sb_restore_session(): bool {
    if (isset($_SESSION['sb_recovery'])) return false;
    static $validated = false;
    if ($validated && !empty($_SESSION['sb_auth'])) return true;
    if (($_SESSION['auth_backend'] ?? '') !== 'supabase') {
        unset($_SESSION['logged_in'], $_SESSION['USER_ID'], $_SESSION['USER_EMAIL'], $_SESSION['aw_cookie']);
    }
    $auth = $_SESSION['sb_auth'] ?? null;
    $refresh = $auth['refresh_token'] ?? ($_COOKIE['mi_sb_refresh'] ?? null);
    try {
        if (!$auth || ($auth['expires_at'] ?? 0) <= time() + 60) {
            if (!$refresh) return false;
            sb_store_session(sb_app()->refresh($refresh), (bool)($auth['remember'] ?? true));
        }
        try {
            $user = sb_app()->user($_SESSION['sb_auth']['access_token']);
        } catch (SupabaseRequestException $error) {
            if ($error->httpStatus !== 401 || !$refresh) throw $error;
            sb_store_session(sb_app()->refresh($refresh), (bool)($auth['remember'] ?? true));
            $user = sb_app()->user($_SESSION['sb_auth']['access_token']);
        }
        if (!is_string($user['id'] ?? null) || $user['id'] !== ($_SESSION['USER_ID'] ?? null)) {
            throw new RuntimeException('Session identity could not be verified.');
        }
        $_SESSION['USER_EMAIL'] = $user['email'] ?? '';
        $_SESSION['logged_in'] = true;
        $validated = true;
        return true;
    } catch (SupabaseRequestException $error) {
        if (in_array($error->httpStatus, [400,401,403], true)) {
            sb_clear_session();
            return false;
        }
        throw $error;
    }
}

function sb_access_token(): string {
    if (!sb_restore_session()) throw new RuntimeException('Please sign in again.');
    return $_SESSION['sb_auth']['access_token'];
}

/** PKCE verifier: 32 random bytes, base64url without padding. */
function sb_pkce_verifier(): string {
    return rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
}

function sb_pkce_challenge(string $verifier): string {
    return rtrim(strtr(base64_encode(hash('sha256', $verifier, true)), '+/', '-_'), '=');
}

/** Start a PKCE flow and remember which one the callback must finish. */
function sb_pkce_start(string $flow, ?string $email = null): string {
    if (!in_array($flow, ['signup', 'recovery'], true)
        || ($email !== null && !filter_var($email, FILTER_VALIDATE_EMAIL))) {
        throw new InvalidArgumentException('Invalid email authentication intent.');
    }
    $verifier = sb_pkce_verifier();
    $_SESSION['sb_pkce_verifier'] = $verifier;
    $_SESSION['sb_pkce_flow'] = $flow;
    $_SESSION['sb_pkce_started_at'] = time();
    $_SESSION['sb_pkce_email'] = $email === null ? null : strtolower(trim($email));
    return sb_pkce_challenge($verifier);
}

/** Consume the verifier exactly once. */
function sb_pkce_take(): ?string {
    $verifier = $_SESSION['sb_pkce_verifier'] ?? null;
    unset($_SESSION['sb_pkce_verifier']);
    return is_string($verifier) ? $verifier : null;
}

function sb_pkce_clear(): void {
    unset($_SESSION['sb_pkce_verifier'], $_SESSION['sb_pkce_flow'], $_SESSION['pending_email'],
        $_SESSION['sb_pkce_started_at'], $_SESSION['sb_pkce_email']);
}

/** Email confirmation proves ownership; a fresh password login unlocks saved data. */
function sb_finish_signup_confirmation(array $tokens, callable $revoke): void {
    sb_clear_session();
    sb_pkce_clear();
    session_regenerate_id(true);
    unset($_SESSION['csrf_token']);
    try {
        $revoke($tokens['access_token']);
    } catch (Throwable $error) {
        // Never retain a provisional token locally, including on logout failure.
        error_log('[myInterpreter] provisional confirmation logout failed');
    }
    $_SESSION['sb_auth_notice'] = 'EMAIL_CONFIRMED';
}

function sb_pkce_pending(string $flow, string $email): bool {
    $started = $_SESSION['sb_pkce_started_at'] ?? null;
    return ($_SESSION['sb_pkce_flow'] ?? null) === $flow
        && is_string($_SESSION['sb_pkce_email'] ?? null)
        && hash_equals($_SESSION['sb_pkce_email'], strtolower(trim($email)))
        && is_string($_SESSION['sb_pkce_verifier'] ?? null)
        && preg_match('/^[A-Za-z0-9_-]{43,128}$/D', $_SESSION['sb_pkce_verifier']) === 1
        && is_int($started) && $started <= time() && $started >= time() - 3600;
}

/** Complete only an unexpired, one-use, same-browser email intent. */
function sb_pkce_exchange(string $code, callable $exchange): array {
    $verifier = $_SESSION['sb_pkce_verifier'] ?? null;
    $flow = $_SESSION['sb_pkce_flow'] ?? null;
    $email = $_SESSION['sb_pkce_email'] ?? null;
    $started = $_SESSION['sb_pkce_started_at'] ?? null;
    $currentUser = !empty($_SESSION['logged_in']) ? ($_SESSION['USER_ID'] ?? null) : null;
    sb_pkce_clear(); // Consume on failure too; never fall back to bearer fragments.
    if (!is_string($verifier) || !preg_match('/^[A-Za-z0-9_-]{43,128}$/D', $verifier)
        || !in_array($flow, ['signup', 'recovery'], true) || !is_string($email)
        || !filter_var($email, FILTER_VALIDATE_EMAIL) || !is_int($started)
        || $started > time() || $started < time() - 3600 || $code === '' || strlen($code) > 2048) {
        throw new RuntimeException('Invalid or expired authentication intent.');
    }
    $tokens = $exchange($code, $verifier);
    $user = is_array($tokens) ? ($tokens['user'] ?? null) : null;
    if (!is_array($user) || !is_string($user['id'] ?? null)
        || !is_string($user['email'] ?? null) || !hash_equals($email, strtolower($user['email']))
        || !is_string($user['email_confirmed_at'] ?? null) || !strtotime($user['email_confirmed_at'])
        || ($currentUser !== null && $currentUser !== $user['id'])) {
        throw new RuntimeException('Authentication identity does not match the request.');
    }
    return ['tokens' => $tokens, 'flow' => $flow];
}

/** Recovery tokens never become a trading/login session or a refresh cookie. */
function sb_begin_recovery(array $tokens): void {
    $user = $tokens['user'] ?? null;
    if (!is_array($user) || !is_string($user['id'] ?? null) || !is_string($user['email'] ?? null)
        || !is_string($tokens['access_token'] ?? null) || !is_numeric($tokens['expires_in'] ?? null)
        || (int)$tokens['expires_in'] <= 0) throw new RuntimeException('Invalid recovery response.');
    sb_clear_session();
    session_regenerate_id(true);
    unset($_SESSION['csrf_token']);
    $_SESSION['sb_recovery'] = ['access_token' => $tokens['access_token'],
        'user_id' => $user['id'], 'email' => strtolower($user['email']),
        'expires_at' => time() + min(900, (int)$tokens['expires_in'])];
}

function sb_recovery_access_token(?callable $validate = null): string {
    $recovery = $_SESSION['sb_recovery'] ?? null;
    try {
        if (!is_array($recovery) || !is_int($recovery['expires_at'] ?? null)
            || $recovery['expires_at'] <= time() || $recovery['expires_at'] > time() + 900
            || !is_string($recovery['access_token'] ?? null)) throw new RuntimeException('Recovery expired.');
        $user = $validate === null ? sb_app()->user($recovery['access_token']) : $validate($recovery['access_token']);
        if (!is_array($user) || ($user['id'] ?? null) !== $recovery['user_id']
            || !is_string($user['email'] ?? null) || strtolower($user['email']) !== $recovery['email']
            || empty($user['email_confirmed_at'])) throw new RuntimeException('Invalid recovery identity.');
        return $recovery['access_token'];
    } catch (Throwable $error) {
        unset($_SESSION['sb_recovery']);
        throw new RuntimeException('Recovery must be restarted.');
    }
}

/** Email destinations come from deployment configuration, never request headers. */
function sb_auth_redirect_url(string $publicUrl, string $path): string {
    $parts = parse_url($publicUrl);
    if (!filter_var($publicUrl, FILTER_VALIDATE_URL) || !is_array($parts)
        || ($parts['scheme'] ?? '') !== 'https' || empty($parts['host'])
        || isset($parts['user']) || isset($parts['pass'])
        || isset($parts['query']) || isset($parts['fragment']) || isset($parts['port'])
        || in_array(strtolower($parts['host']), ['localhost', '127.0.0.1', '[::1]'], true)
        || str_ends_with(strtolower($parts['host']), '.localhost')
        || preg_match('#^(?:/[A-Za-z0-9._~-]+)*/?$#D', $parts['path'] ?? '') !== 1
        || preg_match('~(?:^|/)\.{1,2}(?:/|$)~', $parts['path'] ?? '')
        || preg_match('~^/[A-Za-z0-9_-]+\.php$~D', $path) !== 1) {
        throw new RuntimeException('Configure a valid public HTTPS application URL.');
    }
    return rtrim($publicUrl, '/') . $path;
}

function sb_public_url(string $path): string {
    if (!defined('MYINTERPRETER_PUBLIC_URL')) {
        throw new RuntimeException('Configure the public application URL.');
    }
    return sb_auth_redirect_url(MYINTERPRETER_PUBLIC_URL, $path);
}

function sb_trade_request_id(): string {
    $bytes = random_bytes(16);
    $bytes[6] = chr((ord($bytes[6]) & 0x0f) | 0x40);
    $bytes[8] = chr((ord($bytes[8]) & 0x3f) | 0x80);
    $hex = bin2hex($bytes);
    return substr($hex,0,8) . '-' . substr($hex,8,4) . '-' . substr($hex,12,4) . '-' . substr($hex,16,4) . '-' . substr($hex,20);
}
