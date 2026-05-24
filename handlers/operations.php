<?php
session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
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

// ─── Build company object, filling blanks from Appwrite ──────────────────────
$company = new Company($inputs);

$docs = aw_list_docs('company', [q_equal('name', $inputs['NAME']), q_limit(1)]);
if (!empty($docs)) {
    $row = $docs[0];
    $company->stored  = true;
    $company->_awId   = $row['$id'];   // store doc ID for update later
    // Map lowercase Appwrite fields to Company uppercase properties
    $fieldMap = ['BPA' => 'bpa', 'TC5' => 'tc5', 'ROE' => 'roe', 'NA' => 'na', 'CP' => 'cp'];
    foreach ($fieldMap as $prop => $awField) {
        if (empty($inputs[$prop]) && isset($row[$awField])) {
            $company->$prop = (float) $row[$awField];
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
