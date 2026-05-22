<?php
session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/auth.php';
require_once __DIR__ . '/../core/Database.php';
require_once __DIR__ . '/../core/Action.php';

requireLogin();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: ' . BASE_URL . '/Update.php');
    exit();
}

csrf_verify();

$action = $_POST['action'] ?? '';
$green_fields = ['BPA', 'TC5', 'ROE', 'NA', 'CP'];
$errors = [];

$inputs = [
    'NAME' => trim($_POST['NAME'] ?? ''),
    'PA'   => $_POST['PA']  ?? '',
    'BPA'  => $_POST['BPA'] ?? '',
    'TC5'  => $_POST['TC5'] ?? '',
    'ROE'  => $_POST['ROE'] ?? '',
    'NA'   => $_POST['NA']  ?? '',
    'CP'   => $_POST['CP']  ?? '',
];

// ─── Validation ──────────────────────────────────────────────────────────────
if (empty($inputs['NAME'])) {
    $errors[] = 'Le nom de la société est requis.';
}

if ($action === 'big_update') {
    $any_green = false;
    foreach ($green_fields as $f) {
        if (!empty($inputs[$f])) { $any_green = true; break; }
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

// ─── Build company object, filling blanks from DB ────────────────────────────
$db  = (new Database())->opendb();

$company = new Company($inputs);

$stmt = $db->prepare('SELECT * FROM COMPANY WHERE NAME = ?');
$stmt->execute([$inputs['NAME']]);
$row = $stmt->fetch();

if ($row) {
    $company->stored = true;
    // Fill any blank inputs from the DB record
    foreach ($inputs as $key => $val) {
        if ($key === 'NAME') continue;
        if (empty($val) && isset($row[$key])) {
            $company->$key = (float) $row[$key];
        }
    }
}

// Explicit user input always wins
foreach ($inputs as $key => $val) {
    if ($key !== 'NAME' && !empty($val)) {
        $company->$key = (float) $val;
    }
}

// ─── Store in session and redirect ───────────────────────────────────────────
if ($action === 'save_immediately') {
    $_SESSION['save'] = true;
}
$_SESSION['company'] = $company;
unset($_SESSION['old_post']);

header('Location: ' . BASE_URL . '/results.php');
exit();
