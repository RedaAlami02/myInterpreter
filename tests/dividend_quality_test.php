<?php
require_once __DIR__ . '/../core/dividends.php';

$fixtures = json_decode(file_get_contents(__DIR__ . '/fixtures/dividend_periods.json'), true, 512, JSON_THROW_ON_ERROR);
foreach ($fixtures as $fixture) {
    $source = $fixture['row'];
    $before = $source;
    $issue = div_verification_issue($source);
    if ($issue !== $fixture['issue']) throw new RuntimeException($fixture['name']);
    $projected = div_review_row($source);
    if ($source !== $before) throw new RuntimeException('Source changed');
    if ($issue !== null) {
        if ($projected['amount'] !== null || div_confirmed($source)
            || div_yield($source, 100) !== null || div_date($source) !== null
            || div_date_end($source) !== null || div_history([$source], 2026)) {
            throw new RuntimeException('Unverified row leaked into financial output');
        }
        if (div_verification_issue($projected) !== $issue) {
            throw new RuntimeException('Projection lost the review reason');
        }
    } elseif ($projected !== $source) {
        throw new RuntimeException('Valid row changed');
    }
}
$wrong = $fixtures[1]['row'];
[$next, $when] = div_next([$wrong], '2027-01-01');
if ($when !== 'unknown' || $next['amount'] !== null || div_predict([$wrong], 2028) !== null) {
    throw new RuntimeException('Invalid period treated as payment or prediction evidence');
}
echo 'Dividend quality checks passed for ' . count($fixtures) . " shared cases.\n";
