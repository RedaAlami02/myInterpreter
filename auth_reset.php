<?php
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/config/config.php';
require_once __DIR__ . '/core/Appwrite.php';
require_once __DIR__ . '/core/auth.php';
require_once __DIR__ . '/core/i18n.php';
try {
    $recoveryToken = sb_recovery_access_token();
} catch (Throwable $failure) {
    header('Location: ' . BASE_URL . '/index.php');
    exit();
}
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');

$resetError = null;
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_verify();
    if (isset($_POST['cancel_recovery'])) {
        try { sb_app()->signOut($recoveryToken); }
        catch (Throwable $failure) { error_log('[myInterpreter] recovery cancellation revocation unavailable'); }
        sb_clear_session();
        sb_pkce_clear();
        session_regenerate_id(true);
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    }
    $password = is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
    $confirm = is_string($_POST['confirm'] ?? null) ? $_POST['confirm'] : '';
    if (strlen($password) < 8 || strlen($password) > 128) {
        $resetError = 'Le mot de passe doit contenir entre 8 et 128 caractères.';
    } elseif (!hash_equals($password, $confirm)) {
        $resetError = 'Les deux mots de passe ne correspondent pas.';
    } else {
        try {
            sb_app()->updatePassword($recoveryToken, $password);
            try { sb_app()->signOut($recoveryToken); }
            catch (Throwable $failure) { error_log('[myInterpreter] recovery session revocation unavailable'); }
            sb_clear_session();
            sb_pkce_clear();
            $_SESSION = [];
            session_regenerate_id(true);
            header('Location: ' . BASE_URL . '/index.php?reset=1');
            exit();
        } catch (SupabaseRequestException $error) {
            error_log('[myInterpreter] password update rejected: ' . $error->httpStatus);
            $resetError = $error->httpStatus === 422
                ? 'Ce mot de passe ne respecte pas la politique du compte.'
                : 'Impossible de modifier le mot de passe. Réessayez.';
        } catch (Throwable $error) {
            error_log('[myInterpreter] password update failed');
            $resetError = 'Impossible de modifier le mot de passe. Réessayez.';
        }
    }
}
?>
<!DOCTYPE html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex">
  <title><?= te('Nouveau mot de passe') ?> — myInterpreter</title>
  <style>
    :root { color-scheme: dark; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; background:#0b1220;
      color:#e2e8f0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; padding:24px; }
    .card { width:100%; max-width:420px; background:#111a2e; border:1px solid #1f2a44;
      border-radius:16px; padding:28px; box-shadow:0 24px 60px rgba(0,0,0,.35); }
    h1 { font-size:1.15rem; margin:0 0 12px; }
    p { color:#94a3b8; line-height:1.55; font-size:.92rem; }
    label { display:block; color:#94a3b8; font-size:.8rem; margin:14px 0 6px; }
    input { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:10px;
      border:1px solid #24304d; background:#0d1526; color:#e2e8f0; font-size:.95rem; }
    button { width:100%; margin-top:18px; padding:11px 16px; border-radius:10px; border:0;
      background:#22d3ee; color:#04121a; font-weight:700; font-size:.95rem; cursor:pointer; }
    .error { color:#f87171; margin-top:12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1><?= te('Choisissez un nouveau mot de passe') ?></h1>
    <p><?= te('Le lien de réinitialisation vous a connecté temporairement. Définissez un nouveau mot de passe, puis reconnectez-vous.') ?></p>
    <?php if ($resetError): ?>
      <p class="error"><?= te($resetError) ?></p>
    <?php endif; ?>
    <form method="POST" action="">
      <?= csrf_field() ?>
      <label for="password"><?= te('Nouveau mot de passe') ?></label>
      <input id="password" type="password" name="password" minlength="8" maxlength="128"
        autocomplete="new-password" required>
      <label for="confirm"><?= te('Confirmer le mot de passe') ?></label>
      <input id="confirm" type="password" name="confirm" minlength="8" maxlength="128"
        autocomplete="new-password" required>
      <button type="submit"><?= te('Enregistrer') ?></button>
    </form>
    <form method="POST" action="">
      <?= csrf_field() ?>
      <button type="submit" name="cancel_recovery" value="1"><?= te('Annuler') ?></button>
    </form>
  </div>
</body>
</html>
