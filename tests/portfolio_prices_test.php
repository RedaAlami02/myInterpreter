<?php
require __DIR__ . '/../core/portfolio_prices.php';
$fixture = json_decode(file_get_contents(__DIR__ . '/fixtures/portfolio/recorded_prices.json'), true, 512, JSON_THROW_ON_ERROR);
foreach ($fixture['cases'] as $case) {
    $prices = portfolio_recorded_prices($case['prices'], new DateTimeImmutable($fixture['now']));
    $result = portfolio_reference_totals($case['holdings'], $prices, $case['holdings_complete'] ?? true);
    foreach ($case['expected'] as $key => $value) {
        if ($result[$key] != $value || ($result[$key] === null) !== ($value === null)) {
            throw new RuntimeException($case['name'] . ': ' . $key);
        }
    }
    if ($result['portfolio_valuation_eligible'] !== false) throw new RuntimeException('Reference promoted');
    foreach ($prices as $price) if ($price['price'] !== null && $price['status'] !== 'RECORDED_REFERENCE') throw new RuntimeException('Invalid authority');
}
echo count($fixture['cases']) . " portfolio reference/coverage cases passed.\n";
