<?php
/** Date-only historical bars; no live quote or official-close authority is asserted. */
function latest_session_symbol(array $mappings,string $company): ?string {
    $symbols=[];
    foreach ($mappings as $row) if (($row['name']??null)===$company && is_string($row['symbol']??null)) $symbols[$row['symbol']]=true;
    if (count($symbols)!==1) return null;
    $symbol=array_key_first($symbols);
    if (!preg_match('/^[A-Z0-9][A-Z0-9._-]{0,31}$/D',$symbol)) return null;
    foreach ($mappings as $row) if (($row['symbol']??null)===$symbol && ($row['name']??null)!==$company) return null;
    return $symbol;
}

function session_decimal($value, bool $allowZero = false): ?string {
    if (!is_string($value) || strlen($value)>80 || !preg_match('/^[0-9]+(?:\.[0-9]+)?$/D',$value)) return null;
    [$whole,$fraction]=array_pad(explode('.',$value,2),2,'');
    $whole=ltrim($whole,'0') ?: '0';$fraction=rtrim($fraction,'0');
    $normal=$whole.($fraction!==''?'.'.$fraction:'');
    return ((!$allowZero && $normal==='0') || (float)$normal>1e15) ? null : $normal;
}

function latest_sessions(array $document,string $symbol,string $today,int $limit=5): array {
    if (($document['contract']??null)!=='recent-market-sessions/v1' || ($document['symbol']??null)!==$symbol
        || !is_array($document['candidates']??null) || !array_is_list($document['candidates'])
        || count($document['candidates'])>250 || $limit<1 || $limit>20) throw new RuntimeException('Session history is unavailable.');
    $days=[];
    foreach ($document['candidates'] as $candidate) {
        $day=$candidate['day']??'';
        if (!is_string($day) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/D',$day,$m)
            || !checkdate((int)$m[2],(int)$m[3],(int)$m[1]) || $day>$today
            || !in_array($candidate['tier']??null,[0,1],true)) continue;
        $price=session_decimal($candidate['price']??null);if ($price===null) continue;
        $row=['day'=>$day,'price'=>$price,'open'=>session_decimal($candidate['open']??null),
            'high'=>session_decimal($candidate['high']??null),'low'=>session_decimal($candidate['low']??null),
            'quantity'=>session_decimal($candidate['quantity']??null,true)];
        if ($row['quantity']!==null && str_contains($row['quantity'],'.')) $row['quantity']=null;
        $issues=is_array($candidate['issues']??null)?$candidate['issues']:[];
        if (array_intersect($issues,['SOURCE_OHLC_INCONSISTENT','inconsistent_ohlc_range','SOURCE_QUALITY_UNCLASSIFIED'])
            || ($row['low']!==null && $row['high']!==null && (float)$row['low']>(float)$row['high'])
            || ($row['low']!==null && (float)$price<(float)$row['low'])
            || ($row['high']!==null && (float)$price>(float)$row['high'])
            || ($row['open']!==null && (($row['low']!==null && (float)$row['open']<(float)$row['low'])
                || ($row['high']!==null && (float)$row['open']>(float)$row['high'])))) {
            $row['open']=$row['high']=$row['low']=null;
        }
        $days[$day][$candidate['tier']][json_encode($row,JSON_THROW_ON_ERROR)]=$row;
    }
    krsort($days);$result=[];
    foreach (array_slice($days,0,$limit,true) as $day=>$tiers) {
        ksort($tiers);$tier=array_key_first($tiers);$versions=array_values($tiers[$tier]);
        $result[]=count($versions)!==1
            ? ['day'=>$day,'price'=>null,'open'=>null,'high'=>null,'low'=>null,'quantity'=>null,'fallback'=>$tier>0,'conflict'=>true]
            : [...$versions[0],'fallback'=>$tier>0,'conflict'=>false];
    }
    return $result;
}

function render_latest_sessions(array $rows): void {
    ?>
    <section class="card-glass latest-sessions mb-4" aria-labelledby="latestSessionsTitle">
      <h2 id="latestSessionsTitle"><?= te('Dernières séances') ?></h2>
      <div class="overflow-x-auto"><table class="tbl">
        <thead><tr><th scope="col"><?= te('Date') ?></th><th scope="col" class="num"><?= te('Prix') ?></th>
          <th scope="col" class="num"><?= te('Ouverture') ?></th><th scope="col" class="num"><?= te('Plus haut') ?></th>
          <th scope="col" class="num"><?= te('Plus bas') ?></th><th scope="col" class="num"><?= te('Qté') ?></th></tr></thead>
        <tbody>
        <?php foreach ($rows as $row): ?><tr<?= $row['conflict']?' class="session-conflict"':'' ?>>
          <th scope="row" class="mono"><?= htmlspecialchars(implode('/',array_reverse(explode('-',$row['day'])))) ?></th>
          <?php foreach (['price','open','high','low','quantity'] as $field): ?>
            <td class="num mono"><?= $row[$field]===null?'—':number_format((float)$row[$field],$field==='quantity'?0:2,',',' ') ?></td>
          <?php endforeach; ?></tr><?php endforeach; ?>
        <?php if (!$rows): ?><tr><td colspan="6" class="muted"><?= te('Historique de séances indisponible.') ?></td></tr><?php endif; ?>
        </tbody>
      </table></div>
      <p class="muted latest-sessions__note"><?= te('Références historiques, pas de cotations en direct. Les champs absents restent indisponibles.') ?></p>
      <?php if (array_filter($rows,fn($row)=>$row['conflict'])): ?><p class="muted latest-sessions__note"><?= te('Des observations contradictoires restent non résolues.') ?></p><?php endif; ?>
    </section>
    <?php
}
