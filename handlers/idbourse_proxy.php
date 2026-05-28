<?php
/**
 * idbourse.com API proxy — server-side to avoid CORS.
 * GET ?symbol=M2M  →  JSON with all enrichment data + computed fundamentals.
 * Parallel curl (curl_multi) for performance.
 */
session_start();
require_once __DIR__ . '/../config/config.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=3600'); // cache 1h — idbourse data is daily

$symbol = preg_replace('/[^A-Z0-9]/', '', strtoupper($_GET['symbol'] ?? ''));
if (!$symbol) { echo json_encode(['error' => 'symbol required']); exit; }

// ── Parallel curl ─────────────────────────────────────────────────────────────
function idb_batch(array $requests): array {
    $mh = curl_multi_init();
    $handles = [];
    foreach ($requests as $key => $spec) {
        $ch = curl_init($spec['url']);
        $hdr = ['Accept: */*', 'User-Agent: Mozilla/5.0 (compatible)',
                'Origin: https://www.idbourse.com', 'Referer: https://www.idbourse.com/'];
        $opts = [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 10,
                 CURLOPT_HTTPHEADER => array_merge($hdr, $spec['extra_headers'] ?? [])];
        if (!empty($spec['post'])) {
            $opts[CURLOPT_POST]       = true;
            $opts[CURLOPT_POSTFIELDS] = $spec['post'];
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

function sb(string $table, string $col, string $value, bool $single = true, ?string $select = null): string {
    $opts = ['filter' => ['column' => $col, 'value' => $value], 'single' => $single];
    if ($select) $opts['select'] = $select;
    return json_encode(['table' => $table, 'options' => $opts]);
}

$SB = 'https://www.idbourse.com/api/proxy/supabase';

// ── Step 1: stock info + financial summary + symbol list ─────────────────────
$s1 = idb_batch([
    'stock'     => ['url' => "https://www.idbourse.com/api/proxy/stock/{$symbol}"],
    'financial' => ['url' => "https://www.idbourse.com/api/proxy/financial/{$symbol}"],
    'symlinks'  => ['url' => "https://www.idbourse.com/api/proxy/symblinks"],
]);

$stock    = $s1['stock']    ?? null;
$fin      = $s1['financial']['financialData'] ?? [];
$symlinks = $s1['symlinks'] ?? [];

// Find idbourse name + sector for this symbol
$idb_name = null; $sector = null;
if (is_array($symlinks)) {
    foreach ($symlinks as $s) {
        if (($s['symbol'] ?? '') === $symbol) {
            $idb_name = $s['name'] ?? null;
            $sector   = $s['type'] ?? null;
            break;
        }
    }
}
if (!$idb_name && $stock) $idb_name = $stock['name'] ?? null;

// ── Step 2: all supabase tables in parallel ───────────────────────────────────
$s2 = [];
if ($idb_name) {
    $soc = $idb_name; // Société column value
    $s2 = idb_batch([
        'rnpg'     => ['url' => $SB, 'post' => sb('rnpg-corpo',    'Société', $soc)],
        'ca'       => ['url' => $SB, 'post' => sb('ca-corpo',      'Société', $soc)],
        'ebe'      => ['url' => $SB, 'post' => sb('ebe-corpo',     'Société', $soc)],
        'ebit'     => ['url' => $SB, 'post' => sb('ebit-corpo',    'Société', $soc)],
        'fp'       => ['url' => $SB, 'post' => sb('fp-corpo',      'Société', $soc)],
        'dn'       => ['url' => $SB, 'post' => sb('dn-corpo',      'Société', $soc)],
        'tn'       => ['url' => $SB, 'post' => sb('tn-corpo',      'Société', $soc)],
        'dpa'      => ['url' => $SB, 'post' => sb('dpa-corpo',     'Société', $soc)],
        'fcf'      => ['url' => $SB, 'post' => sb('fcf-corpo',     'Société', $soc)],
        'actif'    => ['url' => $SB, 'post' => sb('actif-corpo',   'Société', $soc)],
        'nmt'      => ['url' => $SB, 'post' => sb('nmt-corpo',     'Société', $soc)],
        'trim'     => ['url' => $SB, 'post' => sb('trim-corpo',    'Société', $soc)],
        'sem'      => ['url' => $SB, 'post' => sb('sem-corpo',     'Société', $soc)],
        'coursref' => ['url' => $SB, 'post' => sb('coursref-corpo','Société', $soc)],
        'beta'     => ['url' => $SB, 'post' => sb('beta',          'Société', $soc)],
        'desc'     => ['url' => $SB, 'post' => sb('descriptions',  'symbol',  $symbol, true, 'description')],
        'holders'  => ['url' => $SB, 'post' => sb('actionnariat',  'Ticker',  $symbol, false, 'Shareholder,Percentage')],
    ]);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function sb_data(array $r, string $key): ?array {
    $v = $r[$key] ?? null;
    return is_array($v) ? ($v['data'] ?? null) : null;
}

function latest_val(array $r, string $key): ?float {
    $d = sb_data($r, $key);
    if (!$d) return null;
    foreach (['2024','2023','2022','2021'] as $y) {
        if (isset($d[$y]) && is_numeric($d[$y])) return (float)$d[$y];
    }
    return null;
}

function yearly_series(array $r, string $key): array {
    $d = sb_data($r, $key);
    if (!$d) return [];
    $out = [];
    foreach ($d as $k => $v) {
        if (is_numeric($v) && (preg_match('/^\d{4}$/', $k) || preg_match('/^\d{4}p$/', $k)))
            $out[$k] = (float)$v;
    }
    ksort($out);
    return $out;
}

function cagr_calc(array $r, string $key, int $years = 5): ?float {
    $d = sb_data($r, $key);
    if (!$d) return null;
    $latest_y = null; $latest_v = null;
    for ($y = 2024; $y >= 2021; $y--) {
        if (isset($d[(string)$y]) && is_numeric($d[(string)$y]) && $d[(string)$y] > 0)
            { $latest_y = $y; $latest_v = (float)$d[(string)$y]; break; }
    }
    if (!$latest_y) return null;
    $past_y = (string)($latest_y - $years);
    if (!isset($d[$past_y]) || !is_numeric($d[$past_y]) || $d[$past_y] <= 0) return null;
    return round((pow($latest_v / (float)$d[$past_y], 1 / $years) - 1) * 100, 2);
}

// ── Extract values ────────────────────────────────────────────────────────────
$rnpg   = latest_val($s2, 'rnpg');
$fp     = latest_val($s2, 'fp');
$nmt    = latest_val($s2, 'nmt'); // share count
$ca     = latest_val($s2, 'ca');
$ebe    = latest_val($s2, 'ebe');
$ebit   = latest_val($s2, 'ebit');
$dn     = latest_val($s2, 'dn');
$tn     = latest_val($s2, 'tn');
$dpa_v  = latest_val($s2, 'dpa');
$fcf_v  = latest_val($s2, 'fcf');
$actif  = latest_val($s2, 'actif');

// BPA — idbourse financial endpoint first, then compute
$bpa = null;
foreach (['2024','2023','2022'] as $y) {
    $v = $fin['beneficeParAction'][$y] ?? null;
    if ($v !== null && is_numeric($v)) { $bpa = (float)$v; break; }
}
if ($bpa === null && $rnpg !== null && $nmt !== null && $nmt > 0)
    $bpa = round($rnpg * 1_000_000 / $nmt, 2);

// DPA — supabase first, then financial endpoint
if ($dpa_v === null) {
    foreach (['2024','2023','2022'] as $y) {
        $v = $fin['dividendeParAction'][$y] ?? null;
        if ($v !== null && is_numeric($v)) { $dpa_v = (float)$v; break; }
    }
}

// ROE, TC5, CP
$roe = ($rnpg !== null && $fp !== null && $fp != 0) ? round($rnpg / $fp * 100, 2) : null;
$tc5 = cagr_calc($s2, 'ca', 5);
$cp  = ($fp !== null) ? $fp * 1_000_000 : null;

$profit_margin  = ($rnpg !== null && $ca !== null && $ca != 0) ? round($rnpg / $ca * 100, 2) : null;
$rev_growth_5y  = cagr_calc($s2, 'ca',   5);
$rnpg_growth_5y = cagr_calc($s2, 'rnpg', 5);

$beta_d  = sb_data($s2, 'beta');
$beta_3y = $beta_d ? (isset($beta_d['Béta 3 ans']) ? (float)$beta_d['Béta 3 ans'] : null) : null;
$beta_5y = $beta_d ? (isset($beta_d['Béta 5 ans']) ? (float)$beta_d['Béta 5 ans'] : null) : null;

$desc_d      = sb_data($s2, 'desc');
$description = $desc_d ? mb_substr(trim($desc_d['description'] ?? ''), 0, 3800) : null;

$holders_d = sb_data($s2, 'holders');
$shareholders = null;
if (is_array($holders_d)) {
    $shareholders = array_values(array_filter(
        array_map(fn($h) => ['name' => $h['Shareholder'] ?? '', 'pct' => round((float)($h['Percentage'] ?? 0) * 100, 2)],
                  $holders_d),
        fn($h) => $h['pct'] > 0
    ));
}

echo json_encode([
    'symbol'   => $symbol,
    'idb_name' => $idb_name,
    'sector'   => $sector,
    'stock'    => $stock,
    'computed' => [
        'bpa'           => $bpa,
        'dpa'           => $dpa_v,
        'tc5'           => $tc5,
        'roe'           => $roe,
        'na'            => $nmt,
        'cp'            => $cp,
        'beta_3y'       => $beta_3y,
        'beta_5y'       => $beta_5y,
        'revenue'       => $ca,
        'ebitda'        => $ebe,
        'ebit'          => $ebit,
        'net_profit'    => $rnpg,
        'fcf'           => $fcf_v,
        'net_debt'      => $dn,
        'net_cash'      => $tn,
        'total_assets'  => $actif,
        'profit_margin' => $profit_margin,
        'rev_growth_5y' => $rev_growth_5y,
        'rnpg_growth_5y'=> $rnpg_growth_5y,
        'shareholders'  => $shareholders ? json_encode($shareholders, JSON_UNESCAPED_UNICODE) : null,
    ],
    'description'  => $description,
    'shareholders' => $shareholders,
    'charts' => [
        'ca'       => yearly_series($s2, 'ca'),
        'rnpg'     => yearly_series($s2, 'rnpg'),
        'ebe'      => yearly_series($s2, 'ebe'),
        'ebit'     => yearly_series($s2, 'ebit'),
        'fcf'      => yearly_series($s2, 'fcf'),
        'fp'       => yearly_series($s2, 'fp'),
        'dn'       => yearly_series($s2, 'dn'),
        'dpa'      => yearly_series($s2, 'dpa'),
        'coursref' => yearly_series($s2, 'coursref'),
    ],
    'trim' => sb_data($s2, 'trim'),
    'sem'  => sb_data($s2, 'sem'),
], JSON_UNESCAPED_UNICODE | JSON_PARTIAL_OUTPUT_ON_ERROR);
