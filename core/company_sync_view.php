<?php
/** Presentation only; mutation and administrator checks belong to the controller. */
$fieldLabels=['ext_name'=>'Nom complet','sector'=>'Secteur','description'=>'Présentation','shareholders'=>'Actionnariat du profil'];
$statusLabels=['UPDATED'=>'Compléments appliqués','UNCHANGED'=>'Déjà présents',
    'PROTECTED'=>'Valeur existante conservée','STALE'=>'Profil modifié ou trop ancien : nouvel aperçu requis','MISSING'=>'Société introuvable'];
?>
<!DOCTYPE html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= te('Compléter les fiches sociétés') ?> | myInterpreter</title>
<link href="../assets/css/global.css?v=5" rel="stylesheet">
<link href="../assets/css/workspace.css?v=3" rel="stylesheet">
<link href="../assets/css/company_sync.css?v=20261116" rel="stylesheet">
<script src="../assets/js/theme.js?v=3"></script>
</head><body><main class="sync-shell">
<a href="../Update.php" class="sync-back"><?= te('Retour à Société / MAJ') ?></a>
<header><h1><?= te('Compléter les fiches sociétés') ?></h1>
<p><?= te('Prévisualisez les champs biographiques manquants avant de les appliquer.') ?></p>
<p class="sync-note"><?= te('Profils sauvegardés uniquement. Aucune collecte en direct ni mise à jour des chiffres financiers.') ?></p></header>
<?php if ($error): ?><p class="sync-alert" role="alert"><?= te($error) ?></p><?php endif; ?>
<?php if ($receipts): ?>
<section class="sync-result" aria-labelledby="sync-result-title" role="status">
<h2 id="sync-result-title"><?= te('Résultat confirmé') ?></h2>
<p><?= te('{count} fiches complétées', ['count'=>$summary['updated']]) ?> · <?= te('{count} déjà présentes', ['count'=>$summary['unchanged']]) ?> · <?= te('{count} non appliquées', ['count'=>$summary['not_applied']]) ?></p>
<ul><?php foreach ($receipts as $receipt): ?><li><strong><?= sync_escape($receipt['name']) ?></strong> — <?= te($statusLabels[$receipt['status']]) ?></li><?php endforeach; ?></ul>
</section>
<?php endif; ?>
<?php if (!$loadFailed): ?>
<section aria-labelledby="sync-preview-title">
<h2 id="sync-preview-title"><?= te('Aperçu des compléments') ?></h2>
<p class="sync-summary"><?= te('{count} fiches examinées', ['count'=>$summary['examined']]) ?> · <?= te('{count} fiches avec un complément proposé', ['count'=>$summary['proposed']]) ?><?php if ($summary['blocked']): ?> · <?= te('{count} profils non exploitables', ['count'=>$summary['blocked']]) ?><?php endif; ?></p>
<?php if (!$summary['proposed']): ?>
<p class="sync-empty"><?= te('Ces profils sauvegardés n’apportent aucun nouveau complément biographique.') ?></p>
<?php endif; ?>
<div class="sync-scroll"><table><thead><tr><th><?= te('Société') ?></th><th><?= te('Capture du profil (UTC)') ?></th><th><?= te('Compléments proposés') ?></th><th><?= te('État') ?></th></tr></thead><tbody>
<?php foreach ($plans as $plan): ?>
<tr><th scope="row"><?= sync_escape($plan['name']) ?> <small><?= sync_escape($plan['symbol']) ?></small></th>
<td><?php if ($plan['captured_at']): $stamp=(new DateTimeImmutable($plan['captured_at']))->setTimezone(new DateTimeZone('UTC')); ?><time datetime="<?= sync_escape($plan['captured_at']) ?>"><?= $stamp->format('d/m/Y') ?></time><?php else: ?><?= te('Inconnue') ?><?php endif; ?></td>
<td><?php if ($plan['fields']): ?>
<?php foreach ($plan['fields'] as $field=>$value): ?>
<details><summary><?= te($fieldLabels[$field]) ?></summary>
<?php $holders=$field==='shareholders' ? json_decode($value,true) : null;
if (is_array($holders) && array_is_list($holders) && $holders): ?>
<ul><?php foreach ($holders as $holder): ?><li><?= sync_escape($holder['name'] ?? '') ?><?php if (isset($holder['pct']) && is_numeric($holder['pct'])): ?> — <?= number_format((float)$holder['pct'],2,',',' ') ?> %<?php endif; ?></li><?php endforeach; ?></ul>
<?php else: ?><p class="sync-value"><?= nl2br(sync_escape($value)) ?></p><?php endif; ?>
</details>
<?php endforeach; ?>
<?php else: ?><?= te('Aucun complément proposé') ?><?php endif; ?></td>
<td><?php if ($plan['reason']): ?><?= te($plan['reason']) ?>
<?php elseif ($plan['fields']): ?><?= te($plan['in_batch'] ? 'Inclus dans ce lot' : 'Disponible au prochain lot') ?>
<?php elseif ($plan['protected']): ?><?= te('Valeurs existantes conservées') ?>
<?php elseif (empty($plan['available'])): ?><?= te('Aucun complément exploitable dans le profil') ?>
<?php else: ?><?= te('Champs disponibles déjà renseignés') ?><?php endif; ?></td></tr>
<?php endforeach; ?>
</tbody></table></div>
<?php if ($planToken): ?>
<form method="POST" class="sync-confirm" onsubmit="this.querySelector('button').disabled=true">
<?= csrf_field() ?><input type="hidden" name="plan_token" value="<?= sync_escape($planToken) ?>">
<p><?= te('Seuls les compléments marqués « Inclus dans ce lot » seront appliqués. Les valeurs existantes sont conservées.') ?></p>
<button type="submit" class="btn btn-cyan"><?= te('Appliquer les compléments à {count} fiches', ['count'=>$summary['batch']]) ?></button>
</form>
<?php elseif (!$applyAttempted): ?><p class="sync-note"><?= te('Aucune écriture effectuée.') ?></p><?php endif; ?>
</section>
<?php endif; ?>
<footer><a href="../Update.php"><?= te('Retour à Société / MAJ') ?></a> · <a href="sync_companies.php"><?= te('Actualiser l’aperçu') ?></a></footer>
</main></body></html>
