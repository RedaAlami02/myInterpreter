<?php
/** User-scoped Auth and portfolio REST client. Never accepts an elevated key. */
final class SupabaseRequestException extends RuntimeException
{
    public function __construct(public readonly int $httpStatus, public readonly string $reason = '')
    {
        parent::__construct('Supabase request could not be completed.');
    }
}

final class SupabaseAppClient
{
    private string $baseUrl;
    private $transport;
    private array $recoveredTokens = [];

    public function __construct(string $projectUrl, private string $publishableKey, ?callable $transport = null, private bool $portfolioRecoveryEnabled = false)
    {
        if (!preg_match('~^https://[a-z0-9]{10,40}\.supabase\.co/?$~D', $projectUrl)
            || !preg_match('/^sb_publishable_[A-Za-z0-9_-]+$/D', $publishableKey)) {
            throw new InvalidArgumentException('Invalid public Supabase configuration.');
        }
        $this->baseUrl = rtrim($projectUrl, '/');
        $this->transport = $transport;
    }

    public function signUp(string $email, string $password, string $name = '', ?string $codeChallenge = null, ?string $redirectTo = null): array
    {
        $data = ['email' => $email, 'password' => $password, 'data' => ['name' => $name]];
        if ($codeChallenge !== null) {
            $this->assertChallenge($codeChallenge);
            $data['code_challenge'] = $codeChallenge;
            $data['code_challenge_method'] = 's256';
        }
        if ($redirectTo !== null) {
            $this->assertRedirect($redirectTo);
        }
        return $this->request('POST', '/auth/v1/signup' . ($redirectTo === null ? '' : '?redirect_to=' . rawurlencode($redirectTo)), $data);
    }

    public function recover(string $email, ?string $redirectTo = null, ?string $codeChallenge = null): void
    {
        $data = ['email' => $email];
        if ($codeChallenge !== null) {
            $this->assertChallenge($codeChallenge);
            $data['code_challenge'] = $codeChallenge;
            $data['code_challenge_method'] = 's256';
        }
        if ($redirectTo !== null) {
            $this->assertRedirect($redirectTo);
        }
        $this->request('POST', '/auth/v1/recover' . ($redirectTo === null ? '' : '?redirect_to=' . rawurlencode($redirectTo)), $data);
    }

    public function resendConfirmation(string $email, ?string $redirectTo = null, ?string $codeChallenge = null): void
    {
        $data = ['type' => 'signup', 'email' => $email];
        if ($redirectTo !== null) {
            $this->assertRedirect($redirectTo);
        }
        if ($codeChallenge !== null) {
            $this->assertChallenge($codeChallenge);
            $data['code_challenge'] = $codeChallenge;
            $data['code_challenge_method'] = 's256';
        }
        $this->request('POST', '/auth/v1/resend' . ($redirectTo === null ? '' : '?redirect_to=' . rawurlencode($redirectTo)), $data);
    }

    /** PKCE code exchange; the verifier never leaves the server session store. */
    public function exchangeCode(string $code, string $verifier): array
    {
        if (!preg_match('/^[A-Za-z0-9._~-]{8,512}$/D', $code)
            || !preg_match('/^[A-Za-z0-9._~-]{43,128}$/D', $verifier)) {
            throw new InvalidArgumentException('Invalid authorization code.');
        }
        return $this->request('POST', '/auth/v1/token?grant_type=pkce', [
            'auth_code' => $code, 'code_verifier' => $verifier,
        ]);
    }

    public function updatePassword(string $accessToken, string $password): array
    {
        if (strlen($password) < 8 || strlen($password) > 128) {
            throw new InvalidArgumentException('Password must be between 8 and 128 characters.');
        }
        return $this->request('PUT', '/auth/v1/user', ['password' => $password], $accessToken);
    }

    private function assertChallenge(string $challenge): void
    {
        if (!preg_match('/^[A-Za-z0-9_-]{43}$/D', $challenge)) {
            throw new InvalidArgumentException('Invalid code challenge.');
        }
    }

    private function assertRedirect(string $url): void
    {
        if (!preg_match('~^https://[^\s]{1,2048}$~D', $url) || !filter_var($url, FILTER_VALIDATE_URL)) {
            throw new InvalidArgumentException('Invalid redirect URL.');
        }
    }

    public function signIn(string $email, string $password): array
    {
        return $this->request('POST', '/auth/v1/token?grant_type=password', ['email' => $email, 'password' => $password]);
    }

    public function refresh(string $refreshToken): array
    {
        if ($refreshToken === '' || strlen($refreshToken) > 4096 || preg_match('/[\x00-\x20\x7f]/', $refreshToken)) {
            throw new InvalidArgumentException('Invalid session refresh token.');
        }
        return $this->request('POST', '/auth/v1/token?grant_type=refresh_token', ['refresh_token' => $refreshToken]);
    }

    public function user(string $accessToken): array
    {
        return $this->request('GET', '/auth/v1/user', [], $accessToken);
    }

    public function signOut(string $accessToken): void
    {
        $this->request('POST', '/auth/v1/logout?scope=local', [], $accessToken);
    }

    public function recordTrade(string $accessToken, string $requestId, string $side, string $name, $quantity, $price): string
    {
        if (!preg_match('/^[a-f0-9-]{36}$/Di', $requestId) || !in_array($side, ['buy', 'sell'], true)) {
            throw new InvalidArgumentException('Invalid trade request.');
        }
        $this->ensurePortfolioRecovery($accessToken);
        $result = $this->request('POST', '/rest/v1/rpc/record_trade', [
            'p_request_id' => $requestId, 'p_side' => $side, 'p_c_name' => $name,
            'p_quantity' => $quantity, 'p_price' => $price,
        ], $accessToken);
        if (!is_string($result) || strtolower($result) !== strtolower($requestId)) {
            throw new RuntimeException('Invalid trade receipt.');
        }
        return $result;
    }

    public function companyDailyHistory(string $accessToken, string $name): array
    {
        if ($name === '' || strlen($name) > 640 || mb_strlen($name) > 160) {
            throw new InvalidArgumentException('Invalid company.');
        }
        $result = $this->request('POST', '/rest/v1/rpc/read_company_daily_history_v1', ['p_name' => $name], $accessToken);
        if (!is_array($result) || ($result['contract'] ?? null) !== 'company-daily-history/v1'
            || ($result['company'] ?? null) !== $name || !is_array($result['rows'] ?? null)
            || !array_is_list($result['rows']) || count($result['rows']) > 10000) {
            throw new RuntimeException('Company history is unavailable.');
        }
        return $result;
    }

    public function recentMarketSessions(string $accessToken, string $symbol): array
    {
        if (!preg_match('/^[A-Z0-9][A-Z0-9._-]{0,31}$/D',$symbol)) throw new InvalidArgumentException('Invalid instrument.');
        $result=$this->request('POST','/rest/v1/rpc/read_recent_market_sessions',['p_symbol'=>$symbol,'p_limit'=>5],$accessToken);
        if (!is_array($result) || ($result['contract']??null)!=='recent-market-sessions/v1'
            || ($result['symbol']??null)!==$symbol) throw new RuntimeException('Session history is unavailable.');
        return $result;
    }

    /** Date-idempotent valuation of the caller's own portfolio. */
    public function recordDailyValuation(string $accessToken): array
    {
        $this->ensurePortfolioRecovery($accessToken);
        $result = $this->request('POST', '/rest/v1/rpc/record_official_close_valuation', [], $accessToken);
        $statuses = ['CREATED', 'EXISTING', 'EMPTY', 'PRICE_UNAVAILABLE', 'OUTSIDE_WINDOW', 'DISABLED', 'RECOVERY_REQUIRED'];
        if (!is_array($result) || !in_array($result['status'] ?? null, $statuses, true)) {
            throw new RuntimeException('Invalid valuation receipt.');
        }
        if (!is_string($result['date'] ?? null) || !preg_match('/^\d{4}-\d{2}-\d{2}$/D', $result['date'])) {
            throw new RuntimeException('Invalid valuation receipt.');
        }
        if (array_key_exists('value', $result) && $result['value'] !== null
            && !is_int($result['value']) && !is_float($result['value'])) {
            throw new RuntimeException('Invalid valuation receipt.');
        }
        if (in_array($result['status'], ['CREATED', 'EXISTING'], true)) {
            if (!isset($result['value']) || !is_finite((float)$result['value'])
                || !in_array($result['basis'] ?? null, ['OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION', 'PREEXISTING_UNVERIFIED'], true)
                || ($result['status'] === 'CREATED' && $result['basis'] !== 'OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION')) {
                throw new RuntimeException('Official-close valuation receipt required.');
            }
        }
        return $result;
    }

    /** Daily valuation from the published close history (no close batch needed). */
    public function recordHistoryValuation(string $accessToken): array
    {
        $result = $this->request('POST', '/rest/v1/rpc/record_daily_valuation_from_history', [], $accessToken);
        if (!is_array($result)
            || !in_array($result['status'] ?? null,
                          ['CREATED', 'EXISTING', 'EMPTY', 'PRICE_UNAVAILABLE'], true)) {
            throw new RuntimeException('Invalid valuation receipt.');
        }
        if (!is_string($result['date'] ?? null) || !preg_match('/^\d{4}-\d{2}-\d{2}$/D', $result['date'])) {
            throw new RuntimeException('Invalid valuation receipt.');
        }
        if (($result['status'] ?? '') === 'CREATED') {
            if (!isset($result['value']) || !is_finite((float)$result['value'])
                || ($result['basis'] ?? null) !== 'HISTORY_CLOSE') {
                throw new RuntimeException('History valuation receipt required.');
            }
        }
        return $result;
    }

    /** RLS enforces ownership even if the caller omits a user_id filter. */    public function listDocuments(string $collection, array $queries, string $accessToken): array
    {
        $fields = match ($collection) {
            'achats' => ['id','user_id','c_name','number','prix_achat','date','purchase_day','purchase_day_basis'],
            'ventes' => ['id','user_id','c_name','number','prix_vente','date'],
            'portefeuille' => ['id','user_id','c_name','quantity','total_cost'],
            'benefits' => ['id','user_id','date','value'],
            default => throw new InvalidArgumentException('Unsupported private collection.'),
        };
        $this->ensurePortfolioRecovery($accessToken);
        $params = ['select' => implode(',', $fields), 'limit' => 100, 'offset' => 0];
        $orders = [];
        foreach ($queries as $encoded) {
            $query = json_decode($encoded, true, 32, JSON_THROW_ON_ERROR);
            $method = $query['method'] ?? '';
            $value = $query['values'][0] ?? null;
            if (in_array($method, ['limit','offset'], true)) {
                if (!is_int($value) || $value < ($method === 'limit' ? 1 : 0)
                    || $value > ($method === 'limit' ? 500 : 10000000)) {
                    throw new InvalidArgumentException('Invalid private pagination.');
                }
                $params[$method] = $value;
                continue;
            }
            $field = ($query['attribute'] ?? '') === '$id' ? 'id' : ($query['attribute'] ?? '');
            if (!in_array($field, $fields, true)) throw new InvalidArgumentException('Invalid private field.');
            if ($method === 'orderAsc' || $method === 'orderDesc') {
                $orders[$field] = $field . ($method === 'orderAsc' ? '.asc' : '.desc');
            } elseif ($method === 'equal' && count($query['values'] ?? []) === 1
                && (is_string($value) || is_int($value)) && !isset($params[$field])) {
                $params[$field] = 'eq.' . $value;
            } else {
                throw new InvalidArgumentException('Unsupported private query.');
            }
        }
        if (!isset($orders['id'])) $orders['id'] = 'id.desc';
        $params['order'] = implode(',', $orders);
        $rows = $this->request('GET', '/rest/v1/' . $collection . '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986), [], $accessToken);
        if (!is_array($rows) || !array_is_list($rows)) throw new RuntimeException('Invalid private data response.');
        foreach ($rows as &$row) {
            if (!is_array($row) || !is_string($row['id'] ?? null)) throw new RuntimeException('Invalid private record.');
            $row['$id'] = $row['id'];
            unset($row['id']);
        }
        unset($row);
        return $rows;
    }

    private function ensurePortfolioRecovery(string $accessToken): void
    {
        if (!$this->portfolioRecoveryEnabled) return;
        $key = hash('sha256', $accessToken);
        if (isset($this->recoveredTokens[$key])) return;
        $result = $this->request('POST', '/rest/v1/rpc/claim_saved_portfolio', [], $accessToken);
        $status = is_array($result) ? ($result['status'] ?? null) : null;
        if ($status === 'PASSWORD_REQUIRED') throw new RuntimeException('Sign out and sign in with your password to recover the saved portfolio.');
        if (in_array($status, ['DISABLED', 'NOT_AVAILABLE'], true) && array_keys($result) === ['status']) return;
        if ($status === 'CLAIMED' && count($result) === 2 && is_array($result['counts'] ?? null)) {
            $keys = array_keys($result['counts']); sort($keys);
            if ($keys === ['achats','benefits','portefeuille','ventes']
                && count(array_filter($result['counts'], fn($value) => is_int($value) && $value >= 0 && $value <= 10000)) === 4
                && array_sum($result['counts']) > 0 && array_sum($result['counts']) <= 10000) {
                $this->recoveredTokens[$key] = true;
                return;
            }
        }
        throw new RuntimeException('Saved portfolio recovery requires review before accessing or changing holdings.');
    }

    private function request(string $method, string $path, array $data = [], ?string $accessToken = null): mixed
    {
        $headers = ['apikey: ' . $this->publishableKey, 'Content-Type: application/json', 'Accept: application/json'];
        if ($accessToken !== null) {
            if (!preg_match('/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/D', $accessToken)) {
                throw new InvalidArgumentException('Invalid user session token.');
            }
            $headers[] = 'Authorization: Bearer ' . $accessToken;
        }
        $body = $method === 'GET' ? null : json_encode($data ?: new stdClass(), JSON_THROW_ON_ERROR);
        if ($this->transport !== null) {
            $response = ($this->transport)($method, $this->baseUrl . $path, $headers, $body);
        } else {
            $curl = curl_init($this->baseUrl . $path);
            curl_setopt_array($curl, [
                CURLOPT_RETURNTRANSFER => true, CURLOPT_CUSTOMREQUEST => $method,
                CURLOPT_HTTPHEADER => $headers, CURLOPT_FOLLOWLOCATION => false,
                // Bound the read-only page authentication check; retain write timeouts.
                CURLOPT_CONNECTTIMEOUT => $method === 'GET' && $path === '/auth/v1/user' ? 3 : 8,
                CURLOPT_TIMEOUT => $method === 'GET' && $path === '/auth/v1/user' ? 5 : 20,
                CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            ]);
            if ($body !== null) curl_setopt($curl, CURLOPT_POSTFIELDS, $body);
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
            // Only allow known machine codes, never server diagnostics or personal data.
            $code = is_array($decoded) ? ($decoded['error_code'] ?? $decoded['code'] ?? '') : '';
            $reason = in_array($code, ['invalid_credentials','email_not_confirmed','refresh_token_not_found','refresh_token_already_used'], true) ? $code : '';
            throw new SupabaseRequestException($status, $reason);
        }
        return $decoded;
    }
}
