<?php
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/config/config.php';
require_once __DIR__ . '/core/Appwrite.php';
require_once __DIR__ . '/core/i18n.php';

$callbackError = null;
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_verify();
    http_response_code(400);
    $callbackError = 'Lien invalide ou expiré.';
}

if ($callbackError === null && isset($_GET['code']) && is_string($_GET['code'])) {
    try {
        $result = sb_pkce_exchange($_GET['code'], fn($code, $verifier) => sb_app()->exchangeCode($code, $verifier));
        $verifiedUser = sb_app()->user($result['tokens']['access_token']);
        if (($verifiedUser['id'] ?? null) !== $result['tokens']['user']['id']
            || strtolower($verifiedUser['email'] ?? '') !== strtolower($result['tokens']['user']['email'])
            || empty($verifiedUser['email_confirmed_at'])) throw new RuntimeException('Unverified callback identity.');
        $result['tokens']['user'] = $verifiedUser;
        $recovery = $result['flow'] === 'recovery';
        if ($recovery) sb_begin_recovery($result['tokens']);
        else sb_finish_signup_confirmation($result['tokens'], fn($token) => sb_app()->signOut($token));
        header('Location: ' . BASE_URL . ($recovery ? '/auth_reset.php' : '/index.php'));
        exit();
    } catch (Throwable $failure) {
        error_log('[myInterpreter] auth callback code exchange failed');
        $callbackError = 'Lien invalide, expiré, ou ouvert dans un autre navigateur.';
    }
}
?>
<!DOCTYPE html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex">
  <title><?= te('Confirmation') ?> — myInterpreter</title>
  <style>
    :root { color-scheme: dark; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; background:#0b1220;
      color:#e2e8f0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; padding:24px; }
    .card { width:100%; max-width:420px; background:#111a2e; border:1px solid #1f2a44;
      border-radius:16px; padding:28px; box-shadow:0 24px 60px rgba(0,0,0,.35); }
    h1 { font-size:1.15rem; margin:0 0 12px; }
    p { color:#94a3b8; line-height:1.55; font-size:.92rem; }
    a.button { display:inline-block; margin-top:8px; padding:10px 16px; border-radius:10px;
      background:#22d3ee; color:#04121a; font-weight:700; text-decoration:none; }
    .error { color:#f87171; }
  </style>
</head>
<body>
  <div class="card">
    <h1><?= te('Confirmation') ?></h1>
    <?php if ($callbackError): ?>
      <p class="error"><?= te($callbackError) ?></p>
      <a class="button" href="<?= BASE_URL ?>/index.php"><?= te('Retour à la connexion') ?></a>
    <?php else: ?>
      <p class="error"><?= te('Lien invalide, expiré, ou ouvert dans un autre navigateur.') ?></p>
      <a class="button" href="<?= BASE_URL ?>/index.php"><?= te('Retour à la connexion') ?></a>
    <?php endif; ?>
  </div>
  <script>
    // Clear invalid credentials/codes from browser history without adopting them.
    window.history.replaceState(null, '', window.location.pathname);
  </script>
</body>
</html>
