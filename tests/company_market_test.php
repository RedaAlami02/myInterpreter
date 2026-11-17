<?php
require __DIR__ . '/../core/company_market.php';
function market_check(bool $value): void { if (!$value) throw new RuntimeException('Company market regression failed.'); }
function te(string $text): string { return htmlspecialchars($text, ENT_QUOTES, 'UTF-8'); }
$now = new DateTimeImmutable('2026-11-17T12:00:00Z');
$rows = [
    ['c_name'=>'ADDOHA','pa'=>30,'date'=>'2026-11-16T10:00:00Z'],
    ['c_name'=>'ADDOHA','pa'=>'31.25','date'=>'2026-11-17T10:00:00Z'],
    ['c_name'=>'ADDOHA','pa'=>999,'date'=>'2026-11-18T10:00:00Z'],
    ['c_name'=>'OTHER','pa'=>999,'date'=>'2026-11-17T11:00:00Z'],
    ['c_name'=>'ADDOHA','pa'=>0,'date'=>'2026-11-17T11:00:00Z'],
];
$quote = company_market_quote('ADDOHA', $rows, $now);
market_check($quote['price'] === 31.25);
market_check(company_market_quote('ADDOHA', [], $now) === null);
market_check(company_market_quote('ADDOHA', [['c_name'=>'ADDOHA','pa'=>10,'date'=>'2026-02-30']], $now) === null);
market_check(company_market_quote('ADDOHA', [['c_name'=>'ADDOHA','pa'=>true,'date'=>'2026-11-16']], $now) === null);
$row = ['symbol'=>'ADH','captured_at'=>'2026-11-16T10:00:00Z','snapshot'=>['symbol'=>'ADH',
    'bids'=>[['price'=>30,'quantity'=>10],['price'=>31,'quantity'=>20]],
    'asks'=>[['price'=>33,'quantity'=>5],['price'=>32,'quantity'=>8]],
    'source'=>'private-fixture-must-not-render']];
$book = company_market_book($row, 'ADH', $now);
market_check($book['bids'][0]['price'] === 31.0 && $book['asks'][0]['price'] === 32.0);
market_check(company_market_book($row, 'OTHER', $now) === null);
$invalid = $row; $invalid['snapshot']['symbol'] = 'OTHER';
market_check(company_market_book($invalid, 'ADH', $now) === null);
$invalid = $row; $invalid['snapshot']['bids'][0]['quantity'] = 1.5;
market_check(company_market_book($invalid, 'ADH', $now) === null);
$oneSided = $row; $oneSided['snapshot']['asks'] = [];
market_check(company_market_book($oneSided, 'ADH', $now)['asks'] === []);
ob_start(); render_company_market($quote, $book, $now); $html = ob_get_clean();
market_check(str_contains($html, '31,25') && str_contains($html, 'Carnet historique'));
market_check(str_contains($html, '17/11/2026') && !str_contains($html, 'private-fixture'));
ob_start(); render_company_market(null, null, $now); $html = ob_get_clean();
market_check(str_contains($html, 'Cours indisponible') && str_contains($html, 'indisponible pour le moment'));
echo "Company market tests passed.\n";
