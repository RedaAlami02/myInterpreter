<?php
/**
 * Saves market enrichment data to the company collection.
 * POST { name, symbol } updates the company through the authenticated adapter.
 */
require_once __DIR__ . '/../core/session.php';
app_session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
requireAdmin();
header('Content-Type: application/json');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    header('Allow: POST');
    echo json_encode(['ok' => false, 'msg' => 'method not allowed']);
    exit;
}
// Preserve an explicit form token; use the header only when it is absent.
$_POST['csrf_token'] = $_POST['csrf_token'] ?? ($_SERVER['HTTP_X_CSRF_TOKEN'] ?? '');
csrf_verify();

if (!is_string($_POST['name'] ?? null) || !is_string($_POST['symbol'] ?? null)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'msg' => 'invalid params']);
    exit;
}
$name   = trim($_POST['name']   ?? '');
$symbol = preg_replace('/[^A-Z0-9]/', '', strtoupper($_POST['symbol'] ?? ''));
if (!$name || !$symbol || mb_strlen($name) > 200 || strlen($symbol) > 32) { http_response_code(400); echo json_encode(['ok'=>false,'msg'=>'missing params']); exit; }

// Fetch enrichment data directly (no self-curl)
require_once __DIR__ . '/market_proxy.php';
$data = mkt_fetch_symbol($symbol);
if (!$data || !empty($data['error'])) {
    echo json_encode(['ok'=>false,'msg'=>'proxy unavailable']); exit;
}

$c = $data['computed'] ?? [];
$update = array_filter([
    'ext_name'      => $data['ext_name']    ?? null,
    'sector'        => $data['sector']      ?? null,
    'description'   => $data['description'] ?? null,
    'shareholders'  => $c['shareholders']   ?? null,
    'beta_3y'       => $c['beta_3y']        ?? null,
    'beta_5y'       => $c['beta_5y']        ?? null,
    'revenue'       => $c['revenue']        ?? null,
    'ebitda'        => $c['ebitda']         ?? null,
    'ebit'          => $c['ebit']           ?? null,
    'net_profit'    => $c['net_profit']     ?? null,
    'fcf'           => $c['fcf']            ?? null,
    'net_debt'      => $c['net_debt']       ?? null,
    'net_cash'      => $c['net_cash']       ?? null,
    'total_assets'  => $c['total_assets']   ?? null,
    'profit_margin' => $c['profit_margin']  ?? null,
    'rev_growth_5y' => $c['rev_growth_5y']  ?? null,
    'rnpg_growth_5y'=> $c['rnpg_growth_5y'] ?? null,
], fn($v) => $v !== null && $v !== '');

if (empty($update)) { echo json_encode(['ok'=>true,'msg'=>'nothing to save']); exit; }

try {
    $receipt = sb_admin()->updateCompany(sb_access_token(), $name, $update);
    if ($receipt['status'] === 'MISSING') {
        echo json_encode(['ok'=>false,'msg'=>'company not found']); exit;
    }
    echo json_encode(['ok'=>true,'saved'=>$receipt['fields'],'description'=>!empty($update['description'])]);
} catch (Throwable $e) {
    error_log('[myInterpreter] save_enrichment error for "' . $name . '": ' . $e->getMessage());
    echo json_encode(['ok'=>false,'msg'=>'save unavailable']);
}
