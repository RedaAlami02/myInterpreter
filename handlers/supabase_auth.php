<?php
// Included by index.php before rendering; all mutations require its CSRF check.
$loginError = '';
$sessionValidated = false;
$loginNotice = '';
if (($_SESSION['sb_auth_notice'] ?? null) === 'EMAIL_CONFIRMED') {
    $loginNotice = 'Email confirmé. Connectez-vous avec votre mot de passe pour retrouver votre portefeuille.';
}
unset($_SESSION['sb_auth_notice']);
$isSignUp = isset($_POST['signup_form']);
$isResetRequest = isset($_POST['reset_request']);
$pendingEmail = is_string($_SESSION['pending_email'] ?? null) ? $_SESSION['pending_email'] : '';
if (isset($_GET['reset']) && $_GET['reset'] === '1') {
    $loginNotice = 'Votre mot de passe a été modifié. Connectez-vous avec le nouveau.';
}
try {
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['logout'])) {
        try {
            if (sb_restore_session()) sb_app()->signOut(sb_access_token());
        } finally {
            sb_clear_session();
            sb_pkce_clear();
            $_SESSION = [];
            session_regenerate_id(true);
        }
        header('Location: ' . BASE_URL . '/index.php');
        exit();
    }
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['reset_request'])) {
        $email = is_string($_POST['email'] ?? null) ? trim($_POST['email']) : '';
        // The answer is identical whether or not an account exists.
        if (filter_var($email, FILTER_VALIDATE_EMAIL)) {
            try {
                $redirect = sb_public_url('/auth_callback.php');
                sb_app()->recover(
                    $email,
                    $redirect,
                    sb_pkce_start('recovery', $email)
                );
            } catch (Throwable $error) {
                error_log('[myInterpreter] password reset request failed');
            }
        }
        $loginNotice = 'Si un compte existe pour cet email, un lien de réinitialisation a été envoyé.';
    }
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['resend_confirmation'])) {
        $email = is_string($_POST['email'] ?? null) ? trim($_POST['email']) : $pendingEmail;
        if (filter_var($email, FILTER_VALIDATE_EMAIL) && sb_pkce_pending('signup', $email)) {
            try {
                sb_app()->resendConfirmation($email, sb_public_url('/auth_callback.php'), sb_pkce_start('signup', $email));
                $_SESSION['pending_email'] = $email;
                $pendingEmail = $email;
            } catch (Throwable $error) {
                error_log('[myInterpreter] confirmation resend failed');
            }
            $loginNotice = 'Si ce compte attend une confirmation, un nouvel email a été envoyé.';
        } else {
            $loginNotice = 'Recommencez l’inscription dans ce navigateur pour recevoir un nouveau lien.';
        }
    }
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && (isset($_POST['signup_form']) || isset($_POST['login_form']))) {
        $email = is_string($_POST['email'] ?? null) ? trim($_POST['email']) : '';
        $password = is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
        $name = is_string($_POST['name'] ?? null) ? trim($_POST['name']) : '';
        if (!filter_var($email, FILTER_VALIDATE_EMAIL) || $password === '' || strlen($name) > 200) {
            $loginError = 'Veuillez vérifier votre email et votre mot de passe.';
        } else {
            if ($isSignUp) {
                $redirect = sb_public_url('/auth_callback.php');
                $tokens = sb_app()->signUp(
                    $email,
                    $password,
                    $name,
                    sb_pkce_start('signup', $email),
                    $redirect
                );
            } else {
                $tokens = sb_app()->signIn($email, $password);
            }
            if (empty($tokens['access_token'])) {
                // Confirm-email projects return a user, not a session. Do not
                // pretend the user is logged in or disable email confirmation.
                $_SESSION['pending_email'] = $email;
                $pendingEmail = $email;
                $loginNotice = 'Vérifiez votre email pour confirmer votre compte, puis connectez-vous.';
            } else {
                sb_store_session($tokens, !empty($_POST['stay']));
                sb_pkce_clear();
                header('Location: ' . BASE_URL . '/index.php');
                exit();
            }
        }
    }
    $sessionValidated = sb_restore_session();
} catch (SupabaseRequestException $error) {
    $loginError = match (true) {
        $error->httpStatus === 429 => 'Trop de tentatives. Veuillez patienter avant de réessayer.',
        $error->reason === 'email_not_confirmed' => 'Confirmez votre adresse email avant de vous connecter.',
        $error->httpStatus >= 500 => 'Service temporairement indisponible. Veuillez réessayer.',
        default => 'Connexion ou inscription impossible. Vérifiez vos informations et votre email de confirmation.',
    };
} catch (Throwable $error) {
    $loginError = 'Service temporairement indisponible. Veuillez réessayer.';
}
