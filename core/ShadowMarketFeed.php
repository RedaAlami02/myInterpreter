<?php
/** Separate preview contract. No legacy document conversion or portfolio writes. */
final class ShadowMarketSnapshot
{
    private array $rows;
    public readonly string $status;

    private static function validPrice($value): bool
    {
        if (!is_string($value) || !preg_match('/^[0-9]{1,13}(?:\.[0-9]{1,28})?$/D', $value)
            || str_replace(['0','.'], '', $value) === '') return false;
        [$integer, $fraction] = array_pad(explode('.', $value, 2), 2, '');
        $integer = ltrim($integer, '0') ?: '0';
        if (strlen($integer) > 13 || (strlen($integer) === 13 && strcmp($integer, '1000000000000') > 0)) return false;
        return $integer !== '1000000000000' || trim($fraction, '0') === '';
    }

    public static function timestamp($value): ?DateTimeImmutable
    {
        if ($value === null) return null;
        if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/D', $value)) {
            throw new RuntimeException('Invalid preview timestamp.');
        }
        try { $stamp = new DateTimeImmutable($value); }
        catch (Throwable $error) { throw new RuntimeException('Invalid preview timestamp.'); }
        if ($stamp->format('Y-m-d\TH:i:s') !== substr($value, 0, 19)) throw new RuntimeException('Invalid preview timestamp.');
        return $stamp;
    }

    public function __construct(array $payload)
    {
        if (!in_array($payload['contract'] ?? null, ['app-market-preview/v1','app-market-preview/v2','app-market-preview/v3'], true) || ($payload['mode'] ?? null) !== 'SHADOW_ONLY'
            || !in_array($payload['status'] ?? null, ['AVAILABLE','DISABLED','WAITING','SOURCE_DISABLED','EVIDENCE_UNAVAILABLE'], true)
            || !is_array($payload['rows'] ?? null) || !array_is_list($payload['rows']) || count($payload['rows']) > 2048
            || self::timestamp($payload['as_of'] ?? null) === null
            || ($payload['status'] !== 'AVAILABLE' && $payload['rows'] !== [])) {
            throw new RuntimeException('Invalid preview feed.');
        }
        $this->status = $payload['status'];
        $this->rows = [];
        $seen = [];
        foreach ($payload['rows'] as $row) {
            if (!is_array($row) || !is_string($row['asset_key'] ?? null) || isset($seen[$row['asset_key']])
                || !is_string($row['c_name'] ?? null) || !is_string($row['symbol'] ?? null)
                || !in_array($row['instrument_type'] ?? null, ['STOCK','INDEX'], true)
                || !in_array($row['status'] ?? null, ['MISSING_QUOTE','CONFLICTING_QUOTES','STALE_OR_MISSING_SOURCE_DATE','STALE_CAPTURE_DATE','STALE_CAPTURE','STALE_SOURCE_EVENT','FUTURE_CAPTURE','REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED'], true)
                || ($row['price_basis'] ?? null) !== 'REPORTED_QUOTE'
                || ($row['prediction_eligible'] ?? null) !== false || ($row['portfolio_valuation_eligible'] ?? null) !== false
                || ($row['reported_time_timezone'] ?? null) !== 'UNKNOWN') throw new RuntimeException('Invalid preview row.');
            $seen[$row['asset_key']] = true;
            $capture = self::timestamp($row['captured_at'] ?? null);
            $expiry = self::timestamp($row['expires_at'] ?? null);
            $price = $row['price_decimal'] ?? null;
            $current = in_array($row['status'], ['REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED'], true);
            if ($current) {
                if (!self::validPrice($price)
                    || !$capture || !$expiry || $expiry <= $capture || $expiry > $capture->modify('+3600 seconds')) {
                    throw new RuntimeException('Invalid preview price.');
                }
            } elseif ($price !== null || $expiry !== null) throw new RuntimeException('Unavailable preview price.');
            // Build an allowlisted copy; private/unknown backend properties never escape.
            $safe = array_intersect_key($row, array_flip(['asset_key','company_id','c_name','symbol','instrument_type','status','price_decimal','captured_at','expires_at','reported_time_text','reported_day','reported_time_timezone','source_event_at','price_basis','prediction_eligible','portfolio_valuation_eligible']));
            $referenceCapture = $referenceExpiry = null;
            if (in_array($payload['contract'], ['app-market-preview/v2','app-market-preview/v3'], true)) {
                if (!array_key_exists('reference_price', $row)) throw new RuntimeException('Missing reference-price field.');
                if (!is_bool($row['reference_conflict'] ?? null)
                    || ($row['reference_conflict'] && ($row['status'] !== 'MISSING_QUOTE'
                        || $row['instrument_type'] !== 'STOCK' || $row['reference_price'] !== null))) {
                    throw new RuntimeException('Invalid reference conflict flag.');
                }
                $safe['reference_conflict'] = $row['reference_conflict'];
                $safe['reference_price'] = null;
                if ($row['reference_price'] !== null) {
                    $ref = $row['reference_price'];
                    if (!is_array($ref) || $row['status'] !== 'MISSING_QUOTE' || $row['instrument_type'] !== 'STOCK'
                        || !self::validPrice($ref['price_decimal'] ?? null) || ($ref['price_basis'] ?? null) !== 'INSTRUMENT_REFERENCE'
                        || !array_key_exists('source_event_at', $ref) || $ref['source_event_at'] !== null
                        || !array_key_exists('reported_day', $ref) || $ref['reported_day'] !== null
                        || ($ref['reported_time_timezone'] ?? null) !== 'UNKNOWN'
                        || ($ref['prediction_eligible'] ?? null) !== false || ($ref['portfolio_valuation_eligible'] ?? null) !== false) {
                        throw new RuntimeException('Invalid reference price.');
                    }
                    $referenceCapture = self::timestamp($ref['captured_at'] ?? null);
                    $referenceExpiry = self::timestamp($ref['expires_at'] ?? null);
                    $feedCapture = self::timestamp($payload['captured_at'] ?? null);
                    if (!$referenceCapture || !$referenceExpiry || !$feedCapture || $referenceCapture != $feedCapture
                        || $referenceExpiry <= $referenceCapture || $referenceExpiry > $referenceCapture->modify('+3600 seconds')) {
                        throw new RuntimeException('Invalid reference-price lifetime.');
                    }
                    $safe['reference_price'] = array_intersect_key($ref, array_flip(['price_decimal','price_basis','captured_at','expires_at','source_event_at','reported_day','reported_time_timezone','prediction_eligible','portfolio_valuation_eligible']));
                }
            }
            $applicationExpiry = null;
            if ($payload['contract'] === 'app-market-preview/v3') {
                if (!array_key_exists('application_fields', $row) || !array_key_exists('application_expires_at', $row)) {
                    throw new RuntimeException('Missing application display fields.');
                }
                $safe['application_fields'] = null;
                $safe['application_expires_at'] = $row['application_expires_at'];
                $applicationExpiry = self::timestamp($row['application_expires_at']);
                if ($row['application_fields'] === null) {
                    if ($applicationExpiry !== null) throw new RuntimeException('Unavailable application expiry.');
                } else {
                    $f = $row['application_fields'];
                    $chosenPrice = $price ?? ($safe['reference_price']['price_decimal'] ?? null);
                    $chosenCapture = $price !== null ? $capture : $referenceCapture;
                    $chosenExpiry = $price !== null ? $expiry : $referenceExpiry;
                    self::timestamp($row['source_event_at'] ?? null);
                    $reportedDay = $row['reported_day'] ?? null;
                    if ($reportedDay !== null && (!is_string($reportedDay)
                        || !preg_match('/^\d{4}-\d{2}-\d{2}$/D', $reportedDay))) {
                        throw new RuntimeException('Invalid application reported date.');
                    }
                    if ($reportedDay !== null) self::timestamp($reportedDay . 'T00:00:00Z');
                    if (!is_array($f) || !$chosenPrice || !$chosenCapture || !$applicationExpiry || !$chosenExpiry
                        || $applicationExpiry <= $chosenCapture || $applicationExpiry > $chosenExpiry
                        || ($f['c_name'] ?? null) !== $row['c_name']
                        || self::timestamp($f['date'] ?? null) != $chosenCapture
                        || is_bool($f['pa'] ?? null) || !is_numeric($f['pa'] ?? null)
                        || !is_finite((float)$f['pa']) || (float)$f['pa'] !== (float)$chosenPrice
                        || ($row['instrument_type'] === 'STOCK' && ($f['symbol'] ?? null) !== $row['symbol'])) {
                        throw new RuntimeException('Invalid application display row.');
                    }
                    $allowed = ['date','c_name','symbol','pa','cb','pb','per','peg','pr','per_rating','pb_rating',
                        'peg_rating','pr_rating','variation','variation_v','cours_ref','open_price','high','low',
                        'volume','qty_traded','market_cap','data_chart'];
                    $f = array_intersect_key($f, array_flip($allowed));
                    foreach ($f as $key => $value) {
                        if ($row['instrument_type'] === 'INDEX' && in_array($key,
                            ['symbol','cb','pb','per','peg','pr','per_rating','pb_rating','peg_rating','pr_rating'], true)) {
                            throw new RuntimeException('Invalid index application field.');
                        }
                        if (in_array($key, ['date','c_name','symbol'], true)) continue;
                        if ($key === 'data_chart') {
                            if (!is_string($value) || strlen($value) > 195) throw new RuntimeException('Invalid application chart.');
                        } elseif (str_ends_with($key, '_rating')) {
                            if (!in_array($value, ['green','orange','red'], true)) throw new RuntimeException('Invalid application rating.');
                        } elseif ((!is_int($value) && !is_float($value)) || !is_finite((float)$value) || abs($value) > 1e30
                            || ($key === 'qty_traded' && (!is_int($value) || $value < 0))) {
                            throw new RuntimeException('Invalid application number.');
                        }
                    }
                    $safe['application_fields'] = $f;
                }
            }
            $this->rows[] = ['data' => $safe, 'capture' => $capture, 'expiry' => $expiry,
                'referenceCapture' => $referenceCapture, 'referenceExpiry' => $referenceExpiry,
                'applicationExpiry' => $applicationExpiry];
        }
    }

    public function rowsAt(?DateTimeImmutable $asOf = null): array
    {
        $asOf ??= new DateTimeImmutable('now');
        $rows = [];
        foreach ($this->rows as $record) {
            $row = $record['data'];
            if (($row['price_decimal'] ?? null) !== null && ($asOf < $record['capture'] || $asOf >= $record['expiry'])) {
                $row['price_decimal'] = null;
                $row['status'] = $asOf < $record['capture'] ? 'FUTURE_CAPTURE' : 'STALE_CAPTURE';
            }
            if (($row['reference_price'] ?? null) !== null
                && ($asOf < $record['referenceCapture'] || $asOf >= $record['referenceExpiry'])) {
                $row['reference_price'] = null;
            }
            if (($row['application_fields'] ?? null) !== null
                && (($row['price_decimal'] === null && ($row['reference_price'] ?? null) === null)
                    || $asOf >= $record['applicationExpiry'])) {
                $row['application_fields'] = null;
            }
            $rows[] = $row;
        }
        return $rows;
    }

    /** Explicit current display output; never a historical/valuation document. */
    public function applicationRowsAt(?DateTimeImmutable $asOf = null): array
    {
        $output = [];
        foreach ($this->rowsAt($asOf) as $row) {
            if (($row['application_fields'] ?? null) === null) continue;
            $reference = ($row['price_decimal'] ?? null) === null;
            $output[] = ['asset_key' => $row['asset_key'], 'fields' => $row['application_fields'],
                'price_decimal' => $reference ? $row['reference_price']['price_decimal'] : $row['price_decimal'],
                'price_basis' => $reference ? 'INSTRUMENT_REFERENCE' : 'REPORTED_QUOTE',
                'captured_at' => $reference ? $row['reference_price']['captured_at'] : $row['captured_at'],
                'expires_at' => $row['application_expires_at'],
                'source_event_at' => $reference ? null : ($row['source_event_at'] ?? null),
                'reported_day' => $reference ? null : ($row['reported_day'] ?? null),
                'prediction_eligible' => false, 'portfolio_valuation_eligible' => false];
        }
        return $output;
    }

    /** Display only: never convert this into portfolio price/valuation records. */
    public function displayRowsAt(?DateTimeImmutable $asOf = null, array $lastKnown = []): array
    {
        $asOf ??= new DateTimeImmutable('now');
        return array_map(static function (array $row) use ($asOf, $lastKnown): array {
            $row['display_price_decimal'] = $row['price_decimal'] ?? $row['reference_price']['price_decimal'] ?? null;
            $row['display_price_basis'] = ($row['price_decimal'] ?? null) !== null ? 'REPORTED_QUOTE'
                : ($row['reference_price']['price_basis'] ?? (($row['reference_conflict'] ?? false) ? 'CONFLICTING_INSTRUMENT_PRICES' : 'UNAVAILABLE'));
            if ($row['display_price_decimal'] === null && $row['status'] === 'MISSING_QUOTE'
                && $row['instrument_type'] === 'STOCK' && !($row['reference_conflict'] ?? false)) {
                $best = null; $conflict = false;
                foreach ($lastKnown as $record) {
                    if (($record['c_name'] ?? null) !== $row['c_name']
                        || (!empty($record['symbol']) && $record['symbol'] !== $row['symbol'])
                        || !is_string($record['id'] ?? $record['$id'] ?? null)
                        || ($record['id'] ?? $record['$id']) === '') continue;
                    $price = $record['pa'] ?? null;
                    if (is_bool($price) || (!is_string($price) && !is_int($price) && !is_float($price))
                        || !self::validPrice((string)$price)) continue;
                    try { $recorded = self::timestamp($record['date'] ?? null); }
                    catch (RuntimeException $error) { continue; }
                    if (!$recorded || $recorded > $asOf) continue;
                    [$whole,$fraction] = array_pad(explode('.', (string)$price, 2), 2, '');
                    $normalized = (ltrim($whole,'0') ?: '0') . (rtrim($fraction,'0') !== '' ? '.'.rtrim($fraction,'0') : '');
                    if ($best === null || $recorded > $best['recorded']) {
                        $best = ['price'=>(string)$price,'normalized'=>$normalized,'recorded'=>$recorded]; $conflict = false;
                    } elseif ($recorded == $best['recorded'] && $normalized !== $best['normalized']) $conflict = true;
                }
                if ($best !== null && !$conflict) {
                    $row['display_price_decimal'] = $best['price'];
                    $row['display_price_basis'] = 'RECOVERED_LAST_KNOWN';
                    $row['display_recorded_at'] = $best['recorded']->format('c');
                } elseif ($conflict) $row['display_price_basis'] = 'CONFLICTING_SAVED_PRICES';
            }
            return $row;
        }, $this->rowsAt($asOf));
    }
}

final class ShadowMarketFeedReader
{
    public function __construct(private string $url, private string $key, private ?string $token, private mixed $transport = null,
        private bool $applicationRows = false, private bool $recurring = false)
    {
        if (!preg_match('~^https://[a-z0-9]{10,40}\.supabase\.co$~D', $url)
            || !preg_match('/^sb_publishable_[A-Za-z0-9_-]+$/D', $key)
            || ($token !== null && !preg_match('/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/D', $token))) {
            throw new InvalidArgumentException('Invalid public preview configuration.');
        }
    }

    public function read(): ShadowMarketSnapshot
    {
        if ($this->token === null) throw new RuntimeException('Please sign in to view market data.');
        try { return $this->readAuthorized(); }
        catch (Throwable $error) { throw new RuntimeException('Market preview is temporarily unavailable.'); }
    }

    private function readAuthorized(): ShadowMarketSnapshot
    {
        $headers = ['apikey: '.$this->key, 'Authorization: Bearer '.$this->token, 'Content-Type: application/json'];
        $url = $this->url . '/rest/v1/rpc/' . ($this->applicationRows ? 'read_shadow_application_feed' : 'read_shadow_market_feed') . ($this->recurring ? '_recurring_v1' : '');
        if ($this->transport !== null) {
            $response = ($this->transport)($url, $headers, '{}');
        } else {
            $body = '';
            $curl = curl_init($url);
            curl_setopt_array($curl, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => '{}', CURLOPT_HTTPHEADER => $headers,
                CURLOPT_FOLLOWLOCATION => false, CURLOPT_TIMEOUT => 20, CURLOPT_CONNECTTIMEOUT => 8,
                CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
                CURLOPT_WRITEFUNCTION => static function ($handle, string $part) use (&$body): int {
                    if (strlen($body)+strlen($part) > 2097152) return 0;
                    $body .= $part; return strlen($part);
                }]);
            $ok = curl_exec($curl); $status = curl_getinfo($curl, CURLINFO_HTTP_CODE); curl_close($curl);
            $response = ['status' => $ok === false ? 0 : $status, 'body' => $body];
        }
        if (($response['status'] ?? 0) !== 200 || !is_string($response['body'] ?? null) || strlen($response['body']) > 2097152) {
            throw new RuntimeException('Market preview is temporarily unavailable.');
        }
        try { $data = json_decode($response['body'], true, 64, JSON_THROW_ON_ERROR); }
        catch (Throwable $error) { throw new RuntimeException('Invalid preview feed.'); }
        if (!is_array($data)) throw new RuntimeException('Invalid preview feed.');
        return new ShadowMarketSnapshot($data);
    }
}
