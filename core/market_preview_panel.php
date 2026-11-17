<?php
require_once __DIR__ . '/ShadowMarketFeed.php';

/** Read-only presentation shared by the existing dashboard and selection pages. */
function render_market_preview(?ShadowMarketSnapshot $snapshot, ?DateTimeImmutable $asOf = null): void
{
    $asOf ??= new DateTimeImmutable('now');
    $views = [];
    foreach ($snapshot?->applicationRowsAt($asOf) ?? [] as $view) $views[$view['asset_key']] = $view;
    $rows = $snapshot?->rowsAt($asOf) ?? [];
    $unavailable = $snapshot === null || $snapshot->status !== 'AVAILABLE';
    $recordedRows = [];
    if (!$views && function_exists('sb_market')) {
        try {
            $recordedRows = sb_market()->listDocuments('latest_prices', [
                json_encode(['method'=>'limit','values'=>[500]])]);
        } catch (Throwable $error) { /* Existing unavailable state stays usable. */ }
    }

    ?>
    <link rel="stylesheet" href="assets/css/market_preview.css?v=1">
    <section class="market-preview" aria-labelledby="market-preview-heading">
      <div class="market-preview-head">
        <div><h2 id="market-preview-heading"><?= te('Aperçu du marché') ?></h2>
          <p><?= te('Consultez la nature du prix et sa date avant de le comparer.') ?></p></div>
        <button type="button" class="btn btn-ghost" data-market-refresh><?= te('Actualiser') ?></button>
      </div>
      <?php if (!$views && $recordedRows): ?>
        <?php require_once __DIR__ . '/recorded_market_panel.php';
          if (!render_recorded_market_panel($recordedRows, $asOf)): ?>
          <p role="status"><?= te('Aucun prix enregistré utilisable.') ?></p>
        <?php endif; ?>
      <?php elseif ($unavailable || !$rows): ?>
        <p class="market-preview-empty" role="status"><?= te('Les cours récents sont indisponibles. Réessayez plus tard.') ?></p>
      <?php else: ?>
        <p class="market-preview-note"><?= te('Les prix de référence ne confirment pas une transaction récente.') ?></p>
        <label class="market-preview-search"><?= te('Chercher une société…') ?>
          <input type="search" data-market-search autocomplete="off" placeholder="<?= te('Société ou symbole') ?>"></label>
        <div class="market-preview-grid">
        <?php foreach ($rows as $quote):
            $view = $views[$quote['asset_key']] ?? null;
            $fields = $view['fields'] ?? [];
            $reference = ($view['price_basis'] ?? null) === 'INSTRUMENT_REFERENCE';
            $priceLabel = !$view ? 'Prix indisponible' : ($reference ? 'Prix de référence' : 'Cours annoncé');
            ?>
          <article class="market-preview-card<?= !$view ? ' is-unavailable' : '' ?>"
              data-market-card data-market-name="<?= htmlspecialchars($quote['c_name'].' '.$quote['symbol'], ENT_QUOTES, 'UTF-8') ?>"
              data-market-captured="<?= htmlspecialchars($view['captured_at'] ?? '', ENT_QUOTES, 'UTF-8') ?>"
              data-market-expiry="<?= htmlspecialchars($view['expires_at'] ?? '', ENT_QUOTES, 'UTF-8') ?>"
              data-market-expired-label="<?= te('Prix expiré — actualisez') ?>">
            <div class="market-preview-card-head">
              <?php if ($quote['instrument_type'] === 'INDEX'): ?>
                <strong><?= htmlspecialchars($quote['c_name'], ENT_QUOTES, 'UTF-8') ?></strong>
              <?php else: ?>
                <a href="infoAction.php?name=<?= urlencode($quote['c_name']) ?>"><?= htmlspecialchars($quote['c_name'], ENT_QUOTES, 'UTF-8') ?></a>
                <span><?= htmlspecialchars($quote['symbol'], ENT_QUOTES, 'UTF-8') ?></span>
              <?php endif; ?>
            </div>
            <div class="market-preview-price"><span data-market-value><?= $view ? number_format((float)$fields['pa'], 2, ',', ' ') : '—' ?></span> <?= $quote['instrument_type'] === 'INDEX' ? te('points') : 'MAD' ?></div>
            <p class="market-preview-basis" data-market-state><?= te($priceLabel) ?></p>
            <?php if ($view): ?>
              <p class="market-preview-date">
                <?php if ($reference): ?><?= te('Date de cotation inconnue.') ?>
                <?php elseif ($view['source_event_at'] !== null): ?><?= te('Coté le {date}', ['date'=>fmt_datetime($view['source_event_at'])]) ?>
                <?php elseif ($view['reported_day'] !== null): ?><?= te('Date annoncée : {date} — heure inconnue', ['date'=>fmt_date($view['reported_day'])]) ?>
                <?php else: ?><?= te('Date de cotation inconnue.') ?><?php endif; ?>
                <br><?= te('Reçu le {date}', ['date'=>fmt_datetime($view['captured_at'])]) ?>
              </p>
            <?php endif; ?>
            <?php if ($quote['instrument_type'] === 'STOCK'): ?>
              <div class="market-preview-ratios">
              <?php foreach (['per'=>'PER','peg'=>'PEG','pr'=>'P/R','pb'=>'P/B'] as $key=>$label):
                  $value = $fields[$key] ?? null;
                  $rating = $value !== null && $value > 0 ? ($fields[$key.'_rating'] ?? 'none') : 'none'; ?>
                <span class="market-preview-ratio <?= htmlspecialchars($rating, ENT_QUOTES, 'UTF-8') ?>"><?= $label ?>
                  <strong data-market-value><?= $value !== null && $value > 0 ? number_format((float)$value, 2, ',', ' ') : '—' ?></strong></span>
              <?php endforeach; ?>
              </div>
            <?php endif; ?>
          </article>
        <?php endforeach; ?>
        </div>
        <p hidden data-market-no-results role="status"><?= te('Aucune société ne correspond à votre recherche.') ?></p>
      <?php endif; ?>
    </section>
    <script src="assets/js/market_preview.js?v=1" defer></script>
    <?php
}
