<?php
require_once __DIR__ . '/../core/sector_allocation.php';

$allocation = market_sector_allocation([
    ['c_name' => 'COSUMAR', 'quantity' => 2, 'current_value' => 100],
    ['c_name' => 'COSUMAR', 'quantity' => 3, 'current_value' => 150], // another lot is still one company
    ['c_name' => 'MUTANDIS', 'quantity' => 1, 'current_value' => 50],
    ['c_name' => 'AFRIC INDUSTRIES', 'quantity' => 10, 'current_value' => 1000],
    ['c_name' => 'IAM', 'quantity' => 1, 'current_value' => 200],
    ['c_name' => 'MED PAPER', 'quantity' => 1, 'current_value' => 25], // absent from this listing snapshot
    ['c_name' => 'PROMOPHARM', 'quantity' => 0, 'current_value' => 0], // no current holding
]);

$byCode = array_column($allocation['rows'], null, 'code');
assert(count(MARKET_SECTORS) === 24);
assert(array_sum(array_column($allocation['rows'], 'market')) === 78);
assert($byCode['AGR']['held'] === 2 && $byCode['AGR']['market'] === 6);
assert($byCode['AGR']['value'] === 300.0);
assert($byCode['BMC']['held'] === 1 && $byCode['BMC']['market'] === 9);
assert($byCode['BMC']['value'] === 1000.0);
assert($byCode['TCO']['held'] === 1 && $byCode['TCO']['market'] === 1);
assert($byCode['PHA']['held'] === 0);
assert($allocation['rows'][0]['code'] === 'AGR');
assert($allocation['unclassified'] === ['MED PAPER']);
assert($allocation['unclassified_value'] === 25.0);
assert($allocation['held_companies']['AGR'][0]['name'] === 'COSUMAR');
assert($allocation['held_companies']['AGR'][0]['value'] === 250.0);
assert(count($allocation['held_companies']['AGR']) === 2);

$directory = market_sector_directory(['COSUMAR', 'MUTANDIS', 'IAM', 'MED PAPER']);
assert($directory['AGR'] === ['COSUMAR', 'MUTANDIS']);
assert($directory['TCO'] === ['IAM']);
assert($directory['OTHER'] === ['MED PAPER']);
assert(market_sector_for_company('AFRIC INDUSTRIES') === 'BMC');

echo "sector allocation OK\n";
