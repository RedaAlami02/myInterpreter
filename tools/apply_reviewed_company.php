<?php
// CLI-only, explicit audited-company update. Never deploy this tool.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/../config/config.php';
require __DIR__ . '/../core/Appwrite.php';
require __DIR__ . '/../core/company_disclosures.php';
$symbol = $argv[1] ?? '';
$review = reviewed_company_disclosure($symbol);
if (!$review) throw new RuntimeException('No reviewed disclosure for this symbol');
$docs = aw_list_docs('company', [q_equal('name', $review['name']), q_limit(2)]);
if (count($docs) !== 1) throw new RuntimeException('Expected exactly one company');
$current = $docs[0];
if (($current['fiscal_year'] ?? 0) > $review['fields']['fiscal_year']) {
    throw new RuntimeException('Refusing to overwrite newer accounts');
}
$changes = [];
foreach ($review['fields'] as $key => $value) {
    if (($current[$key] ?? null) !== $value) $changes[$key] = $value;
}
echo $symbol . ': ' . count($changes) . ' reviewed fields: ' . implode(', ', array_keys($changes)) . PHP_EOL;
if (!in_array('--apply', $argv, true) || !$changes) exit;
$backup = tempnam(sys_get_temp_dir(), 'myinterpreter-company-');
if (!$backup || file_put_contents($backup, json_encode($current, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)) === false) {
    throw new RuntimeException('Backup failed; no changes made');
}
chmod($backup, 0600);
echo 'Rollback record: ' . $backup . PHP_EOL;
aw_update_doc('company', $current['$id'], $changes);
$saved = aw_list_docs('company', [q_equal('name', $review['name']), q_limit(1)])[0] ?? [];
foreach ($changes as $key => $value) {
    if (($saved[$key] ?? null) != $value) throw new RuntimeException('Read-back mismatch: ' . $key);
}
echo "PASS company update read-back; prices and historical records untouched\n";
