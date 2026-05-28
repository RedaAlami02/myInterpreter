<?php
/**
 * Bulk sync all companies from idbourse.com.
 * Admin-only. Processes each company, updates Appwrite with enrichment data.
 * Access: /handlers/sync_idb.php
 */
session_start();
require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../core/Appwrite.php';
require_once __DIR__ . '/../core/auth.php';
requireAdmin();

set_time_limit(600); // 10 min — idbourse calls take time
ob_implicit_flush(true);
ob_end_flush();

$dryRun  = isset($_GET['dry']);
$only    = isset($_GET['symbol']) ? strtoupper(trim($_GET['symbol'])) : null;
?>
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Sync idbourse</title>
  <link href="../assets/css/global.css" rel="stylesheet">
  <style>
    body { padding: 32px; font-family: var(--font-body); font-size: 14px; }
    .row { display: flex; gap: 12px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); }
    .sym { font-family: var(--font-mono); font-size: 12px; color: var(--accent); width: 50px; }
    .name { width: 240px; color: var(--text-dim); }
    .status { flex: 1; }
    .ok  { color: var(--pos); }
    .skip{ color: var(--text-mute); }
    .err { color: var(--neg); }
    .warn{ color: var(--warn); }
    h2 { font-family: var(--font-display); margin-bottom: 24px; }
    .summary { margin-top: 24px; padding: 16px; background: var(--surface); border-radius: var(--radius); }
  </style>
</head>
<body>
<h2>🔄 Sync idbourse <?= $dryRun ? '<span style="color:var(--warn)">(DRY RUN)</span>' : '' ?></h2>
<p style="color:var(--text-dim);margin-bottom:24px">
  Mise à jour de toutes les sociétés depuis idbourse.com.
  <?= $dryRun ? 'Mode simulation — aucune écriture.' : 'Écriture activée.' ?>
</p>

<?php
flush();

// ── Build name→symbol map from format collection ──────────────────────────────
$fmt_docs = aw_list_docs('format', [q_limit(500)]);
$name_to_symbol = [];
foreach ($fmt_docs as $d) {
    if (!empty($d['name']) && !empty($d['symbol']))
        $name_to_symbol[strtolower(trim($d['name']))] = $d['symbol'];
}

// ── Get all companies ─────────────────────────────────────────────────────────
$companies = aw_list_docs('company', [q_order_asc('name'), q_limit(500)]);

$total = 0; $updated = 0; $skipped = 0; $errors = 0;

foreach ($companies as $co) {
    $co_name = trim($co['name'] ?? '');
    if (!$co_name) continue;
    if ($only && !str_contains(strtoupper($co_name), $only) && ($co['idb_name'] ?? '') !== $only) continue;

    $total++;

    // Find symbol
    $symbol = $co['idb_name'] ? null : ($name_to_symbol[strtolower($co_name)] ?? null);
    if (!$symbol) {
        // Try partial match
        foreach ($name_to_symbol as $fmt_name => $fmt_sym) {
            if (str_contains($fmt_name, strtolower(substr($co_name, 0, 8))) ||
                str_contains(strtolower($co_name), substr($fmt_name, 0, 8))) {
                $symbol = $fmt_sym; break;
            }
        }
    }
    if (!$symbol) {
        echo "<div class='row'><span class='sym'>?</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status warn'>⚠ symbole introuvable</span></div>\n";
        flush(); $skipped++; continue;
    }

    // Call idbourse proxy inline (same logic, direct function call)
    $proxy_url = BASE_URL . '/handlers/idbourse_proxy.php?symbol=' . urlencode($symbol);
    $ch = curl_init($proxy_url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_COOKIE         => session_name() . '=' . session_id(),
    ]);
    $body = curl_exec($ch);
    $http  = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if (!$body || $http !== 200) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status err'>✗ proxy error (HTTP {$http})</span></div>\n";
        flush(); $errors++; continue;
    }

    $data = json_decode($body, true);
    if (!$data || !empty($data['error'])) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status err'>✗ " . htmlspecialchars($data['error'] ?? 'parse error') . "</span></div>\n";
        flush(); $errors++; continue;
    }

    $c = $data['computed'] ?? [];

    // Build update payload — only set non-null values
    $update = array_filter([
        'idb_name'      => $data['idb_name'] ?? null,
        'sector'        => $data['sector']   ?? null,
        'description'   => $data['description'] ?? null,
        'shareholders'  => $c['shareholders'] ?? null,
        'beta_3y'       => $c['beta_3y']     ?? null,
        'beta_5y'       => $c['beta_5y']     ?? null,
        'revenue'       => $c['revenue']     ?? null,
        'ebitda'        => $c['ebitda']      ?? null,
        'ebit'          => $c['ebit']        ?? null,
        'net_profit'    => $c['net_profit']  ?? null,
        'fcf'           => $c['fcf']         ?? null,
        'net_debt'      => $c['net_debt']    ?? null,
        'net_cash'      => $c['net_cash']    ?? null,
        'total_assets'  => $c['total_assets']?? null,
        'profit_margin' => $c['profit_margin']?? null,
        'rev_growth_5y' => $c['rev_growth_5y']?? null,
        'rnpg_growth_5y'=> $c['rnpg_growth_5y']?? null,
        // Fundamental fields — only update if current value is empty/null
        'bpa' => (!empty($c['bpa']) && empty($co['bpa']))  ? $c['bpa']  : null,
        'dpa' => (!empty($c['dpa']) && empty($co['dpa']))  ? $c['dpa']  : null,
        'tc5' => (!empty($c['tc5']) && empty($co['tc5']))  ? $c['tc5']  : null,
        'roe' => (!empty($c['roe']) && empty($co['roe']))  ? $c['roe']  : null,
        'na'  => (!empty($c['na'])  && empty($co['na']))   ? $c['na']   : null,
        'cp'  => (!empty($c['cp'])  && empty($co['cp']))   ? $c['cp']   : null,
    ], fn($v) => $v !== null && $v !== '' && $v !== false);

    $field_count = count($update);
    $summary_parts = [];
    if (!empty($c['bpa']))    $summary_parts[] = "BPA=" . number_format((float)$c['bpa'], 2);
    if (!empty($c['revenue'])) $summary_parts[] = "CA=" . $c['revenue'] . "M";
    if (!empty($c['beta_3y'])) $summary_parts[] = "β3=" . $c['beta_3y'];
    if (!empty($data['description'])) $summary_parts[] = "desc✓";
    if (!empty($data['shareholders'])) $summary_parts[] = "actionnaires✓";

    if ($field_count === 0) {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status skip'>— aucune donnée disponible</span></div>\n";
        flush(); $skipped++; continue;
    }

    if (!$dryRun) {
        try {
            aw_update_doc('company', $co['$id'], $update);
            $updated++;
            echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status ok'>✓ {$field_count} champs — " . implode(' · ', $summary_parts) . "</span></div>\n";
        } catch (Throwable $e) {
            echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status err'>✗ " . htmlspecialchars($e->getMessage()) . "</span></div>\n";
            $errors++;
        }
    } else {
        echo "<div class='row'><span class='sym'>{$symbol}</span><span class='name'>" . htmlspecialchars($co_name) . "</span><span class='status ok'>[DRY] {$field_count} champs — " . implode(' · ', $summary_parts) . "</span></div>\n";
        $updated++;
    }
    flush();
    usleep(200_000); // 200ms between companies to avoid hammering idbourse
}
?>

<div class="summary">
  <strong>Résultat :</strong>
  <?= $total ?> sociétés traitées —
  <span class="ok"><?= $updated ?> mises à jour</span> ·
  <span class="skip"><?= $skipped ?> ignorées</span> ·
  <span class="err"><?= $errors ?> erreurs</span>
</div>
<p style="margin-top:16px;color:var(--text-dim)">
  <a href="../Update.php" style="color:var(--accent)">← Retour à Update.php</a>
  &nbsp;·&nbsp;
  <a href="sync_idb.php?dry" style="color:var(--text-dim)">Dry run</a>
</p>
</body>
</html>
