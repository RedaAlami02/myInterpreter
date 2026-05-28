<?php
/**
 * Market data proxy — server-side aggregator.
 * GET ?symbol=ATW  →  JSON with enrichment data + computed fundamentals.
 * Parallel curl for performance.
 */
session_start();
require_once __DIR__ . '/../config/config.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=3600');

$symbol = preg_replace('/[^A-Z0-9]/', '', strtoupper($_GET['symbol'] ?? ''));
if (!$symbol) { echo json_encode(['error' => 'symbol required']); exit; }

// ── Parallel curl ─────────────────────────────────────────────────────────────
function mkt_batch(array $requests): array {
    $mh = curl_multi_init();
    $handles = [];
    foreach ($requests as $key => $spec) {
        $ch  = curl_init($spec['url']);
        $hdr = array_merge(['Accept: */*', 'User-Agent: Mozilla/5.0 (compatible)'], $spec['extra_headers'] ?? []);
        $opts = [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10, CURLOPT_HTTPHEADER => $hdr];
        if (!empty($spec['post'])) {
            $opts[CURLOPT_POST]         = true;
            $opts[CURLOPT_POSTFIELDS]   = $spec['post'];
            $opts[CURLOPT_HTTPHEADER][] = 'Content-Type: application/json';
        }
        curl_setopt_array($ch, $opts);
        curl_multi_add_handle($mh, $ch);
        $handles[$key] = $ch;
    }
    $running = null;
    do { curl_multi_exec($mh, $running); curl_multi_select($mh, 0.1); } while ($running > 0);
    $results = [];
    foreach ($handles as $key => $ch) {
        $body = curl_multi_getcontent($ch);
        $results[$key] = $body ? (json_decode($body, true) ?? null) : null;
        curl_multi_remove_handle($mh, $ch);
    }
    curl_multi_close($mh);
    return $results;
}

function mkt_sb(string $t, string $col, string $val, bool $single = true, ?string $sel = null): string {
    $o = ['filter' => ['column' => $col, 'value' => $val], 'single' => $single];
    if ($sel) $o['select'] = $sel;
    return json_encode(['table' => $t, 'options' => $o]);
}

// ── Data source endpoints (backend-private) ───────────────────────────────────
$_SRC1 = 'https://www.idbourse.com/api/proxy';
$_SRC2 = 'https://www.idbourse.com/api/proxy/supabase';

// ── Step 1: live stock data + financial summary + symbol registry ─────────────
$s1 = mkt_batch([
    'stock'     => ['url' => "{$_SRC1}/stock/{$symbol}"],
    'financial' => ['url' => "{$_SRC1}/financial/{$symbol}"],
    'symlinks'  => ['url' => "{$_SRC1}/symblinks"],
]);

$stock    = $s1['stock'] ?? null;
$fin      = $s1['financial']['financialData'] ?? [];
$symlinks = $s1['symlinks'] ?? [];

$ext_name = null; $sector = null;
if (is_array($symlinks)) {
    foreach ($symlinks as $s) {
        if (($s['symbol'] ?? '') === $symbol) { $ext_name = $s['name'] ?? null; $sector = $s['type'] ?? null; break; }
    }
}
if (!$ext_name && $stock) $ext_name = $stock['name'] ?? null;

// ── Step 2: all financial tables in parallel ──────────────────────────────────
$s2 = [];
if ($ext_name) {
    $soc = $ext_name;
    $s2  = mkt_batch([
        'rnpg'     => ['url' => $_SRC2, 'post' => mkt_sb('rnpg-corpo',    'Société', $soc)],
        'ca'       => ['url' => $_SRC2, 'post' => mkt_sb('ca-corpo',      'Société', $soc)],
        'ebe'      => ['url' => $_SRC2, 'post' => mkt_sb('ebe-corpo',     'Société', $soc)],
        'ebit'     => ['url' => $_SRC2, 'post' => mkt_sb('ebit-corpo',    'Société', $soc)],
        'fp'       => ['url' => $_SRC2, 'post' => mkt_sb('fp-corpo',      'Société', $soc)],
        'dn'       => ['url' => $_SRC2, 'post' => mkt_sb('dn-corpo',      'Société', $soc)],
        'tn'       => ['url' => $_SRC2, 'post' => mkt_sb('tn-corpo',      'Société', $soc)],
        'dpa'      => ['url' => $_SRC2, 'post' => mkt_sb('dpa-corpo',     'Société', $soc)],
        'fcf'      => ['url' => $_SRC2, 'post' => mkt_sb('fcf-corpo',     'Société', $soc)],
        'actif'    => ['url' => $_SRC2, 'post' => mkt_sb('actif-corpo',   'Société', $soc)],
        'nmt'      => ['url' => $_SRC2, 'post' => mkt_sb('nmt-corpo',     'Société', $soc)],
        'trim'     => ['url' => $_SRC2, 'post' => mkt_sb('trim-corpo',    'Société', $soc)],
        'sem'      => ['url' => $_SRC2, 'post' => mkt_sb('sem-corpo',     'Société', $soc)],
        'coursref' => ['url' => $_SRC2, 'post' => mkt_sb('coursref-corpo','Société', $soc)],
        'beta'     => ['url' => $_SRC2, 'post' => mkt_sb('beta',          'Société', $soc)],
        'desc'     => ['url' => $_SRC2, 'post' => mkt_sb('descriptions',  'symbol',  $symbol, true, 'description')],
        'holders'  => ['url' => $_SRC2, 'post' => mkt_sb('actionnariat',  'Ticker',  $symbol, false, 'Shareholder,Percentage')],
    ]);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function mkt_data(array $r, string $k): ?array { $v = $r[$k] ?? null; return is_array($v) ? ($v['data'] ?? null) : null; }
function mkt_latest(array $r, string $k): ?float {
    $d = mkt_data($r, $k); if (!$d) return null;
    foreach (['2024','2023','2022','2021'] as $y) { if (isset($d[$y]) && is_numeric($d[$y])) return (float)$d[$y]; }
    return null;
}
function mkt_series(array $r, string $k): array {
    $d = mkt_data($r, $k); if (!$d) return [];
    $out = [];
    foreach ($d as $ky => $v) { if (is_numeric($v) && preg_match('/^\d{4}p?$/', $ky)) $out[$ky] = (float)$v; }
    ksort($out); return $out;
}
function mkt_cagr(array $r, string $k, int $yr = 5): ?float {
    $d = mkt_data($r, $k); if (!$d) return null;
    $ly = null; $lv = null;
    for ($y = 2024; $y >= 2021; $y--) { if (isset($d[(string)$y]) && is_numeric($d[(string)$y]) && $d[(string)$y] > 0) { $ly=$y; $lv=(float)$d[(string)$y]; break; } }
    if (!$ly) return null;
    $py = (string)($ly - $yr);
    if (!isset($d[$py]) || !is_numeric($d[$py]) || $d[$py] <= 0) return null;
    return round((pow($lv / (float)$d[$py], 1/$yr) - 1) * 100, 2);
}

// ── Compute ───────────────────────────────────────────────────────────────────
$rnpg=$_ = mkt_latest($s2,'rnpg'); $fp=mkt_latest($s2,'fp'); $nmt=mkt_latest($s2,'nmt');
$ca=mkt_latest($s2,'ca'); $ebe=mkt_latest($s2,'ebe'); $ebit=mkt_latest($s2,'ebit');
$dn=mkt_latest($s2,'dn'); $tn=mkt_latest($s2,'tn'); $dpa_v=mkt_latest($s2,'dpa');
$fcf_v=mkt_latest($s2,'fcf'); $actif=mkt_latest($s2,'actif');

$bpa = null;
foreach (['2024','2023','2022'] as $y) { $v=$fin['beneficeParAction'][$y]??null; if($v!==null&&is_numeric($v)){$bpa=(float)$v;break;} }
if ($bpa===null&&$rnpg!==null&&$nmt!==null&&$nmt>0) $bpa = round($rnpg*1_000_000/$nmt, 2);
if ($dpa_v===null) { foreach(['2024','2023','2022'] as $y){$v=$fin['dividendeParAction'][$y]??null;if($v!==null&&is_numeric($v)){$dpa_v=(float)$v;break;}} }

$roe  = ($rnpg!==null&&$fp!==null&&$fp!=0) ? round($rnpg/$fp*100,2) : null;
$tc5  = mkt_cagr($s2,'ca',5);
$cp   = $fp!==null ? $fp*1_000_000 : null;
$pm   = ($rnpg!==null&&$ca!==null&&$ca!=0) ? round($rnpg/$ca*100,2) : null;

$beta_d  = mkt_data($s2,'beta');
$beta_3y = $beta_d&&isset($beta_d['Béta 3 ans']) ? (float)$beta_d['Béta 3 ans'] : null;
$beta_5y = $beta_d&&isset($beta_d['Béta 5 ans']) ? (float)$beta_d['Béta 5 ans'] : null;

$desc_d      = mkt_data($s2,'desc');
$description = $desc_d ? mb_substr(trim($desc_d['description']??''),0,3800) : null;

$holders_d    = mkt_data($s2,'holders');
$shareholders = null; $holders_json = null;
if (is_array($holders_d)) {
    $shareholders = array_values(array_filter(
        array_map(fn($h)=>['name'=>$h['Shareholder']??'','pct'=>round((float)($h['Percentage']??0)*100,2)],$holders_d),
        fn($h)=>$h['pct']>0
    ));
    $holders_json = json_encode($shareholders,JSON_UNESCAPED_UNICODE);
}

echo json_encode([
    'symbol'      => $symbol,
    'ext_name'    => $ext_name,
    'sector'      => $sector,
    'stock'       => $stock,
    'description' => $description,
    'shareholders'=> $shareholders,
    'computed'    => [
        'bpa'=>$bpa,'dpa'=>$dpa_v,'tc5'=>$tc5,'roe'=>$roe,'na'=>$nmt,'cp'=>$cp,
        'beta_3y'=>$beta_3y,'beta_5y'=>$beta_5y,'revenue'=>$ca,'ebitda'=>$ebe,
        'ebit'=>$ebit,'net_profit'=>$rnpg,'fcf'=>$fcf_v,'net_debt'=>$dn,
        'net_cash'=>$tn,'total_assets'=>$actif,'profit_margin'=>$pm,
        'rev_growth_5y'=>mkt_cagr($s2,'ca',5),'rnpg_growth_5y'=>mkt_cagr($s2,'rnpg',5),
        'shareholders'=>$holders_json,
    ],
    'charts' => [
        'ca'=>mkt_series($s2,'ca'),'rnpg'=>mkt_series($s2,'rnpg'),'ebe'=>mkt_series($s2,'ebe'),
        'ebit'=>mkt_series($s2,'ebit'),'fcf'=>mkt_series($s2,'fcf'),'fp'=>mkt_series($s2,'fp'),
        'dn'=>mkt_series($s2,'dn'),'dpa'=>mkt_series($s2,'dpa'),'coursref'=>mkt_series($s2,'coursref'),
    ],
    'trim' => mkt_data($s2,'trim'),
    'sem'  => mkt_data($s2,'sem'),
], JSON_UNESCAPED_UNICODE|JSON_PARTIAL_OUTPUT_ON_ERROR);
