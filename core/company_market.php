<?php
/** Display-only market observations. Never implies streaming or official closes. */
function company_market_date($value, ?DateTimeImmutable $now = null): ?DateTimeImmutable
{
    if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$/D', $value)) return null;
    try {
        $date = new DateTimeImmutable($value, new DateTimeZone('Africa/Casablanca'));
        if (DateTimeImmutable::getLastErrors() !== false || $date > ($now ?? new DateTimeImmutable('now'))) return null;
        return $date;
    } catch (Throwable $error) { return null; }
}

function company_market_number($value, bool $integer = false): ?float
{
    if ((!is_string($value) && !is_int($value) && !is_float($value)) || !is_numeric($value)) return null;
    $number = (float)$value;
    return !is_finite($number) || $number <= 0 || $number > 1e15 || ($integer && floor($number) !== $number) ? null : $number;
}

function company_market_quote(string $name, array $candidates, ?DateTimeImmutable $now = null): ?array
{
    $best = null;
    foreach ($candidates as $row) {
        if (($row['c_name'] ?? null) !== $name) continue;
        $price = company_market_number($row['pa'] ?? null);
        $date = company_market_date($row['date'] ?? null, $now);
        if ($price === null || $date === null) continue;
        if ($best === null || $date > $best['observed_at']) {
            $best = ['price' => $price, 'date' => $row['date'], 'observed_at' => $date];
        }
    }
    return $best;
}

function company_market_book(array $row, string $symbol, ?DateTimeImmutable $now = null): ?array
{
    $snapshot = $row['snapshot'] ?? null;
    $date = company_market_date($row['captured_at'] ?? null, $now);
    if (($row['symbol'] ?? null) !== $symbol || !is_array($snapshot)
        || ($snapshot['symbol'] ?? null) !== $symbol || $date === null) return null;
    $book = ['date' => $row['captured_at'], 'observed_at' => $date];
    foreach (['bids', 'asks'] as $side) {
        $levels = $snapshot[$side] ?? null;
        if (!is_array($levels) || !array_is_list($levels) || count($levels) > 50) return null;
        $book[$side] = [];
        foreach ($levels as $level) {
            if (!is_array($level)) return null;
            $price = company_market_number($level['price'] ?? null);
            $quantity = company_market_number($level['quantity'] ?? null, true);
            if ($price === null || $quantity === null) return null;
            $book[$side][] = ['price' => $price, 'quantity' => $quantity];
        }
        usort($book[$side], static fn($a, $b) => $side === 'bids' ? $b['price'] <=> $a['price'] : $a['price'] <=> $b['price']);
        $book[$side] = array_slice($book[$side], 0, 5);
    }
    return $book;
}

function company_market_stamp(DateTimeImmutable $date, bool $dayOnly = false): string
{
    return $date->setTimezone(new DateTimeZone('Africa/Casablanca'))->format($dayOnly ? 'd/m/Y' : 'd/m/Y H:i:s');
}

function render_company_market(?array $quote, ?array $book, ?DateTimeImmutable $now = null): void
{
    $now ??= new DateTimeImmutable('now');
    $today = $now->setTimezone(new DateTimeZone('Africa/Casablanca'))->format('Y-m-d');
    ?>
    <section class="card-glass company-market mb-4" aria-labelledby="companyMarketTitle">
      <h2 id="companyMarketTitle"><?= te('Dernier cours disponible') ?></h2>
      <?php if ($quote): ?>
        <p class="company-market__price mono"><?= number_format($quote['price'], 2, ',', ' ') ?> <span>MAD</span></p>
        <p class="muted"><?= te('Observation du') ?> <?= htmlspecialchars(company_market_stamp($quote['observed_at'], strlen($quote['date']) === 10)) ?>
          · <?= te($quote['observed_at']->setTimezone(new DateTimeZone('Africa/Casablanca'))->format('Y-m-d') === $today ? 'Observé aujourd’hui' : 'Donnée historique') ?></p>
      <?php else: ?><p class="muted"><?= te('Cours indisponible pour le moment.') ?></p><?php endif; ?>
      <p class="muted"><?= te('Dernière observation disponible, sans garantie de temps réel ni de clôture officielle. Heures du Maroc.') ?></p>
      <h3><?= te('Carnet d’ordres') ?></h3>
      <?php if ($book): ?>
        <p class="muted"><?= te('Capture du') ?> <?= htmlspecialchars(company_market_stamp($book['observed_at'])) ?>
          · <?= te('Instantané enregistré, pas un carnet en direct.') ?></p>
        <?php if ($book['observed_at']->setTimezone(new DateTimeZone('Africa/Casablanca'))->format('Y-m-d') !== $today): ?>
          <p class="company-market__notice"><?= te('Carnet historique : ces ordres peuvent ne plus être disponibles.') ?></p>
        <?php endif; ?>
        <div class="overflow-x-auto"><table class="tbl company-market__book">
          <thead><tr><th scope="col" class="num"><?= te('Qté achat') ?></th><th scope="col" class="num"><?= te('Achat (MAD)') ?></th><th scope="col" class="num"><?= te('Vente (MAD)') ?></th><th scope="col" class="num"><?= te('Qté vente') ?></th></tr></thead>
          <tbody><?php for ($i = 0; $i < max(count($book['bids']), count($book['asks'])); $i++): ?>
            <tr><?php foreach ([['bids', 'quantity'], ['bids', 'price'], ['asks', 'price'], ['asks', 'quantity']] as [$side, $field]): ?>
              <td class="num mono"><?= isset($book[$side][$i]) ? number_format($book[$side][$i][$field], $field === 'quantity' ? 0 : 2, ',', ' ') : '—' ?></td>
            <?php endforeach; ?></tr>
          <?php endfor; ?>
          <?php if (!$book['bids'] && !$book['asks']): ?><tr><td colspan="4" class="muted"><?= te('Aucun ordre dans cet instantané.') ?></td></tr><?php endif; ?>
          </tbody></table></div>
      <?php else: ?><p class="muted"><?= te('Carnet d’ordres indisponible pour le moment.') ?></p><?php endif; ?>
    </section>
    <?php
}
