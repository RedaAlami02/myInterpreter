<?php
/** Display estimates only; stored trades and holding cost snapshots are untouched. */
function portfolio_trade_time(string $value): int
{
    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})(?:T| )/', $value, $m)
        || !checkdate((int)$m[2], (int)$m[3], (int)$m[1])
        || !preg_match('/(?:Z|[+-]\d{2}:\d{2})$/D', $value)) {
        throw new InvalidArgumentException('Trade timestamp requires a valid date and timezone.');
    }
    $stamp = new DateTimeImmutable($value);
    return (int)$stamp->format('U') * 1000000 + (int)$stamp->format('u');
}

function portfolio_positive($value): float
{
    if (is_bool($value) || !is_numeric($value) || !is_finite((float)$value) || (float)$value <= 0) {
        throw new InvalidArgumentException('Invalid trade amount.');
    }
    return (float)$value;
}

/** One company's FIFO matches, retaining errors rather than inventing opening trades. */
function portfolio_fifo(array $buys, array $sells): array
{
    $lots = []; $sales = [];
    foreach ($buys as $i => $b) {
        $lots[] = ['source' => $b, 'time' => portfolio_trade_time($b['DATE']),
            'id' => (string)($b['ID'] ?? $i), 'left' => portfolio_positive($b['NUMBER']),
            'price' => portfolio_positive($b['PRIX_ACHAT'])];
    }
    foreach ($sells as $i => $s) {
        $sales[] = ['source' => $s, 'time' => portfolio_trade_time($s['DATE']),
            'id' => (string)($s['ID'] ?? $i), 'qty' => portfolio_positive($s['NUMBER']),
            'price' => portfolio_positive($s['PRIX_VENTE'])];
    }
    $order = static fn(array $a, array $b): int => ($a['time'] <=> $b['time']) ?: strcmp($a['id'], $b['id']);
    usort($lots, $order); usort($sales, $order);
    $rows = []; $epsilon = 1e-9;
    foreach ($sales as $sale) {
        $work = $lots; $pending = []; $left = $sale['qty']; $error = null;
        for ($i = 0; $i < count($work) && $left > $epsilon;) {
            if ($work[$i]['left'] <= $epsilon) { $i++; continue; }
            if ($work[$i]['time'] > $sale['time']) break;
            if ($work[$i]['time'] === $sale['time']) { $error = 'AMBIGUOUS_TRADE_ORDER'; break; }
            $group = []; $total = 0.0; $prices = [];
            $stamp = $work[$i]['time']; $j = $i;
            while ($j < count($work) && $work[$j]['time'] === $stamp) {
                if ($work[$j]['left'] > $epsilon) {
                    $group[] = $j; $total += $work[$j]['left'];
                    $prices[(string)$work[$j]['price']] = true;
                }
                $j++;
            }
            if ($left + $epsilon < $total && count($prices) > 1) { $error = 'AMBIGUOUS_LOT_ORDER'; break; }
            foreach ($group as $index) {
                if ($left <= $epsilon) break;
                $lot = $work[$index]; $quantity = min($left, $lot['left']);
                $buyAmount = $quantity * $lot['price']; $sellAmount = $quantity * $sale['price'];
                $pending[] = ['sale_id' => $sale['id'], 'achat_date' => $lot['source']['DATE'], 'achat_nombre' => $quantity,
                    'achat_prix' => $lot['price'], 'achat_montant' => $buyAmount,
                    'vente_date' => $sale['source']['DATE'], 'vente_nombre' => $quantity,
                    'vente_prix' => $sale['price'], 'vente_montant' => $sellAmount,
                    'duree_days' => (int)floor(($sale['time'] - $lot['time']) / 86400000000),
                    'benefice' => $sellAmount - $buyAmount,
                    'is_split' => $quantity + $epsilon < (float)$lot['source']['NUMBER']];
                $work[$index]['left'] -= $quantity; $left -= $quantity;
            }
            $i = $j;
        }
        if ($error !== null || $left > $epsilon) {
            $rows[] = ['sale_id' => $sale['id'], 'error' => $error ?? 'INCOMPLETE_BUY_HISTORY', 'vente_date' => $sale['source']['DATE']];
            // Do not let an unresolved sale leave its possibly consumed lots available.
            // Later realization cannot be established without resolving the history.
            foreach ($sales as $later) {
                if ($order($later, $sale) > 0) $rows[] = ['sale_id' => $later['id'], 'error' => 'PRIOR_SALE_UNRESOLVED', 'vente_date' => $later['source']['DATE']];
            }
            break;
        }
        $lots = $work; array_push($rows, ...$pending);
    }
    return $rows;
}

function portfolio_realized_totals(array $rows, float $commissionRate, float $taxRate): array
{
    $gross = 0.0; $fees = 0.0; $unresolved = 0;
    foreach ($rows as $row) {
        if (isset($row['error'])) { $unresolved++; continue; }
        $gross += $row['benefice'];
        $fees += ($row['achat_montant'] + $row['vente_montant']) * $commissionRate;
    }
    $tax = max(0.0, $gross) * $taxRate;
    return ['gross' => $gross, 'fees' => $fees, 'tax' => $tax,
        'net' => $gross - $fees - $tax, 'unresolved_sales' => $unresolved];
}
