<?php
/**
 * Saves market enrichment data to the company collection.
 * POST { name, symbol }  →  fetches proxy and updates Appwrite doc.
 */
session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
requireAdmin();
header('Content-Type: application/json');
// CSRF: accept from POST field or X-CSRF-Token header
$_POST['_csrf'] = $_POST['_csrf'] ?? ($_SERVER['HTTP_X_CSRF_TOKEN'] ?? '');
csrf_verify();

$name   = trim($_POST['name']   ?? '');
$symbol = preg_replace('/[^A-Z0-9]/', '', strtoupper($_POST['symbol'] ?? ''));
if (!$name || !$symbol) { echo json_encode(['ok'=>false,'msg'=>'missing params']); exit; }

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
    $docs = aw_list_docs('company', [q_equal('name', $name), q_limit(1)]);
    if (empty($docs)) { echo json_encode(['ok'=>false,'msg'=>'company not found']); exit; }
    aw_update_doc('company', $docs[0]['$id'], $update);
    echo json_encode(['ok'=>true,'saved'=>count($update),'description'=>!empty($update['description'])]);
} catch (Throwable $e) {
    echo json_encode(['ok'=>false,'msg'=>$e->getMessage()]);
}
