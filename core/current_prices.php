<?php
/** Current display quotes only. Never a writer or an official-close authority. */
function current_market_prices(ShadowMarketSnapshot $snapshot, ?DateTimeImmutable $now = null): array
{
    $now ??= new DateTimeImmutable('now');
    $day = $now->setTimezone(new DateTimeZone('Africa/Casablanca'))->format('Y-m-d');
    $result = [];
    foreach ($snapshot->applicationRowsAt($now) as $entry) {
        // Unknown-date references remain available in the market panel, but do
        // not silently become a fresh portfolio/detail quote.
        if ($entry['price_basis'] !== 'REPORTED_QUOTE' || $entry['reported_day'] !== $day
            || !str_starts_with($entry['asset_key'], 'company:')) continue;
        $fields = $entry['fields'];
        $name = $fields['c_name'] ?? null;
        if (!is_string($name) || $name === '') throw new RuntimeException('Invalid current quote identity.');
        if (isset($result[$name])) throw new RuntimeException('Conflicting current quote identity.');
        $result[$name] = ['c_name' => $name, 'pa' => $entry['price_decimal'],
            'date' => $entry['captured_at'], 'source' => 'CURRENT_REPORTED_QUOTE',
            'source_reported_day' => $entry['reported_day'],
            'source_event_at' => $entry['source_event_at'],
            'portfolio_valuation_eligible' => false, 'prediction_eligible' => false];
    }
    return $result;
}

function overlay_current_prices(array $recorded, array $current): array
{
    // Remove only the display copies of superseded references. Original SQL
    // history stays untouched, and unmatched dated references retain their dates.
    $output = array_values(array_filter($recorded,
        static fn(array $row): bool => !isset($current[$row['c_name'] ?? ''])));
    return array_merge($output, array_values($current));
}
