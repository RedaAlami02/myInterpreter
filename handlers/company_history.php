<?php
require_once __DIR__ . '/../core/session.php';
app_session_start();
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/company_history.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    http_response_code(405);
    header('Allow: GET');
    echo '{"error":"Method not allowed."}';
    exit;
}
$name = $_GET['name'] ?? null;
if (array_diff(array_keys($_GET), ['name']) || !is_string($name) || $name === '' || mb_strlen($name) > 160) {
    http_response_code(400);
    echo '{"error":"Invalid company."}';
    exit;
}
try {
    if (!sb_restore_session()) {
        http_response_code(401);
        echo '{"error":"Sign in required."}';
        exit;
    }
    $token = sb_access_token();
    // Release the PHP session lock before waiting on the database, allowing
    // chart and financial-profile requests from this browser to run together.
    session_write_close();
    $document = sb_app()->companyDailyHistory($token, $name);
    echo json_encode(company_history_points($document, $name), JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    http_response_code(503);
    echo '{"error":"Company history is temporarily unavailable."}';
}
