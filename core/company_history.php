<?php
/** Browser projection of recorded daily observations; never official closes. */
function company_history_points(array $document, string $name): array
{
    if (($document['contract'] ?? null) !== 'company-daily-history/v1'
        || ($document['company'] ?? null) !== $name || !is_array($document['rows'] ?? null)
        || !array_is_list($document['rows']) || count($document['rows']) > 10000) {
        throw new RuntimeException('Invalid company history.');
    }
    $points = [];
    $previous = '';
    foreach ($document['rows'] as $row) {
        $day = $row['day'] ?? null;
        $price = $row['price'] ?? null;
        if (!is_string($day) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/D', $day, $parts)
            || !checkdate((int)$parts[2], (int)$parts[3], (int)$parts[1]) || $day <= $previous
            || !is_string($price) || !preg_match('/^[0-9]+(?:\.[0-9]+)?$/D', $price)
            || !is_finite((float)$price) || (float)$price > 1e15) {
            throw new RuntimeException('Invalid company history.');
        }
        $points[] = ['day' => $day, 'price' => (float)$price];
        $previous = $day;
    }
    return ['contract' => 'company-daily-history/v1', 'company' => $name, 'points' => $points];
}
