<?php
require __DIR__ . '/../core/company_history.php';
require __DIR__ . '/../core/SupabaseApp.php';
function history_check(bool $value): void { if (!$value) throw new RuntimeException('History regression failed.'); }
function history_reject(callable $callback): void {
    try { $callback(); } catch (Throwable $error) { return; }
    throw new RuntimeException('Invalid history was accepted.');
}
$document = ['contract' => 'company-daily-history/v1', 'company' => 'Alpha', 'rows' => [
    ['day' => '2026-11-16', 'price' => '10.25', 'private' => 'must-not-escape'],
    ['day' => '2026-11-17', 'price' => '11'],
]];
$points = company_history_points($document, 'Alpha');
history_check($points['points'] === [['day'=>'2026-11-16', 'price'=>10.25], ['day'=>'2026-11-17', 'price'=>11.0]]);
history_check(!str_contains(json_encode($points), 'must-not-escape'));
history_check(company_history_points(array_replace($document, ['rows'=>[]]), 'Alpha')['points'] === []);
history_reject(fn() => company_history_points($document, 'Other'));
foreach ([['day'=>'2026-02-30','price'=>'1'], ['day'=>'2026-11-17','price'=>'-1'],
          ['day'=>'2026-11-17','price'=>true], ['day'=>'2026-11-17','price'=>'INF']] as $invalid) {
    history_reject(fn() => company_history_points(array_replace($document, ['rows'=>[$invalid]]), 'Alpha'));
}
history_reject(fn() => company_history_points(array_replace($document, ['rows'=>array_reverse($document['rows'])]), 'Alpha'));
history_reject(fn() => company_history_points(array_replace($document, ['rows'=>[$document['rows'][0],$document['rows'][0]]]), 'Alpha'));
$client = new SupabaseAppClient('https://abcdefghijklmnopqrst.supabase.co', 'sb_publishable_fixture',
    static function ($method, $url, $headers, $body) use ($document): array {
        history_check($method === 'POST' && str_ends_with($url, '/rpc/read_company_daily_history_v1'));
        history_check(json_decode($body, true) === ['p_name'=>'Alpha']);
        history_check(in_array('Authorization: Bearer fixture.user.signature', $headers, true));
        return ['status'=>200, 'body'=>json_encode($document)];
    });
history_check($client->companyDailyHistory('fixture.user.signature', 'Alpha') === $document);
history_reject(fn() => $client->companyDailyHistory('fixture.user.signature', ''));
echo "Company history normalization and authenticated client tests passed.\n";
