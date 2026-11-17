<?php
require_once __DIR__.'/../core/ShadowMarketFeed.php';
require_once __DIR__.'/../core/current_prices.php';
require_once __DIR__.'/../core/portfolio_prices.php';
$fixture=json_decode(file_get_contents(__DIR__.'/fixtures/portfolio/reference_price_parity.json'),true,512,JSON_THROW_ON_ERROR);
$template=json_decode(file_get_contents(__DIR__.'/fixtures/shadow_market_preview_v3.json'),true,512,JSON_THROW_ON_ERROR);
foreach ($fixture['scenarios'] as $scenario) {
    $row=$template['rows'][0];
    $row['c_name']='SGTM'; $row['price_decimal']='526';
    $row['captured_at']=$scenario['captured']; $row['expires_at']=$scenario['expires'];
    $row['reported_day']=$scenario['day']; $row['application_expires_at']=$scenario['expires'];
    $row['application_fields']['c_name']='SGTM'; $row['application_fields']['pa']=526;
    $row['application_fields']['date']=$scenario['captured'];
    $payload=$template; $payload['rows']=[$row]; $payload['captured_at']=$scenario['captured']; $payload['as_of']=$scenario['now'];
    $now=new DateTimeImmutable($scenario['now']);
    $current=current_market_prices(new ShadowMarketSnapshot($payload),$now);
    $prices=portfolio_recorded_prices(overlay_current_prices($fixture['references'],$current),$now);
    if ($prices['SGTM']['price'] != $scenario['expected']) throw new RuntimeException('Reference parity failed: '.$scenario['name']);
}
echo "Web reference parity: four timing scenarios passed.\n";
