<?php
require_once __DIR__ . '/../core/ShadowMarketFeed.php';
function assertPreview(bool $ok): void { if (!$ok) throw new RuntimeException('Preview regression failed.'); }
function rejectsPreview(callable $callback): void {
    try { $callback(); } catch (RuntimeException | InvalidArgumentException $error) { return; }
    throw new RuntimeException('Expected preview rejection.');
}
$fixture = json_decode(file_get_contents(__DIR__.'/fixtures/shadow_market_preview.json'), true, 64, JSON_THROW_ON_ERROR);
$now = new DateTimeImmutable('2026-10-28T12:05:00Z');
$snapshot = new ShadowMarketSnapshot($fixture);
assertPreview($snapshot->rowsAt($now)[0]['price_decimal'] === '10.50000000000000000001');
assertPreview($snapshot->rowsAt($now)[1]['price_decimal'] === null);
assertPreview($snapshot->rowsAt(new DateTimeImmutable('2026-10-28T12:20:00Z'))[0]['price_decimal'] === null);
assertPreview($snapshot->rowsAt(new DateTimeImmutable('2026-10-28T11:59:00Z'))[0]['status'] === 'FUTURE_CAPTURE');
$private = $fixture; $private['rows'][0]['source_identity']='private-fixture-binding';
assertPreview(!str_contains(json_encode((new ShadowMarketSnapshot($private))->rowsAt($now)), 'private-fixture-binding'));
foreach (['1000000000000.00000000001','0','NaN',true,10.5] as $price) {
    $bad = $fixture; $bad['rows'][0]['price_decimal'] = $price;
    rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
}
foreach (['2026-02-30T12:00:00Z','2026-10-28T12:00:00'] as $time) {
    $bad=$fixture; $bad['rows'][0]['captured_at']=$time;
    rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
}
$bad=$fixture; $bad['rows'][1]['price_decimal']='50.00'; rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
$bad=$fixture; $bad['rows'][0]['prediction_eligible']=true; rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
$reader = new ShadowMarketFeedReader('https://abcdefghijklmnopqrst.supabase.co','sb_publishable_fixture','fixture.user.signature',
    static function ($url,$headers,$body) use ($fixture): array {
        assertPreview(str_ends_with($url,'/rest/v1/rpc/read_shadow_market_feed'));
        assertPreview(in_array('Authorization: Bearer fixture.user.signature',$headers,true));
        assertPreview($body==='{}');return ['status'=>200,'body'=>json_encode($fixture)];
    });
assertPreview($reader->read()->rowsAt($now)[0]['price_decimal']==='10.50000000000000000001');
rejectsPreview(fn() => (new ShadowMarketFeedReader('https://abcdefghijklmnopqrst.supabase.co','sb_publishable_fixture',null))->read());
$reader = new ShadowMarketFeedReader('https://abcdefghijklmnopqrst.supabase.co','sb_publishable_fixture','fixture.user.signature',fn() => ['status'=>500,'body'=>'private-response']);
try { $reader->read(); } catch (RuntimeException $error) { assertPreview(!str_contains($error->getMessage(),'private-response')); }
$v2 = json_decode(file_get_contents(__DIR__.'/fixtures/shadow_market_preview_v2.json'), true, 64, JSON_THROW_ON_ERROR);
$reference = new ShadowMarketSnapshot($v2);
assertPreview($reference->rowsAt($now)[1]['price_decimal'] === null);
assertPreview($reference->displayRowsAt($now)[1]['display_price_decimal'] === '21.25');
assertPreview($reference->displayRowsAt($now)[1]['display_price_basis'] === 'INSTRUMENT_REFERENCE');
assertPreview($reference->displayRowsAt(new DateTimeImmutable('2026-10-28T12:10:00Z'))[1]['display_price_decimal'] === null);
assertPreview($reference->displayRowsAt(new DateTimeImmutable('2026-10-28T11:59:00Z'))[1]['display_price_decimal'] === null);
$saved = [['$id'=>'old-id','c_name'=>'Company B','pa'=>'19.75','date'=>'2026-10-27T12:00:00Z']];
$expired = new DateTimeImmutable('2026-10-28T12:10:00Z');
assertPreview($reference->displayRowsAt($now, $saved)[1]['display_price_decimal'] === '21.25');
assertPreview($reference->displayRowsAt($expired, $saved)[1]['display_price_basis'] === 'RECOVERED_LAST_KNOWN');
assertPreview($reference->displayRowsAt($expired, $saved)[1]['price_decimal'] === null);
$future=$saved; $future[0]['date']='2026-10-29T12:00:00Z';
assertPreview($reference->displayRowsAt($expired, $future)[1]['display_price_decimal'] === null);
$conflicted=$v2; $conflicted['rows'][1]['reference_price']=null; $conflicted['rows'][1]['reference_conflict']=true;
assertPreview((new ShadowMarketSnapshot($conflicted))->displayRowsAt($now,$saved)[1]['display_price_decimal'] === null);
assertPreview((new ShadowMarketSnapshot($conflicted))->displayRowsAt($now,$saved)[1]['display_price_basis'] === 'CONFLICTING_INSTRUMENT_PRICES');
foreach (['price_decimal'=>true,'source_event_at'=>'2026-10-28T12:00:00Z','reported_day'=>'2026-10-28',
          'portfolio_valuation_eligible'=>true,'prediction_eligible'=>true,'captured_at'=>'2026-10-28T12:01:00Z',
          'expires_at'=>'2026-10-28T14:00:00Z'] as $key=>$value) {
    $bad=$v2; $bad['rows'][1]['reference_price'][$key]=$value;
    rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
}
$private=$v2; $private['rows'][1]['reference_price']['native_binding']='private-reference-binding';
assertPreview(!str_contains(json_encode((new ShadowMarketSnapshot($private))->displayRowsAt($now)), 'private-reference-binding'));
$bad=$v2; $bad['rows'][0]['reference_price']=$v2['rows'][1]['reference_price'];
rejectsPreview(fn() => new ShadowMarketSnapshot($bad));
echo "Shadow market feed PHP v1/v2 checks passed.\n";
