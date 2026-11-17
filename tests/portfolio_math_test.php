<?php
require_once __DIR__ . '/../core/portfolio_math.php';
$fixture=json_decode(file_get_contents(__DIR__.'/fixtures/portfolio/fifo_cases.json'),true,512,JSON_THROW_ON_ERROR);
foreach($fixture['cases'] as $case) {
 $result=portfolio_realized_totals(portfolio_fifo($case['buys'],$case['sells']),$fixture['commission_rate'],$fixture['tax_rate']);
 foreach($case['expected'] as $key=>$expected) {
  if(abs($result[$key]-$expected)>1e-7) throw new RuntimeException('FIFO fixture mismatch: '.$case['name'].' '.$key);
 }
}
echo 'Passed '.count($fixture['cases'])." shared FIFO/tax cases.\n";
