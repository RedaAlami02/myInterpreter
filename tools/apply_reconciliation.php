<?php
// CLI-only share-count applier. Reads a reconciliation report, writes only `na`.
// Dry-run unless --apply is passed. Never deploy this tool.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/../config/config.php';
require __DIR__ . '/../core/Appwrite.php';
require __DIR__ . '/../core/SupabaseApp.php';
require __DIR__ . '/../core/SupabaseMarket.php';
require __DIR__ . '/../core/SupabaseAdmin.php';

function fail(string $message): never
{
    fwrite(STDERR, $message . PHP_EOL);
    exit(1);
}

function argument(array $argv, string $name): ?string
{
    $index = array_search('--' . $name, $argv, true);
    return $index === false ? null : ($argv[$index + 1] ?? null);
}

try {
    $reportPath = argument($argv, 'report');
    $apply = in_array('--apply', $argv, true);
    $all = in_array('--all-shares', $argv, true);
    $symbols = array_values(array_filter(array_map('trim', explode(',', argument($argv, 'symbols') ?? ''))));
    if (!$reportPath || !is_readable($reportPath)) fail('Pass --report /path/to/reconciliation.json');
    if (!$all && !$symbols) fail('Pass --symbols SYM[,SYM] or --all-shares');

    $report = json_decode(file_get_contents($reportPath), true, 512, JSON_THROW_ON_ERROR);
    if (($report['contract'] ?? null) !== 'exchange-reconciliation/v1'
        || !is_array($report['companies'] ?? null)) {
        fail('Not an exchange-reconciliation/v1 report');
    }
    $selected = [];
    foreach ($report['companies'] as $company) {
        $symbol = $company['symbol'] ?? null;
        if (!is_string($symbol)) continue;
        if (!$all && !in_array($symbol, $symbols, true)) continue;
        $shares = $company['current_shares'] ?? [];
        $proposed = $company['proposed_fields']['na'] ?? null;
        if (($company['status'] ?? null) === 'QUARANTINE'
            || ($shares['status'] ?? null) !== 'VERIFIED'
            || !is_numeric($proposed) || $proposed <= 0) {
            continue;
        }
        $selected[$symbol] = [
            'name' => $company['saved']['name'] ?? $company['company'] ?? null,
            'exchange_name' => $company['company'] ?? null,
            'na' => $proposed,
            'status' => $company['status'] ?? null,
            'warnings' => $company['warnings'] ?? [],
        ];
    }
    if (!$selected) fail('No verified share proposal matched the selection');

    $email = getenv('MI_ADMIN_EMAIL');
    $password = getenv('MI_ADMIN_PASSWORD');
    if (!$apply) {
        echo json_encode([
            'status' => 'DRY_RUN',
            'changes' => $selected,
            'production_writes' => 0,
        ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL;
        exit(0);
    }
    if (!is_string($email) || $email === '' || !is_string($password) || $password === '') {
        fail('Set MI_ADMIN_EMAIL and MI_ADMIN_PASSWORD');
    }
    $tokens = sb_app()->signIn($email, $password);
    $token = $tokens['access_token'] ?? null;
    if (!is_string($token) || $token === '') fail('Administrator sign-in did not return a session');

    $private = dirname(__DIR__) . '/private/exchange-reconciliation-20261116';
    $backupDir = $private . '/backups';
    if (!is_dir($backupDir) && !mkdir($backupDir, 0700, true) && !is_dir($backupDir)) {
        fail('Cannot create backup directory');
    }
    $reader = new SupabaseMarketReader(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY, null, $token);
    $admin = new SupabaseAdminClient(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY);
    $audit = fopen($private . '/applied.jsonl', 'ab');
    if ($audit === false) fail('Cannot open audit log');
    $results = [];
    try {
        foreach ($selected as $symbol => $change) {
            $name = $change['name'];
            if (!is_string($name) || $name === '') {
                $results[$symbol] = ['status' => 'SKIPPED', 'reason' => 'MISSING_NAME'];
                continue;
            }
            try {
                $rows = $reader->listDocuments('company', [q_equal('name', $name), q_limit(1)]);
                $current = $rows[0] ?? null;
                if (!is_array($current)) {
                    $results[$symbol] = ['status' => 'MISSING'];
                    continue;
                }
                if (abs((float)($current['na'] ?? 0) - (float)$change['na']) < 1e-9) {
                    $results[$symbol] = ['status' => 'UNCHANGED', 'na' => $change['na']];
                    continue;
                }
                $backup = $backupDir . '/' . $symbol . '-' . gmdate('YmdTHisZ') . '.json';
                if (file_put_contents($backup, json_encode($current, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX) === false) {
                    throw new RuntimeException('Backup failed');
                }
                chmod($backup, 0600);
                $receipt = $admin->updateCompany($token, $name, ['na' => $change['na']]);
                $saved = $reader->listDocuments('company', [q_equal('name', $name), q_limit(1)])[0] ?? [];
                if (abs((float)($saved['na'] ?? 0) - (float)$change['na']) >= 1e-9) {
                    throw new RuntimeException('Read-back mismatch');
                }
                $event = [
                    'at' => gmdate('c'), 'symbol' => $symbol, 'name' => $name,
                    'field' => 'na', 'old' => $current['na'] ?? null, 'new' => $change['na'],
                    'report_status' => $change['status'], 'receipt' => $receipt,
                    'backup' => basename($backup),
                ];
                fwrite($audit, json_encode($event, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . PHP_EOL);
                fflush($audit);
                $results[$symbol] = ['status' => 'UPDATED', 'old' => $current['na'] ?? null, 'new' => $change['na']];
            } catch (Throwable $error) {
                $results[$symbol] = ['status' => 'FAILED', 'reason' => 'APPLY_FAILED'];
            }
        }
    } finally {
        fclose($audit);
        try { sb_app()->signOut($token); } catch (Throwable $ignored) {}
    }
    echo json_encode(['status' => 'COMPLETE', 'results' => $results], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . PHP_EOL;
    exit(0);
} catch (Throwable $error) {
    fwrite(STDERR, $error->getMessage() . PHP_EOL);
    exit(1);
}
