<?php
/** Admin saved-profile preview. Only an explicit CSRF-protected POST can apply a reviewed plan. */
require_once __DIR__.'/../core/session.php';
app_session_start();
require_once __DIR__.'/../config/config.php';
require_once __DIR__.'/../core/Appwrite.php';
require_once __DIR__.'/../core/auth.php';
require_once __DIR__.'/../core/company_sync_plan.php';
requireAdmin();
header('Cache-Control: no-store');
$receipts=[]; $error=null; $plans=[]; $changes=[]; $loadFailed=false; $applyAttempted=false;
if ($_SERVER['REQUEST_METHOD']==='POST') {
    csrf_verify();
    $saved=$_SESSION['company_sync_plan'] ?? null;
    $token=$_POST['plan_token'] ?? null;
    if (!is_array($saved) || ($saved['scope'] ?? null)!=='biography-gap/v2' || !is_string($token) || !hash_equals($saved['token'],$token)
        || $saved['expires']<time() || $saved['owner']!==aw_user_id()) {
        $error='Aperçu expiré. Vérifiez les nouvelles propositions avant de les appliquer.';
    } else {
        unset($_SESSION['company_sync_plan']);
        $applyAttempted=true;
        try { $receipts=sb_admin()->applyProfileBiographies(sb_access_token(),$saved['changes']); }
        catch (Throwable $failure) { $error='Le résultat de l’application n’a pas pu être confirmé. Rechargez l’aperçu pour vérifier les valeurs enregistrées.'; }
    }
}
$only=isset($_GET['symbol']) && is_string($_GET['symbol']) ? strtoupper(trim($_GET['symbol'])) : null;
try {
    // Three bounded reads replace the old per-company read/write loop.
    $companies=aw_list_docs('company',[q_order_asc('name'),q_limit(500)]);
    $formats=aw_list_docs('format',[q_limit(500)]);
    $profiles=aw_list_docs('company_profiles',[q_limit(500)]);
    $byName=[]; $ambiguous=[]; $bySymbol=[];
    foreach ($formats as $row) {
        $name=$row['name'] ?? ''; $symbol=$row['symbol'] ?? '';
        if (isset($byName[$name])) $ambiguous[$name]=true;
        $byName[$name]=$symbol;
    }
    foreach ($profiles as $row) $bySymbol[$row['$id']]=$row['profile'] ?? [];
    foreach ($companies as $company) {
        $name=$company['name']; $symbol=$byName[$name] ?? '';
        if ($only && strtoupper($symbol)!==$only) continue;
        $plan=company_profile_sync_plan($company,$bySymbol[$symbol] ?? [],$symbol);
        if (!$symbol || isset($ambiguous[$name])) {
            $plan['fields']=[]; $plan['reason']='Symbole absent ou ambigu';
        }
        $plan['in_batch']=(bool)$plan['fields'] && count($changes)<25;
        $plans[]=$plan;
        if ($plan['in_batch']) {
            $changes[]=['name'=>$name,'symbol'=>$symbol,'captured_at'=>$plan['captured_at'],
                'fields'=>(object)$plan['fields'],'expected'=>(object)$plan['expected']];
        }
    }
} catch (Throwable $failure) { $error='Les fiches sauvegardées sont temporairement indisponibles.'; $loadFailed=true; }
$planToken=null;
if ($changes && !$loadFailed) {
    $planToken=bin2hex(random_bytes(16));
    $_SESSION['company_sync_plan']=['scope'=>'biography-gap/v2','token'=>$planToken,'owner'=>aw_user_id(),'expires'=>time()+900,'changes'=>$changes];
} else { unset($_SESSION['company_sync_plan']); }
$summary=company_sync_summary($plans,$receipts);
function sync_escape($value): string { return htmlspecialchars((string)$value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'); }
require __DIR__.'/../core/company_sync_view.php';
