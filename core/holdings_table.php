      <!-- Holdings table -->
      <?php if (!empty($holdings)): ?>
      <style>
        /* Extra column groups are collapsed by default so the table stays narrow;
           the toggles below reveal them on demand (progressive disclosure). */
        #holdingsTbl .col-frais, #holdingsTbl .col-seuil { display: none; }
        #holdingsTbl.show-frais .col-frais { display: table-cell; }
        #holdingsTbl.show-seuil .col-seuil { display: table-cell; }
        .col-toggles { display:flex; gap:8px; justify-content:flex-end; align-items:center; margin-bottom:10px; flex-wrap:wrap; }
        .col-toggles .lbl { font-size:0.82rem; color:var(--text-mute); margin-right:2px; }
        .col-toggle { opacity:0.5; }
        .col-toggle.active { opacity:1; }
        /* Pin the Société column so it stays visible during horizontal scroll. */
        #holdingsTbl thead th:first-child,
        #holdingsTbl tbody td:first-child {
          position: sticky; left: 0; z-index: 2;
          background: var(--surface-1);
        }
        #holdingsTbl thead th:first-child { z-index: 3; }
        #holdingsTbl .table-sort { display:inline-flex; align-items:center; gap:7px; padding:8px 0; border:0; background:transparent; color:inherit; font:inherit; text-align:inherit; text-transform:inherit; letter-spacing:inherit; cursor:pointer; }
        #holdingsTbl .table-sort:hover { color:var(--cyan); }
        #holdingsTbl .table-sort:focus-visible { outline:2px solid var(--cyan); outline-offset:4px; border-radius:3px; }
        #holdingsTbl .table-sort__arrow { opacity:.55; }
        #holdingsTbl th[aria-sort="ascending"] .table-sort__arrow,
        #holdingsTbl th[aria-sort="descending"] .table-sort__arrow { opacity:1; color:var(--cyan); }
      </style>
      <div class="col-toggles">
        <span class="lbl"><i class="fas fa-table-columns me-1"></i><?= te('Colonnes :') ?></span>
        <button type="button" class="btn btn-ghost btn-sm col-toggle" aria-pressed="false" onclick="toggleCols('frais', this)">
          <i class="fas fa-coins"></i> <?= te('Frais') ?>
        </button>
        <button type="button" class="btn btn-ghost btn-sm col-toggle" aria-pressed="false" onclick="toggleCols('seuil', this)">
          <i class="fas fa-scale-balanced"></i> <?= te('Équilibre') ?>
        </button>
      </div>
      <div class="card-glass overflow-x-auto mb-4">
        <table class="tbl" id="holdingsTbl" data-sort-ascending="<?= te('Trier par ordre croissant') ?>" data-sort-descending="<?= te('Trier par ordre décroissant') ?>">
          <thead><tr>
            <th><?= te('Société') ?></th>
            <th class="num"><?= te('Quantité') ?></th>
            <th class="num"><?= te('Montant investi') ?> <span class="muted"><?= te('(par action)') ?></span></th>
            <th class="num"><?= te('Valeur actuelle') ?></th>
            <th class="num"><?= te('Gain / Perte') ?></th>
            <th class="num col-frais"><?= te('Frais achat') ?></th>
            <th class="num col-frais"><?= te('Frais de vente estimés') ?></th>
            <th class="num col-frais"><?= te('Total frais') ?></th>
            <th class="num col-seuil"><?= te('Seuil de rentabilité') ?> <span class="muted"><?= te('(par action)') ?></span></th>
          </tr></thead>
          <tbody>
            <?php foreach ($holdings as $i => $h):
              $cur = $chartValues[$i];
              $buy = $chartBuys[$i];
              $pnl = $cur - $buy;
              $cls = $cur > 0 ? ($pnl > 0 ? 'pos' : ($pnl < 0 ? 'neg' : 'zero')) : 'zero';
              $pct = ($cur > 0 && $buy > 0) ? ($pnl / $buy) * 100 : null;
              $fraisAchat = commission($buy);                    // 1 % already paid to build this position
              $fraisVente = $cur > 0 ? commission($cur) : null;  // Recorded-price estimate only.
              $totalFrais = $fraisVente !== null ? $fraisAchat + $fraisVente : null;
              // Break-even: market value where selling nets exactly the cash paid in,
              // covering both the 1 % buy commission (already paid) and the 1 % sell commission.
              //   V·(1−r) = B·(1+r)  →  V_be = B·(1+r)/(1−r)
              // Break-even value (incl. 1% commission both legs + 10% gain tax).
              $breakeven  = breakeven_value($buy);
              // Per-share break-even remains available even when the current quote is missing.
              $breakevenPerShare = $h['quantity'] > 1 ? $breakeven / $h['quantity'] : null;
              $sortValues = [$h['c_name'], (float)$h['quantity'], $buy,
                  $cur > 0 ? $cur : null, $cur > 0 ? $pnl : null,
                  $fraisAchat, $fraisVente, $totalFrais, $breakeven > 0 ? $breakeven : null];
            ?>
            <tr data-sort-values="<?= htmlspecialchars(json_encode($sortValues, JSON_THROW_ON_ERROR), ENT_QUOTES) ?>">
              <td class="label-cell"><a href="infoAction.php?name=<?= urlencode($h['c_name']) ?>" class="t-cyan"><?= htmlspecialchars($h['c_name']) ?></a></td>
              <td class="num mono"><?= (int)$h['quantity'] ?></td>
              <td class="num mono"><?= number_format($buy, 2) ?><?php if ($h['quantity'] > 1): ?> <span class="muted">(<?= number_format($buy / $h['quantity'], 2) ?>)</span><?php endif; ?></td>
              <td class="num mono"><span data-live-value="<?= htmlspecialchars($h['c_name'], ENT_QUOTES) ?>"><?= $cur > 0 ? number_format($cur, 2) : '—' ?></span><?php if ($cur > 0 && $h['quantity'] > 1): ?> <span class="muted">(<span data-live-price="<?= htmlspecialchars($h['c_name'], ENT_QUOTES) ?>"><?= number_format($cur / $h['quantity'], 2) ?></span>)</span><?php endif; ?>
                <?php if (!empty($recordedPriceMap[$h['c_name']]['day'])): ?><small class="muted"><?= htmlspecialchars($recordedPriceMap[$h['c_name']]['day']) ?> UTC</small><?php endif; ?>
              </td>
              <td class="num mono <?= $cls ?>"><?php if ($cur > 0): ?><?= ($pnl>=0?'+':'') . number_format($pnl,2) ?><?php if ($pct !== null): ?> <span class="muted">(<?= ($pct>=0?'+':'') . number_format($pct,2) ?>%)</span><?php endif; ?><?php else: ?><span class="muted">—</span><?php endif; ?></td>
              <td class="num mono muted col-frais"><?= number_format($fraisAchat, 2) ?></td>
              <td class="num mono muted col-frais"><?= $fraisVente !== null ? number_format($fraisVente, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono col-frais"><?= $totalFrais !== null ? number_format($totalFrais, 2) : '<span class="muted">—</span>' ?></td>
              <td class="num mono col-seuil"><?php if ($breakeven > 0): ?><?= number_format($breakeven, 2) ?><?php if ($breakevenPerShare !== null): ?> <span class="muted">(<?= number_format($breakevenPerShare, 2) ?>)</span><?php endif; ?><?php else: ?><span class="muted">—</span><?php endif; ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <?php else: ?>
        <div class="alert alert-info"><i class="fas fa-info-circle me-2"></i><?= te('Aucune position ouverte.') ?></div>
      <?php endif; ?>

