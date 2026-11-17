<?php
/** Read-only saved recovery audit; source values and original IDs stay local. */
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require_once __DIR__ . '/../core/dividends.php';

try {
    $root = dirname(__DIR__);
    $rows = json_decode(file_get_contents($root . '/backup_live_recovery_20261022/baseline/dividends.json'), true, 512, JSON_THROW_ON_ERROR);
    $report = ['read_only' => true, 'raw_rows_changed' => false, 'checked_rows' => count($rows),
               'issues' => [], 'by_year' => [], 'records_requiring_review' => []];
    foreach ($rows as $row) {
        $issue = div_verification_issue($row);
        $year = (string)$row['year'];
        $report['by_year'][$year] ??= ['rows' => 0, 'needs_review' => 0, 'effective_confirmed' => 0];
        $report['by_year'][$year]['rows']++;
        if ($issue !== null) {
            $report['by_year'][$year]['needs_review']++;
            $report['issues'][$issue] = ($report['issues'][$issue] ?? 0) + 1;
            $report['records_requiring_review'][] = ['original_id' => $row['$id'], 'c_name' => $row['c_name'],
                'year' => $row['year'], 'issue' => $issue, 'original' => $row];
        }
        if (div_confirmed($row)) $report['by_year'][$year]['effective_confirmed']++;
    }
    $report['generated_at_utc'] = gmdate('c');
    ksort($report['by_year']);
    file_put_contents($root . '/backup_live_nonpersonal_20261024/dividend_quality.json', json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . "\n");
    unset($report['records_requiring_review']);
    echo json_encode($report, JSON_THROW_ON_ERROR) . "\n";
} catch (Throwable $error) {
    echo json_encode(['ok' => false, 'error_category' => get_class($error)]) . "\n";
    exit(1);
}
