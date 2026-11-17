<?php
/** CLI-only live probe; configuration arrives over stdin, never argv or output. */
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require_once __DIR__ . '/../core/SupabaseMarket.php';
$phase = 'configuration';
$caseIndex = -1;
try {
    $input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $reader = new SupabaseMarketReader($input['project_url'], $input['publishable_key'], null, $input['access_token'] ?? null);
    $contract = json_decode(file_get_contents(__DIR__ . '/../migrations/supabase/market_contract.json'), true, 512, JSON_THROW_ON_ERROR);
    $results = [];
    foreach ($input['cases'] as $case) {
        $caseIndex++;
        $phase = 'list_request';
        $rows = $reader->listDocuments($case['collection'], $case['queries']);
        $phase = 'row_count';
        if (count($rows) !== count($case['expected_rows'])) throw new RuntimeException('Row count mismatch.');
        foreach ($rows as $index => $row) {
            $phase = 'field_set';
            $expected = $case['expected_rows'][$index];
            if (array_diff_key($row, $expected) || array_diff_key($expected, $row)) {
                throw new RuntimeException('Field mismatch.');
            }
            foreach ($expected as $field => $value) {
                $phase = 'row_values';
                if (($contract['tables'][$case['collection']]['fields'][$field] ?? '') === 'timestamptz'
                    && $value !== null && $row[$field] !== null) {
                    if ((new DateTimeImmutable($row[$field]))->format('U.u') !== (new DateTimeImmutable($value))->format('U.u')) {
                        throw new RuntimeException('Timestamp mismatch.');
                    }
                } elseif (($value === null) !== ($row[$field] === null)
                          || is_bool($value) !== is_bool($row[$field]) || $row[$field] != $value) {
                    throw new RuntimeException('Value mismatch.');
                }
            }
        }
        $phase = 'exact_count';
        if ($reader->countDocuments($case['collection'], $case['queries']) !== $case['expected_count']) {
            throw new RuntimeException('Exact count mismatch.');
        }
        $results[] = ['case' => $case['name'], 'records_checked' => count($rows), 'matches_sql' => true];
    }
    echo json_encode(['ok' => true, 'php_public_api_checks' => $results], JSON_THROW_ON_ERROR), "\n";
} catch (Throwable $error) {
    echo json_encode(['ok' => false, 'error_category' => get_class($error),
                      'phase' => $phase, 'case_index' => $caseIndex]), "\n";
    exit(1);
}
