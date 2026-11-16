<?php
require_once __DIR__ . '/../core/SupabaseAdmin.php';

$url = 'https://abcdefghij.supabase.co';
$key = 'sb_publishable_test_key';
$calls = [];
$transport = static function (string $method, string $url, array $headers, string $body) use (&$calls): array {
    $calls[] = ['method' => $method, 'url' => $url, 'headers' => $headers, 'body' => $body];
    if (str_ends_with($url, '/rpc/read_exchange_annual_candidates')) {
        return ['status' => 200, 'body' => json_encode([['symbol' => 'TEST']])];
    }
    return ['status' => 200, 'body' => json_encode(['status' => 'COMPLETE', 'applied' => 1,
                                                    'skipped' => 0, 'rejected' => 1])];
};
$client = new SupabaseAdminClient($url, $key, $transport);
$token = 'aa.bb.cc';
$sha = str_repeat('a', 64);

$pending = $client->readExchangeAnnualCandidates($token);
if ($pending !== [['symbol' => 'TEST']] || !str_ends_with($calls[0]['url'], '/rpc/read_exchange_annual_candidates')) {
    throw new RuntimeException('Read RPC mismatch');
}
$applied = $client->applyExchangeAnnualCandidates($token, $sha, ['TEST']);
$body = json_decode($calls[1]['body'], true);
if (($applied['status'] ?? null) !== 'COMPLETE'
    || ($body['p_report_sha256'] ?? null) !== $sha
    || ($body['p_symbols'] ?? null) !== ['TEST']
    || !str_ends_with($calls[1]['url'], '/rpc/apply_exchange_annual_candidates')) {
    throw new RuntimeException('Apply RPC mismatch');
}
$rejected = $client->rejectExchangeAnnualCandidates($token, $sha, ['TEST']);
if (($rejected['status'] ?? null) !== 'COMPLETE'
    || !str_ends_with($calls[2]['url'], '/rpc/reject_exchange_annual_candidates')) {
    throw new RuntimeException('Reject RPC mismatch');
}
try {
    $client->applyExchangeAnnualCandidates($token, 'bad', ['TEST']);
    throw new RuntimeException('Invalid digest accepted');
} catch (InvalidArgumentException $expected) {
}
echo "Exchange annual RPC client tests passed.\n";
