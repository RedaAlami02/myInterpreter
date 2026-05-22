<?php
/**
 * FIFO statistics partial — included by portfolio.php.
 * session_start() and DB connection are assumed to be active.
 */
require_once 'core/Database.php';

/* ── FIFO matching ───────────────────────────────────────── */
function fifoMatch(array $achats, array $ventes): array
{
    $rows      = [];
    $j         = 0;
    $remaining = isset($achats[0]) ? (float)$achats[0]['NUMBER'] : 0;

    foreach ($ventes as $v) {
        $toSell = (float)$v['NUMBER'];
        if ($toSell <= 0) continue;

        while ($toSell > 0) {
            while ($j < count($achats) && $remaining <= 0) {
                $j++;
                $remaining = isset($achats[$j]) ? (float)$achats[$j]['NUMBER'] : 0;
            }
            if ($j >= count($achats)) {
                $rows[] = ['error' => "Vente sans achat correspondant ({$v['DATE']})"];
                break;
            }

            $a       = $achats[$j];
            $matched = min($toSell, $remaining);
            $isSplit = $matched < (float)$a['NUMBER'];

            $buyAmt  = $matched * (float)$a['PRIX_ACHAT'];
            $sellAmt = $matched * (float)$v['PRIX_VENTE'];

            $rows[] = [
                'achat_date'    => $a['DATE'],
                'achat_nombre'  => $matched,
                'achat_prix'    => (float)$a['PRIX_ACHAT'],
                'achat_montant' => $buyAmt,
                'vente_date'    => $v['DATE'],
                'vente_nombre'  => $matched,
                'vente_prix'    => (float)$v['PRIX_VENTE'],
                'vente_montant' => $sellAmt,
                'duree_days'    => (int)(new DateTime($a['DATE']))->diff(new DateTime($v['DATE']))->days,
                'benefice'      => $sellAmt - $buyAmt,
                'is_split'      => $isSplit,
            ];

            $remaining -= $matched;
            $toSell    -= $matched;
        }
    }
    return $rows;
}

function monofmt(float $n, int $dec = 2): string
{
    return number_format($n, $dec, '.', ' ');
}

function stats(): void
{
    $pdo = (new Database())->opendb();
    $uid = $_SESSION['ID_USER'];

    $stmt = $pdo->prepare('SELECT DISTINCT C_NAME FROM VENTES WHERE ID_USER = ? ORDER BY C_NAME');
    $stmt->execute([$uid]);
    $stocks = $stmt->fetchAll(PDO::FETCH_COLUMN);

    $stmtA = $pdo->prepare('SELECT DATE, C_NAME, NUMBER, PRIX_ACHAT FROM ACHATS WHERE C_NAME=? AND ID_USER=? ORDER BY DATE');
    $stmtV = $pdo->prepare('SELECT DATE, C_NAME, NUMBER, PRIX_VENTE FROM VENTES WHERE C_NAME=? AND ID_USER=? ORDER BY DATE');

    $allBuys  = [];
    $allSells = [];
    foreach ($stocks as $s) {
        $stmtA->execute([$s, $uid]); $allBuys[$s]  = $stmtA->fetchAll();
        $stmtV->execute([$s, $uid]); $allSells[$s] = $stmtV->fetchAll();
    }

    $grandTotal = 0.0;
    ?>
    <div class="stats-wrap">
      <h2><i class="fas fa-chart-bar me-2 t-amber"></i>Statistiques P&L</h2>
      <p class="sub">Correspondance FIFO des achats et des ventes par valeur.</p>

      <?php if (empty($stocks)): ?>
        <div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>Aucune vente enregistrée.</div>
        <?php return; ?>
      <?php endif; ?>

      <div class="overflow-x-auto">
        <table class="tbl">
          <thead>
            <tr>
              <th class="h-name"  rowspan="2">Valeur</th>
              <th class="h-buy"   colspan="4">Achat</th>
              <th style="text-align:center;color:var(--text-mute)" rowspan="2">Durée</th>
              <th class="h-sell"  colspan="4">Vente</th>
              <th class="h-profit" rowspan="2">Bénéfice</th>
            </tr>
            <tr>
              <th>Date</th><th class="num">Qté</th><th class="num">Prix</th><th class="num">Montant</th>
              <th>Date</th><th class="num">Qté</th><th class="num">Prix</th><th class="num">Montant</th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($stocks as $stock):
              $rows = fifoMatch($allBuys[$stock], $allSells[$stock]);
              if (empty($rows)) continue;
              $first = true;
            ?>
              <?php foreach ($rows as $r): ?>
                <tr>
                  <?php if ($first): $first = false; ?>
                    <td class="name-cell" rowspan="<?= count($rows) ?>"><?= htmlspecialchars($stock) ?></td>
                  <?php endif; ?>

                  <?php if (isset($r['error'])): ?>
                    <td colspan="9" style="color:var(--rose);padding:8px 16px">
                      <i class="fas fa-exclamation-triangle me-2"></i><?= htmlspecialchars($r['error']) ?>
                    </td>
                  <?php else:
                    $cls = $r['benefice'] > 0 ? 'pos' : ($r['benefice'] < 0 ? 'neg' : 'zero');
                    $grandTotal += $r['benefice'];
                  ?>
                    <td class="date"><?= htmlspecialchars($r['achat_date']) ?></td>
                    <td class="num mono"><?= monofmt($r['achat_nombre'], 0) ?><?= $r['is_split'] ? ' <span class="badge-split">÷</span>' : '' ?></td>
                    <td class="num mono"><?= monofmt($r['achat_prix']) ?></td>
                    <td class="num montant-buy"><?= monofmt($r['achat_montant']) ?></td>
                    <td class="dur"><?= $r['duree_days'] ?>j</td>
                    <td class="date"><?= htmlspecialchars($r['vente_date']) ?></td>
                    <td class="num mono"><?= monofmt($r['vente_nombre'], 0) ?></td>
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
            <?php
              $taxAmt  = $grandTotal * TAX_RATE;
              $netAmt  = $grandTotal - $taxAmt;
              $grossCls= $grandTotal >= 0 ? 'total-pos' : 'total-neg';
              $netCls  = $netAmt   >= 0 ? 'total-pos' : 'total-neg';
            ?>
            <tr>
              <td class="lbl" colspan="10">Bénéfice brut</td>
              <td class="num <?= $grossCls ?>"><?= ($grandTotal>=0?'+':'') . monofmt($grandTotal) ?></td>
            </tr>
            <tr>
              <td class="lbl" colspan="10">Taxe (<?= (TAX_RATE*100) ?>%)</td>
              <td class="num tax-cell">−<?= monofmt($taxAmt) ?></td>
            </tr>
            <tr>
              <td class="lbl" colspan="10">Bénéfice net</td>
              <td class="num <?= $netCls ?>"><?= ($netAmt>=0?'+':'') . monofmt($netAmt) ?></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
    <?php
}
