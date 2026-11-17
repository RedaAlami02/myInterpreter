<?php
require_once __DIR__ . '/portfolio_prices.php';
/** Dated references are distinct from expiring quote/application fields. */
function render_recorded_market_panel(array $records, ?DateTimeImmutable $now = null): bool
{
    $prices = portfolio_recorded_prices($records, $now);
    $prices = array_filter($prices, static fn($p) => $p['price'] !== null && $p['day'] !== null);
    if (!$prices) return false;
    ksort($prices, SORT_NATURAL | SORT_FLAG_CASE);
    ?>
    <p class="market-preview-note"><?= te('Cours récents indisponibles. Prix enregistrés ci-dessous ; ils ne sont pas des cotations en direct.') ?></p>
    <label class="market-preview-search"><?= te('Chercher une société…') ?><input type="search" data-market-search autocomplete="off"></label>
    <div class="market-preview-grid">
    <?php foreach ($prices as $name => $price): ?>
      <article class="market-preview-card" data-market-card data-market-name="<?= htmlspecialchars($name, ENT_QUOTES, 'UTF-8') ?>">
        <div class="market-preview-card-head"><a href="infoAction.php?name=<?= urlencode($name) ?>"><?= htmlspecialchars($name, ENT_QUOTES, 'UTF-8') ?></a></div>
        <div class="market-preview-price"><?= number_format($price['price'], 2, ',', ' ') ?> MAD</div>
        <p><?= te('Prix enregistré') ?> · <?= htmlspecialchars($price['day'], ENT_QUOTES, 'UTF-8') ?> (UTC)</p>
      </article>
    <?php endforeach; ?>
    </div>
    <p hidden data-market-no-results role="status"><?= te('Aucune société ne correspond à votre recherche.') ?></p>
    <?php
    return true;
}
