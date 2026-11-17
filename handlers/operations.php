<?php
require_once __DIR__ . '/../core/session.php';
app_session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
require_once __DIR__ . '/../core/Action.php';

requireAdmin();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: ' . BASE_URL . '/Update.php');
    exit();
}

csrf_verify();

$action = $_POST['action'] ?? '';
$green_fields = ['BPA', 'DPA', 'TC5', 'ROE', 'NA', 'CP'];
$errors = [];

// Reject array-shaped form values before string/number conversion.
foreach (['action', 'NAME', 'PA', 'BPA', 'DPA', 'TC5', 'ROE', 'NA', 'CP'] as $field) {
    if (isset($_POST[$field]) && !is_string($_POST[$field])) {
        http_response_code(400);
        exit('Invalid form input.');
    }
}

$inputs = [
    'NAME' => trim($_POST['NAME'] ?? ''),
    'PA'   => $_POST['PA']  ?? '',
    'BPA'  => $_POST['BPA'] ?? '',
    'DPA'  => $_POST['DPA'] ?? '',
    'TC5'  => $_POST['TC5'] ?? '',
    'ROE'  => $_POST['ROE'] ?? '',
    'NA'   => $_POST['NA']  ?? '',
    'CP'   => $_POST['CP']  ?? '',
];

foreach ($inputs as $field => &$value) {
    $value = trim($value);
    if ($field !== 'NAME' && $value !== '') {
        if (!is_numeric($value) || !is_finite((float)$value)) {
            $errors[] = 'Valeur numérique invalide : ' . $field;
        }
    }
}
unset($value);
if (!in_array($action, ['big_update', 'save_changes', 'save_immediately'], true)) {
    $errors[] = 'Action invalide.';
}

// ─── Validation ──────────────────────────────────────────────────────────────
if (empty($inputs['NAME'])) {
    $errors[] = 'Le nom de la société est requis.';
}

if ($action === 'big_update') {
    $any_green = false;
    foreach ($green_fields as $f) {
        if ($inputs[$f] !== '') { $any_green = true; break; }
    }
    if (!$any_green) {
        $errors[] = '<span style="color:#22d3ee">Remplissez au moins un champ VERT.</span>';
    }
} elseif ($action === 'save_changes' || $action === 'save_immediately') {
    if (empty($inputs['PA'])) {
        $errors[] = 'Le champ "Prix de l\'action" est requis.';
    }
}

if (!empty($errors)) {
    $_SESSION['erreurs']  = $errors;
    $_SESSION['old_post'] = $_POST;
    header('Location: ' . BASE_URL . '/Update.php');
    exit();
}

// ─── Build company object, filling blanks from Appwrite ──────────────────────
$company = new Company($inputs);

try {
    $docs = aw_list_docs('company', [q_equal('name', $inputs['NAME']), q_limit(1)]);
} catch (Throwable $e) {
    error_log('[myInterpreter] operations.php aw_list_docs error: ' . $e->getMessage());
    $_SESSION['erreurs']  = ['Service temporairement indisponible. Veuillez réessayer.'];
    $_SESSION['old_post'] = $_POST;
    header('Location: ' . BASE_URL . '/Update.php');
    exit();
}

if (!empty($docs)) {
    $row = $docs[0];
    $company->stored  = true;
    $company->_awId   = $row['$id'];   // store doc ID for update later
    // Map lowercase Appwrite fields to Company uppercase properties
    $fieldMap = ['BPA' => 'bpa', 'DPA' => 'dpa', 'TC5' => 'tc5', 'ROE' => 'roe', 'NA' => 'na', 'CP' => 'cp'];
    foreach ($fieldMap as $prop => $awField) {
        if ($inputs[$prop] === '' && isset($row[$awField])) {
            $company->$prop = (float) $row[$awField];
        }
    }
}

// Explicit user input always wins
foreach ($inputs as $key => $val) {
    if ($key !== 'NAME' && $val !== '') {
        $company->$key = (float) $val;
    }
}

// ─── Store in session and redirect ───────────────────────────────────────────
unset($_SESSION['analysis_save_notice']);
unset($_SESSION['save']); // A previous immediate-save request must not carry forward.
if ($action === 'save_immediately') {
    $_SESSION['save'] = true;
}
$_SESSION['company'] = $company;
unset($_SESSION['old_post']);

header('Location: ' . BASE_URL . '/results.php');
exit();
