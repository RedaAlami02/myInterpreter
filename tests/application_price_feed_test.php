<?php
require_once __DIR__ . '/shadow_market_feed_test.php';
$payload = json_decode(file_get_contents(getenv('APP_ROWS_FIXTURE') ?: __DIR__.'/fixtures/shadow_market_preview_v3.json'), true, 64, JSON_THROW_ON_ERROR);
$asOf = ShadowMarketSnapshot::timestamp($payload['as_of']);
$snapshot = new ShadowMarketSnapshot($payload);
$rows = $snapshot->applicationRowsAt($asOf);
assertPreview(count($rows) === count($payload['rows']));
$references = array_values(array_filter($rows, fn($row) => $row['price_basis'] === 'INSTRUMENT_REFERENCE'));
assertPreview(count($references) === 1 && $references[0]['fields']['pa'] === 21.25);
assertPreview($references[0]['source_event_at'] === null && $references[0]['reported_day'] === null);
assertPreview($references[0]['portfolio_valuation_eligible'] === false);
assertPreview($snapshot->applicationRowsAt($asOf->modify('-1 day')) === []);
assertPreview($snapshot->applicationRowsAt($asOf->modify('+1 day')) === []);
$private = $payload; $private['rows'][0]['application_fields']['internal_binding'] = 'private-fixture';
assertPreview(!str_contains(json_encode((new ShadowMarketSnapshot($private))->applicationRowsAt($asOf)), 'private-fixture'));
foreach (['pa'=>999,'date'=>'2026-01-01T12:00:00Z','c_name'=>'Other','per'=>true,'per_rating'=>'trusted','qty_traded'=>1.5] as $key=>$value) {
    $bad = $payload; $bad['rows'][0]['application_fields'][$key]=$value;
    rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
}
foreach (['reported_day'=>'2026-02-30','source_event_at'=>['internal_binding'=>'private-fixture']] as $key=>$value) {
    $bad=$payload; $bad['rows'][0][$key]=$value;
    rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
}
$reader = new ShadowMarketFeedReader('https://abcdefghijklmnopqrst.supabase.co','sb_publishable_fixture','fixture.user.signature',
    static function ($url,$headers,$body) use ($payload): array {
        assertPreview(str_ends_with($url,'/rest/v1/rpc/read_shadow_application_feed'));
        return ['status'=>200,'body'=>json_encode($payload)];
    }, true);
assertPreview(count($reader->read()->applicationRowsAt($asOf)) === count($rows));
echo "Application price feed PHP v3 checks passed.\n";
