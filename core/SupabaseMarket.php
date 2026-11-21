<?php
/** Read-only market adapter. Authenticated by default; anonymous only when explicitly enabled. */
final class SupabaseMarketReader
{
    private string $baseUrl;
    private string $publishableKey;
    private array $tables;
    private $transport;
    private ?string $accessToken;
    private bool $closingReferences;
    private bool $allowAnonymous;

    public function __construct(string $projectUrl, string $publishableKey, ?callable $transport = null, ?string $accessToken = null, bool $closingReferences = false, bool $allowAnonymous = false)
    {
        if (!preg_match('~^https://[a-z0-9]{10,40}\.supabase\.co/?$~D', $projectUrl)
            || !preg_match('/^sb_publishable_[A-Za-z0-9_-]+$/D', $publishableKey)) {
            throw new InvalidArgumentException('Invalid public Supabase configuration.');
        }
        $this->baseUrl = rtrim($projectUrl, '/') . '/rest/v1';
        $this->publishableKey = $publishableKey;
        $contract = json_decode(file_get_contents(__DIR__ . '/../migrations/supabase/market_contract.json'), true, 512, JSON_THROW_ON_ERROR);
        $this->tables = $contract['tables'];
        $supplemental = json_decode(file_get_contents(__DIR__ . '/../migrations/supabase/supplemental_contract.json'), true, 512, JSON_THROW_ON_ERROR);
        $this->tables += $supplemental['tables'];
        $this->transport = $transport;
        if ($accessToken !== null && !preg_match('/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/D', $accessToken)) {
            throw new InvalidArgumentException('Invalid user access token.');
        }
        $this->accessToken = $accessToken;
        $this->closingReferences = $closingReferences;
        $this->allowAnonymous = $allowAnonymous;
    }

    /** Translate the existing public query helpers into bounded REST filters. */
    public function queryParameters(string $collection, array $queries): array
    {
        if (!isset($this->tables[$collection])) {
            throw new InvalidArgumentException('Unsupported public market collection.');
        }
        $fields = ['id' => 'text'] + $this->tables[$collection]['fields'];
        $params = ['select' => implode(',', array_keys($fields)), 'limit' => 100, 'offset' => 0];
        $orders = [];
        foreach ($queries as $encoded) {
            if (!is_string($encoded)) throw new InvalidArgumentException('Invalid market query.');
            $query = json_decode($encoded, true, 32, JSON_THROW_ON_ERROR);
            if (!is_array($query)) throw new InvalidArgumentException('Invalid market query.');
            $method = $query['method'] ?? '';
            if ($method === 'limit' || $method === 'offset') {
                $value = $query['values'][0] ?? null;
                if (!is_int($value) || ($method === 'limit' && ($value < 1 || $value > 500))
                    || ($method === 'offset' && ($value < 0 || $value > 10000000))) {
                    throw new InvalidArgumentException('Invalid market pagination.');
                }
                $params[$method] = $value;
                continue;
            }
            $field = $query['attribute'] ?? '';
            if ($field === '$id') $field = 'id';
            if (!is_string($field) || !isset($fields[$field])) {
                throw new InvalidArgumentException('Unsupported market field.');
            }
            if ($method === 'orderAsc' || $method === 'orderDesc') {
                $orders[$field] = $field . ($method === 'orderAsc' ? '.asc' : '.desc');
                continue;
            }
            $operators = ['equal' => 'eq', 'greaterThan' => 'gt', 'greaterThanEqual' => 'gte'];
            if (!isset($operators[$method]) || !isset($query['values']) || count($query['values']) !== 1
                || isset($params[$field])) {
                throw new InvalidArgumentException('Unsupported market filter.');
            }
            $value = $query['values'][0];
            if ($value === null && $method === 'equal') {
                $params[$field] = 'is.null';
            } elseif (is_string($value)) {
                // Plain eq/gt/gte filters take literal values. Quoting rules for
                // compound/in filters do not apply here. URL encoding below
                // keeps ampersands, commas and quotes inside this one value.
                $params[$field] = $operators[$method] . '.' . $value;
            } elseif (is_bool($value)) {
                $params[$field] = $operators[$method] . '.' . ($value ? 'true' : 'false');
            } elseif (is_int($value) || (is_float($value) && is_finite($value))) {
                $params[$field] = $operators[$method] . '.' . json_encode($value, JSON_THROW_ON_ERROR);
            } else {
                throw new InvalidArgumentException('Invalid market filter value.');
            }
        }
        // Stable ordering keeps adjacent pages from repeating tied records.
        if (!isset($orders['id'])) $orders['id'] = 'id.desc';
        $params['order'] = implode(',', $orders);
        return $params;
    }

    public function listDocuments(string $collection, array $queries = []): array
    {
        $response = $this->request($collection, $this->queryParameters($collection, $queries));
        return $this->decodeDocuments($response['body']);
    }

    private function decodeDocuments(string $body): array
    {
        $rows = json_decode($body, true, 512, JSON_THROW_ON_ERROR);
        if (!is_array($rows) || !array_is_list($rows)) {
            throw new RuntimeException('Invalid market API response.');
        }
        foreach ($rows as &$row) {
            if (!is_array($row) || !is_string($row['id'] ?? null)) {
                throw new RuntimeException('Invalid market document identity.');
            }
            $row['$id'] = $row['id'];
            unset($row['id']);
        }
        unset($row);
        return $rows;
    }

    /** Concurrent shared-market reads; partial mode isolates optional panels. */
    public function listDocumentsBatch(array $requests, bool $partial = false): array
    {
        if (!$requests) return [];
        if (count($requests) > 8) throw new InvalidArgumentException('Market batch is too large.');
        if ($this->accessToken === null && !$this->allowAnonymous) {
            throw new RuntimeException('Please sign in to view market data.');
        }
        $prepared = [];
        foreach ($requests as $key => [$collection, $queries]) {
            $params = $this->queryParameters($collection, $queries);
            $path = $collection === 'latest_prices' && $this->closingReferences
                ? 'rpc/read_latest_price_references_v1' : $collection;
            $prepared[$key] = $this->baseUrl . '/' . $path . '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
        }
        $parallel = $this->transport === null;
        foreach (['curl_multi_init', 'curl_multi_add_handle', 'curl_multi_exec', 'curl_multi_select',
                  'curl_multi_getcontent', 'curl_multi_remove_handle', 'curl_multi_close'] as $function) {
            $parallel = $parallel && function_exists($function);
        }
        if (!$parallel) {
            $result = [];
            foreach ($requests as $key => [$collection, $queries]) {
                try { $result[$key] = $this->listDocuments($collection, $queries); }
                catch (Throwable $error) {
                    if (!$partial) throw $error;
                    $result[$key] = null;
                }
            }
            return $result;
        }
        $headers = ['apikey: ' . $this->publishableKey, 'Accept: application/json'];
        if ($this->accessToken !== null) $headers[] = 'Authorization: Bearer ' . $this->accessToken;
        $multi = curl_multi_init();
        $handles = [];
        try {
            foreach ($prepared as $key => $url) {
                $handle = curl_init($url);
                curl_setopt_array($handle, [CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false,
                    CURLOPT_TIMEOUT => 20, CURLOPT_CONNECTTIMEOUT => 8, CURLOPT_HTTPHEADER => $headers,
                    CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2]);
                $handles[$key] = $handle;
                curl_multi_add_handle($multi, $handle);
            }
            do {
                $status = curl_multi_exec($multi, $running);
                if ($status !== CURLM_OK) throw new RuntimeException('Market batch request failed.');
                if ($running && curl_multi_select($multi, 0.2) === -1) usleep(1000);
            } while ($running);
            $result = [];
            foreach ($handles as $key => $handle) {
                try {
                    if (curl_errno($handle) || !in_array(curl_getinfo($handle, CURLINFO_HTTP_CODE), [200, 206], true)) {
                        throw new RuntimeException('Supabase market request failed.');
                    }
                    $body = curl_multi_getcontent($handle);
                    if (!is_string($body)) throw new RuntimeException('Invalid market API response.');
                    $result[$key] = $this->decodeDocuments($body);
                } catch (Throwable $error) {
                    if (!$partial) throw $error;
                    $result[$key] = null;
                }
            }
            return $result;
        } finally {
            foreach ($handles as $handle) {
                curl_multi_remove_handle($multi, $handle);
                curl_close($handle);
            }
            curl_multi_close($multi);
        }
    }

    public function countDocuments(string $collection, array $queries = []): int
    {
        $params = $this->queryParameters($collection, $queries);
        $params['select'] = 'id';
        $params['limit'] = 1;
        $params['offset'] = 0;
        $response = $this->request($collection, $params, true);
        $range = $response['headers']['content-range'] ?? '';
        if (!preg_match('~/(\d+)$~D', $range, $match)) {
            throw new RuntimeException('Market API count is unavailable.');
        }
        return (int)$match[1];
    }

    private function request(string $collection, array $params, bool $count = false): array
    {
        if ($this->accessToken === null && !$this->allowAnonymous) {
            throw new RuntimeException('Please sign in to view market data.');
        }
        $path = $collection === 'latest_prices' && $this->closingReferences
            ? 'rpc/read_latest_price_references_v1' : $collection;
        $url = $this->baseUrl . '/' . $path . '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
        $headers = ['apikey: ' . $this->publishableKey, 'Accept: application/json'];
        if ($this->accessToken !== null) {
            $headers[] = 'Authorization: Bearer ' . $this->accessToken;
        }
        if ($count) $headers[] = 'Prefer: count=exact';
        if ($this->transport !== null) {
            $response = ($this->transport)($url, $headers);
        } else {
            $responseHeaders = [];
            $curl = curl_init($url);
            curl_setopt_array($curl, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_FOLLOWLOCATION => false,
                CURLOPT_TIMEOUT => 20,
                CURLOPT_CONNECTTIMEOUT => 8,
                CURLOPT_HTTPHEADER => $headers,
                CURLOPT_SSL_VERIFYPEER => true,
                CURLOPT_SSL_VERIFYHOST => 2,
                CURLOPT_HEADERFUNCTION => static function ($curl, string $line) use (&$responseHeaders): int {
                    $parts = explode(':', $line, 2);
                    if (count($parts) === 2) $responseHeaders[strtolower(trim($parts[0]))] = trim($parts[1]);
                    return strlen($line);
                },
            ]);
            $body = curl_exec($curl);
            $status = curl_getinfo($curl, CURLINFO_HTTP_CODE);
            curl_close($curl);
            if ($body === false) throw new RuntimeException('Supabase market connection failed.');
            $response = ['status' => $status, 'body' => $body, 'headers' => $responseHeaders];
        }
        if (!in_array($response['status'] ?? 0, [200, 206], true)) {
            // Response bodies may contain sensitive diagnostics; do not surface them.
            throw new RuntimeException('Supabase market request failed.');
        }
        return $response;
    }
}
