<?php
/** Pinned sanitized history only. No credentials, network calls or original-price substitution. */
final class RecoveredHistoryReader
{
    private string $directory;
    private array $manifest;
    private array $instruments = [];
    private const CONTRACT = 'daily-close-preview-v1';

    public function __construct(string $directory, string $manifestSha256)
    {
        $real = realpath($directory);
        if (!$real || !is_dir($real) || !preg_match('/^[a-f0-9]{64}$/D', $manifestSha256)) {
            throw new RuntimeException('Historical preview is unavailable.');
        }
        $this->directory = $real;
        $manifest = $this->readPinned('manifest.json', $manifestSha256, 200000);
        self::keys($manifest, ['contract', 'version', 'generated_at', 'classification', 'not_live', 'original_observation_times', 'instruments']);
        self::header($manifest);
        if (!is_string($manifest['generated_at']) || !is_array($manifest['instruments'])
            || !array_is_list($manifest['instruments']) || count($manifest['instruments']) < 1
            || count($manifest['instruments']) > 1000) self::invalid();
        foreach ($manifest['instruments'] as $item) {
            if (!is_array($item)) self::invalid();
            self::keys($item, ['symbol', 'kind', 'file', 'sha256', 'observation_count', 'first_date', 'last_date', 'duplicate_days', 'conflicting_days']);
            $symbol = $item['symbol'];
            if (!is_string($symbol) || !preg_match('/^[A-Z0-9]{1,12}$/D', $symbol)
                || isset($this->instruments[$symbol]) || !in_array($item['kind'], ['INDEX', 'SECURITY'], true)
                || !is_string($item['file']) || !preg_match('/^s_[a-f0-9]{16}\.json$/D', $item['file'])
                || !is_string($item['sha256']) || !preg_match('/^[a-f0-9]{64}$/D', $item['sha256'])) self::invalid();
            foreach (['observation_count', 'duplicate_days', 'conflicting_days'] as $field) {
                if (!is_int($item[$field]) || $item[$field] < 0) self::invalid();
            }
            if (!self::validDate($item['first_date']) || !self::validDate($item['last_date'])
                || $item['first_date'] > $item['last_date']) self::invalid();
            $this->instruments[$symbol] = $item;
        }
        $this->manifest = $manifest;
    }

    public function instruments(): array
    {
        return array_map(static function (array $item): array {
            unset($item['file'], $item['sha256']);
            return $item;
        }, array_values($this->instruments));
    }

    public function series(string $symbol, ?string $from = null, ?string $through = null): array
    {
        if (!isset($this->instruments[$symbol])) throw new InvalidArgumentException('Unknown historical instrument.');
        if (($from !== null && !self::validDate($from)) || ($through !== null && !self::validDate($through))
            || ($from !== null && $through !== null && $from > $through)) {
            throw new InvalidArgumentException('Invalid historical date range.');
        }
        $item = $this->instruments[$symbol];
        $series = $this->readPinned($item['file'], $item['sha256'], 8000000);
        self::keys($series, ['contract', 'version', 'symbol', 'kind', 'classification', 'price_definition', 'not_live',
            'original_observation_times', 'captured_at', 'first_date', 'last_date', 'observation_count', 'duplicate_days', 'conflicting_days', 'points']);
        self::header($series);
        foreach (['symbol', 'kind', 'first_date', 'last_date', 'observation_count', 'duplicate_days', 'conflicting_days'] as $field) {
            if ($series[$field] !== $item[$field]) self::invalid();
        }
        if ($series['version'] !== $this->manifest['version'] || $series['price_definition'] !== 'DAILY_CLOSE_CANDIDATE'
            || !is_string($series['captured_at']) || !is_array($series['points']) || !array_is_list($series['points'])
            || count($series['points']) < 1 || count($series['points']) > 20000) self::invalid();
        $previous = ''; $ids = []; $count = 0; $duplicates = 0; $conflicts = 0;
        foreach ($series['points'] as $point) {
            if (!is_array($point)) self::invalid();
            self::keys($point, ['date', 'status', 'close_decimal', 'candidates']);
            if (!self::validDate($point['date']) || $point['date'] <= $previous || !is_array($point['candidates'])
                || !array_is_list($point['candidates']) || count($point['candidates']) < 1) self::invalid();
            $previous = $point['date'];
            foreach ($point['candidates'] as $candidate) {
                if (!is_array($candidate)) self::invalid();
                self::keys($candidate, ['observation_id', 'close_decimal', 'quality_warnings']);
                if (!is_string($candidate['observation_id']) || !preg_match('/^[a-f0-9]{64}$/D', $candidate['observation_id'])
                    || isset($ids[$candidate['observation_id']]) || !self::validClose($candidate['close_decimal'])
                    || !is_array($candidate['quality_warnings']) || !array_is_list($candidate['quality_warnings'])) self::invalid();
                foreach ($candidate['quality_warnings'] as $warning) {
                    if (!in_array($warning, ['SOURCE_OHLC_INCONSISTENT', 'SOURCE_OHLC_UNAVAILABLE'], true)) self::invalid();
                }
                $ids[$candidate['observation_id']] = true;
                $count++;
            }
            if (count($point['candidates']) === 1) {
                if ($point['status'] !== 'AVAILABLE' || $point['close_decimal'] !== $point['candidates'][0]['close_decimal']) self::invalid();
            } else {
                if (!in_array($point['status'], ['CONFLICTING_CLOSES', 'DUPLICATE_OBSERVATIONS'], true)
                    || $point['close_decimal'] !== null) self::invalid();
                $duplicates++;
                if ($point['status'] === 'CONFLICTING_CLOSES') $conflicts++;
            }
        }
        if ($series['points'][0]['date'] !== $series['first_date'] || $previous !== $series['last_date']
            || $count !== $series['observation_count'] || $duplicates !== $series['duplicate_days']
            || $conflicts !== $series['conflicting_days']) self::invalid();
        $series['points'] = array_values(array_filter($series['points'], static fn(array $point): bool =>
            ($from === null || $point['date'] >= $from) && ($through === null || $point['date'] <= $through)));
        $series['requested_from'] = $from;
        $series['requested_through'] = $through;
        $series['range_status'] = $series['points'] ? 'HISTORICAL_POINTS_AVAILABLE' : 'NO_HISTORICAL_POINTS_IN_RANGE';
        return $series;
    }

    private function readPinned(string $filename, string $expected, int $maximum): array
    {
        $path = realpath($this->directory . '/' . $filename);
        if (!$path || dirname($path) !== $this->directory || !is_file($path)) self::invalid();
        $raw = @file_get_contents($path, false, null, 0, $maximum + 1);
        if ($raw === false || strlen($raw) > $maximum || !hash_equals($expected, hash('sha256', $raw))) self::invalid();
        $decoded = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($decoded) || array_is_list($decoded)) self::invalid();
        return $decoded;
    }

    private static function keys(array $value, array $expected): void
    {
        $actual = array_keys($value); sort($actual); sort($expected);
        if ($actual !== $expected) self::invalid();
    }

    private static function header(array $value): void
    {
        if ($value['contract'] !== self::CONTRACT || $value['classification'] !== 'RETROSPECTIVE_SOURCE_HISTORY'
            || $value['not_live'] !== true || $value['original_observation_times'] !== 'UNKNOWN'
            || !is_string($value['version']) || !preg_match('/^[a-f0-9]{64}$/D', $value['version'])) self::invalid();
    }

    private static function validDate($value): bool
    {
        if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}$/D', $value)) return false;
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        return $date !== false && $date->format('Y-m-d') === $value;
    }

    private static function validClose($value): bool
    {
        return is_string($value) && preg_match('/^(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/D', $value)
            && is_numeric($value) && is_finite((float)$value) && (float)$value > 0;
    }

    private static function invalid(): never
    {
        throw new RuntimeException('Historical preview integrity check failed.');
    }
}

function recovered_history_reader(): RecoveredHistoryReader
{
    $directory = getenv('MYINTERPRETER_HISTORY_PREVIEW_DIR');
    $pin = getenv('MYINTERPRETER_HISTORY_PREVIEW_SHA256');
    if (!$directory || !$pin) throw new RuntimeException('Historical preview is unavailable.');
    return new RecoveredHistoryReader($directory, $pin);
}
