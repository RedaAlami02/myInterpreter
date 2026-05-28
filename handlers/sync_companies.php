<?php
/**
 * Bulk enrichment sync — updates all company records with market data.
 * Admin-only. Streams progress live. Run once after initial setup.
 * ?dry     = simulation mode (no writes)
 * ?symbol= = process only this ticker
 */
session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
requireAdmin();

set_time_limit(600);
ob_implicit_flush(true);
ob_end_flush();

$dryRun = isset($_GET['dry']);
$only   = isset($_GET['symbol']) ? strtoupper(trim($_GET['symbol'])) : null;
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Enrichissement des sociétés</title>
  <link href="../assets/css/global.css" rel="stylesheet">
  <style>
    body { padding: 32px; font-family: var(--font-body); font-size: 14px; }
    .row { display:flex; gap:12px; align-items:center; padding:6px 0; border-bottom:1px solid var(--border); }
    .sym  { font-family:var(--font-mono); font-size:12px; color:var(--accent); width:50px; }
    .name { width:240px; color:var(--text-dim); }
    .ok   { color:var(--pos); }
    .skip { color:var(--text-mute); }
    .err  { color:var(--neg); }
    h2    { font-family:var(--font-display); margin-bottom:24px; }
    .summary { margin-top:24px; padding:16px; background:var(--surface); border-radius:var(--radius); }
  </style>
</head>
<body>
<h2>Enrichissement des fiches sociétés <?= $dryRun ? '<span style="color:var(--warn)">(simulation)</span>' : '' ?></h2>
<p style="color:var(--text-dim);margin-bottom:24px">
  Mise à jour des données fondamentales et biographiques pour toutes les sociétés.
  <?= $dryRun ? 'Mode simulation — aucune écriture.' : 'Écriture activée.' ?>
</p>
<?php flush();

// Build name→symbol map
$fmt_docs       = aw_list_docs('format', [q_limit(500)]);
$name_to_symbol = [];
foreach ($fmt_docs as $d) {
    if (!empty($d['name']) && !empty($d['symbol']))
        $name_to_symbol[strtolower(trim($d['name']))] = $d['symbol'];
}

$companies = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);
$total = $updated = $skipped = $errors = 0;

foreach ($companies as $co) {
    $co_name = trim($co['name'] ?? '');
    if (!$co_name) continue;
    if ($only && stripos($co_name, $only) === false && stripos($co['ext_name'] ?? '', $only) === false) continue;

    $total++;

    // Find symbol from format collection
    $symbol = $name_to_symbol[strtolower($co_name)] ?? null;
    if (!$symbol) {
        foreach ($name_to_symbol as $fn => $fs) {
            if (str_contains($fn, strtolower(substr($co_name,0,8))) || str_contains(strtolower($co_name), substr($fn,0,8)))
                { $symbol = $fs; break; }
        }
    }
    if (!$symbol) {
        echo "<div class='row'><span class='sym'>?</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='skip'>⚠ symbole introuvable</span></div>\n";
        flush(); $skipped++; continue;
    }

    // Call market proxy
    $ch = curl_init(BASE_URL . '/handlers/market_proxy.php?symbol=' . urlencode($symbol));
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER=>true, CURLOPT_TIMEOUT=>30,
                            CURLOPT_COOKIE => session_name().'='.session_id()]);
    $body = curl_exec($ch);
    $http = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if (!$body || $http !== 200) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='err'>✗ proxy error {$http}</span></div>\n";
        flush(); $errors++; continue;
    }

    $data = json_decode($body, true);
    if (!$data || !empty($data['error'])) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='err'>✗ ".htmlspecialchars($data['error']??'parse error')."</span></div>\n";
        flush(); $errors++; continue;
    }

    $c = $data['computed'] ?? [];
    $update = array_filter([
        'ext_name'       => $data['ext_name']       ?? null,
        'sector'         => $data['sector']          ?? null,
        'description'    => $data['description']     ?? null,
        'shareholders'   => $c['shareholders']       ?? null,
        'beta_3y'        => $c['beta_3y']            ?? null,
        'beta_5y'        => $c['beta_5y']            ?? null,
        'revenue'        => $c['revenue']            ?? null,
        'ebitda'         => $c['ebitda']             ?? null,
        'ebit'           => $c['ebit']               ?? null,
        'net_profit'     => $c['net_profit']         ?? null,
        'fcf'            => $c['fcf']                ?? null,
        'net_debt'       => $c['net_debt']           ?? null,
        'net_cash'       => $c['net_cash']           ?? null,
        'total_assets'   => $c['total_assets']       ?? null,
        'profit_margin'  => $c['profit_margin']      ?? null,
        'rev_growth_5y'  => $c['rev_growth_5y']      ?? null,
        'rnpg_growth_5y' => $c['rnpg_growth_5y']     ?? null,
        // Fundamentals: only fill if empty in Appwrite
        'bpa' => (!empty($c['bpa']) && empty($co['bpa'])) ? $c['bpa'] : null,
        'dpa' => (!empty($c['dpa']) && empty($co['dpa'])) ? $c['dpa'] : null,
        'tc5' => (!empty($c['tc5']) && empty($co['tc5'])) ? $c['tc5'] : null,
        'roe' => (!empty($c['roe']) && empty($co['roe'])) ? $c['roe'] : null,
        'na'  => (!empty($c['na'])  && empty($co['na']))  ? $c['na']  : null,
        'cp'  => (!empty($c['cp'])  && empty($co['cp']))  ? $c['cp']  : null,
    ], fn($v) => $v !== null && $v !== '' && $v !== false);

    if (empty($update)) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='skip'>— aucune donnée</span></div>\n";
        flush(); $skipped++; continue;
    }

    $parts = [];
    if (!empty($c['bpa']))        $parts[] = 'BPA='.number_format((float)$c['bpa'],2);
    if (!empty($c['revenue']))    $parts[] = 'CA='.$c['revenue'].'M';
    if (!empty($c['beta_3y']))    $parts[] = 'β3='.$c['beta_3y'];
    if (!empty($data['description'])) $parts[] = 'desc✓';
    if (!empty($data['shareholders'])) $parts[] = 'actionnaires('.count($data['shareholders']).')';

    if (!$dryRun) {
        try {
            aw_update_doc('company', $co['$id'], $update);
            echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='ok'>✓ ".count($update)." champs — ".implode(' · ',$parts)."</span></div>\n";
            $updated++;
        } catch (Throwable $e) {
            echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='err'>✗ ".htmlspecialchars($e->getMessage())."</span></div>\n";
            $errors++;
        }
    } else {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>".htmlspecialchars($co_name)."</span><span class='ok'>[sim] ".count($update)." champs — ".implode(' · ',$parts)."</span></div>\n";
        $updated++;
    }
    flush();
    usleep(200_000);
}
?>
<div class="summary">
  <strong>Résultat :</strong> <?=$total?> traitées —
  <span class="ok"><?=$updated?> mises à jour</span> ·
  <span class="skip"><?=$skipped?> ignorées</span> ·
  <span class="err"><?=$errors?> erreurs</span>
</div>
<p style="margin-top:16px;color:var(--text-dim)">
  <a href="../Update.php" style="color:var(--accent)">← Update.php</a> &nbsp;·&nbsp;
  <a href="sync_companies.php?dry" style="color:var(--text-dim)">Simulation</a>
</p>
</body>
</html>
