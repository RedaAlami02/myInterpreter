<?php
/** Recorded-price estimates only. These records never authorize a saved valuation. */
function portfolio_recorded_prices(array $records, ?DateTimeImmutable $now = null): array
{
    $now ??= new DateTimeImmutable('now', new DateTimeZone('UTC'));
    $result = [];
    foreach ($records as $record) {
        $name = $record['c_name'] ?? null;
        if (!is_string($name) || $name === '') continue;
        if (isset($result[$name])) {
            $result[$name] = ['price' => null, 'day' => null, 'status' => 'CONFLICT'];
            continue;
        }
        $entry = ['price' => null, 'day' => null, 'status' => 'UNAVAILABLE'];
        $price = $record['pa'] ?? null;
        $numeric = is_int($price) || is_float($price)
            || (is_string($price) && preg_match('/^\d+(?:\.\d+)?$/D', $price));
        if (!$numeric || !is_finite((float)$price) || $price <= 0 || $price > 1000000000000) {
            $result[$name] = $entry; continue;
        }
        $date = $record['date'] ?? null;
        if (!is_string($date) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|([+-])(\d{2}):(\d{2}))$/D', $date, $parts)
            || !checkdate((int)$parts[2], (int)$parts[3], (int)$parts[1])
            || (int)$parts[4] > 23 || (int)$parts[5] > 59 || (int)$parts[6] > 59
            || (isset($parts[9]) && ((int)$parts[9] > 23 || (int)$parts[10] > 59))) {
            $entry['status'] = 'UNKNOWN_DATE'; $result[$name] = $entry; continue;
        }
        try { $stamp = new DateTimeImmutable($date); }
        catch (Throwable $error) { $result[$name] = $entry; continue; }
        if ($stamp > $now) {
            $entry['status'] = 'FUTURE_DATE'; $result[$name] = $entry; continue;
        }
        // Date here is a recorded timestamp, not an asserted trade/session date.
        $result[$name] = ['price' => (float)$price,
            'day' => $stamp->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d'),
            'status' => 'RECORDED_REFERENCE'];
    }
    return $result;
}

/**
 * Latest recorded close per company. A company that did not trade today keeps
 * its previous close — that is its market value — so a single suspended or
 * untraded line must not blank the whole portfolio. The oldest close used is
 * reported as `day`, the newest as `day_latest`, and the page discloses both.
 */
function portfolio_reference_totals(array $holdings, array $prices, bool $holdingsComplete = true): array
{
    $invested = 0.0; $value = 0.0; $covered = 0; $days = []; $valid = true;
    foreach ($holdings as $holding) {
        $qty = $holding['quantity'] ?? null; $cost = $holding['total_cost'] ?? null;
        if (!is_numeric($qty) || !is_numeric($cost) || !is_finite((float)$qty)
            || !is_finite((float)$cost) || $qty <= 0 || $cost < 0) { $valid = false; continue; }
        $invested += (float)$cost;
        $quote = $prices[$holding['c_name'] ?? ''] ?? null;
        if ($quote === null || $quote['price'] === null) continue;
        $value += $qty * $quote['price']; $covered++;
        if (is_string($quote['day'] ?? null)) $days[$quote['day']] = true;
    }
    $complete = $holdingsComplete && $valid && count($holdings) > 0
        && $covered === count($holdings)
        && is_finite($value) && is_finite($invested);
    $sorted = array_keys($days);
    sort($sorted);
    return ['invested' => $valid && $holdingsComplete ? $invested : null,
        'value' => $complete ? $value : null, 'pnl' => $complete ? $value - $invested : null,
        'day' => $complete && $sorted ? $sorted[0] : null,
        'day_latest' => $complete && $sorted ? end($sorted) : null,
        'covered' => $covered,
        'positions' => count($holdings), 'complete' => $complete,
        'portfolio_valuation_eligible' => false];
}
