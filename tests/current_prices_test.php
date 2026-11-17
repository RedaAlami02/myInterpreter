<?php
require_once __DIR__.'/application_price_feed_test.php';
require_once __DIR__.'/../core/current_prices.php';
$current = current_market_prices($snapshot, $asOf);
assertPreview(count($current) === 1);
assertPreview(!isset($current['Company B']));
foreach ($current as $row) {
    assertPreview($row['source'] === 'CURRENT_REPORTED_QUOTE');
    assertPreview($row['portfolio_valuation_eligible'] === false);
}
assertPreview(current_market_prices($snapshot, $asOf->modify('+1 day')) === []);
$old = [['c_name'=>array_key_first($current),'pa'=>1,'date'=>'2000-01-01T12:00:00Z'],
        ['c_name'=>'Other','pa'=>2,'date'=>'2000-01-01T12:00:00Z']];
$merged = overlay_current_prices($old,$current);
assertPreview(count($merged) === 2);
assertPreview($merged[0]['c_name'] === 'Other' && $merged[0]['date'] === '2000-01-01T12:00:00Z');
assertPreview($merged[1]['pa'] !== 1);
$recurringReader = new ShadowMarketFeedReader('https://abcdefghijklmnopqrst.supabase.co','sb_publishable_fixture','fixture.user.signature',
    static function($url,$headers,$body) use ($payload): array {
        assertPreview(str_ends_with($url,'/read_shadow_application_feed_recurring_v1'));
        return ['status'=>200,'body'=>json_encode($payload)];
    },true,true);
assertPreview(count($recurringReader->read()->applicationRowsAt($asOf)) === count($rows));
echo "Current quote display and recurring RPC checks passed.\n";
