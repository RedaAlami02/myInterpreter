<?php
require_once __DIR__ . '/SupabaseApp.php';

/**
 * Owner maintenance writes. The caller's JWT is forwarded and the database
 * rechecks administrator membership; this client never holds an elevated key.
 */
final class SupabaseAdminClient
{
    private string $baseUrl;
    private array $fields;
    private $transport;

    public function __construct(string $projectUrl, private string $publishableKey, ?callable $transport = null)
    {
        if (!preg_match('~^https://[a-z0-9]{10,40}\.supabase\.co/?$~D', $projectUrl)
            || !preg_match('/^sb_publishable_[A-Za-z0-9_-]+$/D', $publishableKey)) {
            throw new InvalidArgumentException('Invalid public Supabase configuration.');
        }
        $contract = json_decode(
            file_get_contents(__DIR__ . '/../migrations/supabase/market_contract.json'),
            true, 512, JSON_THROW_ON_ERROR
        );
        $this->fields = $contract['tables']['company']['fields'];
        unset($this->fields['name'], $this->fields['date']);
        $this->baseUrl = rtrim($projectUrl, '/') . '/rest/v1';
        $this->transport = $transport;
    }

    /** @return array{status:string,name:string,fields?:int} */
    public function updateCompany(string $accessToken, string $name, array $fields): array
    {
        if ($name === '' || $name !== trim($name) || mb_strlen($name) > 200) {
            throw new InvalidArgumentException('Invalid company name.');
        }
        if ($fields === [] || array_diff_key($fields, $this->fields) !== []) {
            throw new InvalidArgumentException('Unsupported company field.');
        }
        foreach ($fields as $field => $value) {
            $this->assertValue($this->fields[$field], $value);
        }
        $result = $this->request('POST', '/rpc/admin_update_company', [
            'p_name' => $name,
            'p_fields' => (object)$fields,
        ], $accessToken);
        if (!is_array($result) || !in_array($result['status'] ?? null, ['UPDATED', 'MISSING'], true)
            || ($result['name'] ?? null) !== $name) {
            throw new RuntimeException('Invalid company update receipt.');
        }
        return $result;
    }

    /** Apply only server-validated saved-profile biography gaps, at most 25 per batch. */
    public function applyProfileBiographies(string $accessToken, array $changes): array
    {
        if (!$changes || !array_is_list($changes) || count($changes)>25) {
            throw new InvalidArgumentException('Invalid profile batch.');
        }
        $result=$this->request('POST','/rpc/admin_apply_profile_biographies',[
            'p_changes'=>$changes,
        ],$accessToken);
        if (!is_array($result) || !is_array($result['results'] ?? null)
            || !array_is_list($result['results']) || count($result['results'])!==count($changes)) {
            throw new RuntimeException('Invalid profile batch receipt.');
        }
        foreach ($result['results'] as $index=>$row) {
            if (!is_array($row) || ($row['name'] ?? null)!==($changes[$index]['name'] ?? null)
                || !in_array($row['status'] ?? null,['UPDATED','UNCHANGED','PROTECTED','STALE','MISSING'],true)) {
                throw new RuntimeException('Invalid profile update receipt.');
            }
        }
        return $result['results'];
    }

    public function recordOperatorSnapshot(string $accessToken, array $fields): string
    {
        $allowed = ['c_name' => true, 'pa' => true, 'cb' => true, 'per' => true, 'peg' => true, 'pr' => true, 'pb' => true];
        if (!isset($fields['c_name'], $fields['pa']) || array_diff_key($fields, $allowed) !== []) {
            throw new InvalidArgumentException('Invalid snapshot input.');
        }
        if (!is_string($fields['c_name']) || $fields['c_name'] === ''
            || $fields['c_name'] !== trim($fields['c_name']) || mb_strlen($fields['c_name']) > 200) {
            throw new InvalidArgumentException('Invalid snapshot company.');
        }
        foreach ($fields as $field => $value) {
            if ($field === 'c_name') continue;
            $this->assertValue('numeric', $value);
            if ($field === 'pa' && $value !== null && !($value > 0)) {
                throw new InvalidArgumentException('Invalid snapshot price.');
            }
        }
        $result = $this->request('POST', '/rpc/admin_record_operator_snapshot', [
            'p_fields' => (object)$fields,
        ], $accessToken);
        if (!is_string($result) || !preg_match('/^[a-f0-9]{32}$/D', $result)) {
            throw new RuntimeException('Invalid snapshot receipt.');
        }
        return $result;
    }

    /** @return list<array<string,mixed>> Pending exchange annual candidates. */
    public function readExchangeAnnualCandidates(string $accessToken): array
    {
        $result = $this->request('POST', '/rpc/read_exchange_annual_candidates', [], $accessToken);
        if (!is_array($result) || !array_is_list($result)) {
            throw new RuntimeException('Invalid annual candidate list.');
        }
        return $result;
    }

    public function applyExchangeAnnualCandidates(string $accessToken, string $reportSha256, array $symbols): array
    {
        if (!preg_match('/^[a-f0-9]{64}$/D', $reportSha256)
            || !$symbols || count($symbols) > 50) {
            throw new InvalidArgumentException('Invalid annual application.');
        }
        $result = $this->request('POST', '/rpc/apply_exchange_annual_candidates', [
            'p_report_sha256' => $reportSha256,
            'p_symbols' => array_values($symbols),
        ], $accessToken);
        if (!is_array($result) || ($result['status'] ?? null) !== 'COMPLETE') {
            throw new RuntimeException('Invalid annual application receipt.');
        }
        return $result;
    }

    public function rejectExchangeAnnualCandidates(string $accessToken, string $reportSha256, array $symbols): array
    {
        if (!preg_match('/^[a-f0-9]{64}$/D', $reportSha256)
            || !$symbols || count($symbols) > 50) {
            throw new InvalidArgumentException('Invalid annual rejection.');
        }
        $result = $this->request('POST', '/rpc/reject_exchange_annual_candidates', [
            'p_report_sha256' => $reportSha256,
            'p_symbols' => array_values($symbols),
        ], $accessToken);
        if (!is_array($result) || ($result['status'] ?? null) !== 'COMPLETE') {
            throw new RuntimeException('Invalid annual rejection receipt.');
        }
        return $result;
    }

    private function assertValue(string $type, $value): void
    {
        if ($value === null) return;
        if ($type === 'text') {
            if (!is_string($value) || $value === '' || mb_strlen($value) > 4000) {
                throw new InvalidArgumentException('Invalid text field.');
            }
            return;
        }
        if ($type === 'integer') {
            if (!is_int($value) || $value < 1900 || $value > 2200) {
                throw new InvalidArgumentException('Invalid year field.');
            }
            return;
        }
        if (is_bool($value) || (!is_int($value) && !is_float($value))
            || !is_finite((float)$value) || abs((float)$value) > 1000000000000000) {
            throw new InvalidArgumentException('Invalid numeric field.');
        }
    }

    private function request(string $method, string $path, array $data, string $accessToken): mixed
    {
        if (!preg_match('/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/D', $accessToken)) {
            throw new InvalidArgumentException('Invalid user session token.');
        }
        $headers = [
            'apikey: ' . $this->publishableKey,
            'Content-Type: application/json',
            'Accept: application/json',
            'Authorization: Bearer ' . $accessToken,
        ];
        // Hosting may use 17 digits, expanding 0.57 into 0.56999999999999995.
        // Shortest-roundtrip JSON preserves values without rounding or weakening SQL checks.
        $previousPrecision = ini_get('serialize_precision');
        if (ini_set('serialize_precision', '-1') === false) {
            throw new RuntimeException('Numeric serialization is unavailable.');
        }
        try {
            $body = json_encode($data ?: new stdClass(), JSON_THROW_ON_ERROR);
        } finally {
            if ($previousPrecision !== false) ini_set('serialize_precision', $previousPrecision);
        }
        if ($this->transport !== null) {
            $response = ($this->transport)($method, $this->baseUrl . $path, $headers, $body);
        } else {
            $curl = curl_init($this->baseUrl . $path);
            curl_setopt_array($curl, [
                CURLOPT_RETURNTRANSFER => true, CURLOPT_CUSTOMREQUEST => $method,
                CURLOPT_HTTPHEADER => $headers, CURLOPT_FOLLOWLOCATION => false,
                CURLOPT_CONNECTTIMEOUT => 8, CURLOPT_TIMEOUT => 20,
                CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
                CURLOPT_POSTFIELDS => $body,
            ]);
            $raw = curl_exec($curl);
            $status = curl_getinfo($curl, CURLINFO_HTTP_CODE);
            curl_close($curl);
            if ($raw === false) throw new RuntimeException('Supabase connection is unavailable.');
            $response = ['status' => $status, 'body' => $raw];
        }
        try {
            $decoded = json_decode($response['body'] ?: 'null', true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $error) {
            throw new RuntimeException('Invalid Supabase response.');
        }
        $status = (int)($response['status'] ?? 0);
        if ($status < 200 || $status >= 300) {
            // Never surface server diagnostics or record contents.
            throw new SupabaseRequestException($status);
        }
        return $decoded;
    }
}
