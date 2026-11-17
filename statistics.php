<?php
require_once __DIR__ . '/core/i18n.php';
/**
 * FIFO statistics partial — included by portfolio.php.
 * session_start() and Appwrite are assumed to be active.
 */
require_once 'core/Appwrite.php';

/* ── FIFO matching ───────────────────────────────────────── */
require_once __DIR__ . '/core/portfolio_math.php';
function fifoMatch(array $achats, array $ventes): array
{
    return portfolio_fifo($achats, $ventes);
}

function monofmt(float $n, int $dec = 2): string
{
    return number_format($n, $dec, '.', ' ');
}

// Normalize a backend document to the format fifoMatch expects
function normalizeAchat(array $doc): array {
    return [
        'ID'         => $doc['$id'] ?? $doc['id'] ?? '',
        'DATE'       => $doc['date'] ?? '',
        'C_NAME'     => $doc['c_name'] ?? '',
        'NUMBER'     => $doc['quantity'] ?? $doc['number'] ?? 0,
        'PRIX_ACHAT' => $doc['price'] ?? $doc['prix_achat'] ?? 0,
    ];
}
function normalizeVente(array $doc): array {
    return [
        'ID'         => $doc['$id'] ?? $doc['id'] ?? '',
        'DATE'       => $doc['date'] ?? '',
        'C_NAME'     => $doc['c_name'] ?? '',
        'NUMBER'     => $doc['quantity'] ?? $doc['number'] ?? 0,
        'PRIX_VENTE' => $doc['price'] ?? $doc['prix_vente'] ?? 0,
    ];
}

function stats(): void
{
    $uid     = aw_user_id();
    $session = aw_session();

    // Fetch all achats and ventes for this user
    $transactions = aw_multi_list_docs([
        'buys' => ['achats', [q_equal('user_id', $uid), q_order_asc('date'), q_limit(500)], $session],
        'sells' => ['ventes', [q_equal('user_id', $uid), q_order_asc('date'), q_limit(500)], $session],
    ]);
    $achatDocs = $transactions['buys'];
    $venteDocs = $transactions['sells'];
    $hasDeclaredDays = (bool)array_filter($achatDocs, fn($row) => ($row['purchase_day_basis'] ?? null) === 'USER_CONFIRMED');
    $purchaseSection = '';
    if ($achatDocs) {
        ob_start();
        ?>
        <section class="card-glass mb-4" aria-labelledby="purchaseHistoryTitle">
          <h2 id="purchaseHistoryTitle" style="padding:18px 20px 0;font-size:1rem"><?= te('Achats enregistrés') ?></h2>
          <div class="overflow-x-auto"><table class="tbl">
            <thead><tr><th scope="col"><?= te('Société') ?></th><th scope="col" class="num"><?= te('Actions') ?></th>
              <th scope="col" class="num"><?= te("Prix d'achat") ?></th><th scope="col"><?= te("Date d'achat") ?></th>
              <th scope="col"><?= te('Saisi le') ?></th></tr></thead>
            <tbody><?php foreach (array_reverse($achatDocs) as $purchase):
                $confirmed = ($purchase['purchase_day_basis'] ?? null) === 'USER_CONFIRMED'
                    && is_string($purchase['purchase_day'] ?? null);
            ?><tr>
              <th scope="row"><?= htmlspecialchars($purchase['c_name']) ?></th>
              <td class="num mono"><?= number_format((float)$purchase['number'], 0, ',', ' ') ?></td>
              <td class="num mono"><?= number_format((float)$purchase['prix_achat'], 2, ',', ' ') ?></td>
              <td class="mono"><?= fmt_date($confirmed ? $purchase['purchase_day'] : $purchase['date']) ?>
                <?php if ($confirmed): ?><small class="muted"><?= te('Déclarée') ?></small>
                <?php else: ?><small class="muted"><?= te('Date enregistrée') ?></small><?php endif; ?></td>
              <td class="mono muted"><?= fmt_datetime($purchase['date']) ?></td>
            </tr><?php endforeach; ?></tbody>
          </table></div>
        </section>
        <?php
        $purchaseSection = ob_get_clean();
    }

    // Get distinct stocks that have been sold
    $soldStocks = [];
    foreach ($venteDocs as $v) {
        $n = $v['c_name'] ?? '';
        if ($n && !in_array($n, $soldStocks)) $soldStocks[] = $n;
    }
    sort($soldStocks);

    if (empty($soldStocks)) {
        echo '<div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>' . te('Aucune vente enregistrée.') . '</div>';
        echo $purchaseSection;
        return;
    }

    // Group by c_name
    $allBuys = $allSells = [];
    foreach ($achatDocs as $d) {
        $n = $d['c_name'] ?? '';
        if ($n) $allBuys[$n][]  = normalizeAchat($d);
    }
    foreach ($venteDocs as $d) {
        $n = $d['c_name'] ?? '';
        if ($n) $allSells[$n][] = normalizeVente($d);
    }

    $grandTotal = 0.0;
    $grandFrais = 0.0;
    $unresolvedSales = 0;
    ?>
    <div class="stats-wrap">
      <style>
        /* Pin the Valeur column (header, body rows and footer total rows) so it
           stays visible while scrolling this wide FIFO table horizontally. */
        #histoTbl thead th.h-name,
        #histoTbl tbody td.name-cell,
        #histoTbl tfoot td.foot-lbl {
          position: sticky; left: 0; z-index: 2;
          background: var(--surface-1);
        }
        /* Footer totals: label pinned left, amount pinned right, empty middle
           scrolls between them — so neither the label nor the value is ever hidden. */
        #histoTbl tfoot td.foot-lbl { white-space: nowrap; text-align: left; }
        #histoTbl tfoot td.foot-val {
          position: sticky; right: 0; z-index: 2;
          background: var(--surface-1);
        }
        #histoTbl thead th.h-name { z-index: 3; }
      </style>
      <h2><i class="fas fa-chart-bar me-2 t-amber"></i><?= te('Statistiques P&L') ?></h2>
      <p class="sub"><?= te('Correspondance FIFO des achats et des ventes par valeur.') ?></p>
      <?php if ($hasDeclaredDays): ?><p class="sub"><?= te("Les dates d'achat déclarées sont conservées séparément. Ces estimations utilisent encore les horodatages enregistrés.") ?></p><?php endif; ?>

      <div class="overflow-x-auto">
        <table class="tbl" id="histoTbl">
          <thead>
            <tr>
              <th class="h-name"  rowspan="2"><?= te('Valeur') ?></th>
              <th class="h-buy"   colspan="4"><?= te('Achat') ?></th>
              <th style="text-align:center;color:var(--text-mute)" rowspan="2"><?= te('Durée') ?></th>
              <th class="h-sell"  colspan="4"><?= te('Vente') ?></th>
              <th class="h-profit" rowspan="2"><?= te('Bénéfice') ?></th>
            </tr>
            <tr>
              <th><?= te('Date') ?></th><th class="num"><?= te('Qté') ?></th><th class="num"><?= te('Prix') ?></th><th class="num"><?= te('Montant') ?></th>
              <th><?= te('Date') ?></th><th class="num"><?= te('Qté') ?></th><th class="num"><?= te('Prix') ?></th><th class="num"><?= te('Montant') ?></th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($soldStocks as $stock):
              $rows = fifoMatch($allBuys[$stock] ?? [], $allSells[$stock] ?? []);
              if (empty($rows)) continue;
              $first = true;
            ?>
              <?php foreach ($rows as $r): ?>
                <tr>
                  <?php if ($first): $first = false; ?>
                    <td class="name-cell" rowspan="<?= count($rows) ?>"><?= htmlspecialchars($stock) ?></td>
                  <?php endif; ?>

                  <?php if (isset($r['error'])): $unresolvedSales++; ?>
                    <td colspan="9" style="color:var(--rose);padding:8px 16px">
                      <i class="fas fa-exclamation-triangle me-2"></i>Purchase history is incomplete or its ordering is uncertain. This sale is excluded from estimates.
                    </td>
                  <?php else:
                    $cls = $r['benefice'] > 0 ? 'pos' : ($r['benefice'] < 0 ? 'neg' : 'zero');
                    $grandTotal += $r['benefice'];
                    $grandFrais += commission($r['achat_montant']) + commission($r['vente_montant']);
                  ?>
                    <td class="date"><?= fmt_date($r['achat_date']) ?></td>
                    <td class="num mono"><?= rtrim(rtrim(monofmt($r['achat_nombre'], 8), '0'), '.') ?><?= $r['is_split'] ? ' <span class="badge-split">S</span>' : '' ?></td>
                    <td class="num mono"><?= monofmt($r['achat_prix']) ?></td>
                    <td class="num montant-buy"><?= monofmt($r['achat_montant']) ?></td>
                    <td class="dur"><?= $r['duree_days'] ?><?= te('j') ?></td>
                    <td class="date"><?= fmt_date($r['vente_date']) ?></td>
                    <td class="num mono"><?= rtrim(rtrim(monofmt($r['vente_nombre'], 8), '0'), '.') ?></td>
                    <td class="num mono"><?= monofmt($r['vente_prix']) ?></td>
                    <td class="num montant-sell"><?= monofmt($r['vente_montant']) ?></td>
                    <td class="num benefice <?= $cls ?>">
                      <?= ($r['benefice'] >= 0 ? '+' : '') . monofmt($r['benefice']) ?>
                    </td>
                  <?php endif; ?>
                </tr>
              <?php endforeach; ?>
            <?php endforeach; ?>
          </tbody>
          <tfoot>
            <?php if ($unresolvedSales > 0): ?>
              <tr><td colspan="11">Incomplete or ambiguous purchase history: <?= $unresolvedSales ?> sale(s) excluded from these estimates.</td></tr>
            <?php endif; ?>
            <?php
              $taxAmt  = max(0.0, $grandTotal) * TAX_RATE;
              $netAmt  = $grandTotal - $taxAmt - $grandFrais;
              $grossCls= $grandTotal >= 0 ? 'total-pos' : 'total-neg';
              $netCls  = $netAmt   >= 0 ? 'total-pos' : 'total-neg';
            ?>
            <tr>
              <td class="lbl foot-lbl"><?= te('Bénéfice brut') ?></td>
              <td colspan="9"></td>
              <td class="num foot-val <?= $grossCls ?>"><?= ($grandTotal>=0?'+':'') . monofmt($grandTotal) ?></td>
            </tr>
            <tr>
              <td class="lbl foot-lbl"><?= te('Taxe (') ?><?= (TAX_RATE*100) ?>%)</td>
              <td colspan="9"></td>
              <td class="num foot-val tax-cell">−<?= monofmt($taxAmt) ?></td>
            </tr>
            <tr>
              <td class="lbl foot-lbl"><?= te('Frais de courtage (') ?><?= (COMMISSION_RATE*100) ?><?= te('% achat + vente)') ?></td>
              <td colspan="9"></td>
              <td class="num foot-val tax-cell">−<?= monofmt($grandFrais) ?></td>
            </tr>
            <tr>
              <td class="lbl foot-lbl"><?= te('Bénéfice net') ?></td>
              <td colspan="9"></td>
              <td class="num foot-val <?= $netCls ?>"><?= ($netAmt>=0?'+':'') . monofmt($netAmt) ?></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
    <?php echo $purchaseSection; ?>
    <?php
}
