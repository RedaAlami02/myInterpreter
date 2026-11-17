<?php
/** A saved-profile sync may fill biographical gaps; it is not financial authority. */
function company_profile_sync_plan(array $company, array $profile, string $symbol, ?DateTimeImmutable $now = null): array
{
    $now ??= new DateTimeImmutable('now');
    $result = ['name'=>$company['name'] ?? '', 'symbol'=>$symbol, 'captured_at'=>null,
        'fields'=>[], 'expected'=>[], 'protected'=>[], 'available'=>[], 'reason'=>null];
    if (($profile['c_name'] ?? null) !== $result['name'] || ($profile['symbol'] ?? null) !== $symbol) {
        $result['reason']='Identité de la fiche non concordante'; return $result;
    }
    $stamp=$profile['captured_at'] ?? null;
    if (!is_string($stamp) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/D',$stamp)) {
        $result['reason']='Date de capture absente'; return $result;
    }
    try { $capture=new DateTimeImmutable($stamp); }
    catch (Throwable $error) { $result['reason']='Date de capture invalide'; return $result; }
    if ($capture->format('Y-m-d')!==substr($stamp,0,10)) {
        $result['reason']='Date de capture invalide'; return $result;
    }
    $result['captured_at']=$stamp;
    if ($capture>$now || $capture<$now->modify('-30 days')) {
        $result['reason']='Capture future ou vieille de plus de 30 jours'; return $result;
    }
    $computed=is_array($profile['computed'] ?? null) ? $profile['computed'] : [];
    $values=['ext_name'=>$profile['ext_name'] ?? null,'sector'=>$profile['sector'] ?? null,
        'description'=>$profile['description'] ?? null,'shareholders'=>$computed['shareholders'] ?? null];
    foreach ($values as $key=>$value) {
        if (!is_string($value) || $value==='' || mb_strlen($value)>4000) continue;
        if ($key==='shareholders') {
            $holders=json_decode($value,true);
            if (!is_array($holders) || !array_is_list($holders) || !$holders) continue;
            foreach ($holders as $holder) {
                if (!is_array($holder) || !is_string($holder['name'] ?? null) || trim($holder['name'])===''
                    || !is_numeric($holder['pct'] ?? null) || !is_finite((float)$holder['pct'])
                    || $holder['pct']<0 || $holder['pct']>100) continue 2;
            }
        }
        $result['available'][]=$key;
        $existing=$company[$key] ?? null;
        if ($existing!==null && $existing!=='') {
            if ($existing!==$value) $result['protected'][]=$key;
            continue;
        }
        $result['fields'][$key]=$value;
        $result['expected'][$key]=$existing;
    }
    return $result;
}

/** Counts describe proposals and confirmed outcomes, never freshness or factual certification. */
function company_sync_summary(array $plans, array $receipts): array
{
    $summary=['examined'=>count($plans),'proposed'=>0,'batch'=>0,'blocked'=>0,
        'updated'=>0,'unchanged'=>0,'not_applied'=>0];
    foreach ($plans as $plan) {
        if (!empty($plan['reason'])) $summary['blocked']++;
        if (!empty($plan['fields'])) $summary['proposed']++;
        if (!empty($plan['in_batch'])) $summary['batch']++;
    }
    foreach ($receipts as $receipt) {
        if (($receipt['status'] ?? '')==='UPDATED') $summary['updated']++;
        elseif (($receipt['status'] ?? '')==='UNCHANGED') $summary['unchanged']++;
        else $summary['not_applied']++;
    }
    return $summary;
}
