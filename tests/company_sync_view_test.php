<?php
require __DIR__.'/../core/i18n.php';
require __DIR__.'/../core/company_sync_plan.php';
function csrf_field() { return '<input name="csrf" value="fixture">'; }
function sync_escape($value): string { return htmlspecialchars((string)$value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'); }
function renderSync(array $overrides=[]): string {
    $plans=[]; $receipts=[]; $error=null; $loadFailed=false; $applyAttempted=false; $planToken=null;
    extract($overrides);
    $summary=company_sync_summary($plans,$receipts);
    ob_start(); require __DIR__.'/../core/company_sync_view.php'; return ob_get_clean();
}
function expectSync($ok) { if (!$ok) throw new RuntimeException('Sync presentation regression'); }
$html=renderSync();
expectSync(str_contains($html,'aucun nouveau complément biographique') && !str_contains($html,'Résultat confirmé'));
$html=renderSync(['receipts'=>[['name'=>'<unsafe>','status'=>'UPDATED'],['name'=>'B','status'=>'UNCHANGED'],['name'=>'C','status'=>'STALE']],'applyAttempted'=>true]);
expectSync(str_contains($html,'1 fiches complétées') && str_contains($html,'1 déjà présentes') && str_contains($html,'1 non appliquées'));
expectSync(str_contains($html,'&lt;unsafe&gt;') && !str_contains($html,'<unsafe>') && !str_contains($html,'Aucune écriture effectuée.'));
$html=renderSync(['loadFailed'=>true,'error'=>'Indisponible']);
expectSync(str_contains($html,'role="alert"') && !str_contains($html,'0 fiches examinées'));
$html=renderSync(['applyAttempted'=>true,'error'=>'Résultat non confirmé']);
expectSync(!str_contains($html,'Aucune écriture effectuée.') && !str_contains($html,'Résultat confirmé'));
echo "Sync presentation: PASS\n";
