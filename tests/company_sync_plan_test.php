<?php
require __DIR__.'/../core/company_sync_plan.php';
function checkSync($condition) { if (!$condition) throw new RuntimeException('Profile sync guard regression'); }
$now=new DateTimeImmutable('2026-11-15T12:00:00Z');
$co=['name'=>'EXAMPLE','description'=>null,'sector'=>'Existing','bpa'=>0,'revenue'=>42];
$p=['c_name'=>'EXAMPLE','symbol'=>'EXA','captured_at'=>'2026-11-01T12:00:00.123456Z',
 'description'=>'Saved biography','sector'=>'Different','computed'=>['revenue'=>100,'bpa'=>22,'shareholders'=>'[{"name":"Holder","pct":51}]']];
$r=company_profile_sync_plan($co,$p,'EXA',$now);
checkSync($r['fields']===['description'=>'Saved biography','shareholders'=>'[{"name":"Holder","pct":51}]']);
checkSync($r['expected']===['description'=>null,'shareholders'=>null]);
checkSync($r['captured_at']===$p['captured_at']);
checkSync($r['protected']===['sector']);
checkSync(!isset($r['fields']['revenue'])&&!isset($r['fields']['bpa']));
foreach (['2026-09-01T12:00:00Z','2026-12-01T12:00:00Z','2026-02-30T12:00:00Z','bad'] as $date) {
 $bad=$p;$bad['captured_at']=$date;checkSync(company_profile_sync_plan($co,$bad,'EXA',$now)['fields']===[]);
}
$bad=$p;$bad['symbol']='OTHER';checkSync(company_profile_sync_plan($co,$bad,'EXA',$now)['fields']===[]);
$bad=$p;$bad['c_name']='OTHER';checkSync(company_profile_sync_plan($co,$bad,'EXA',$now)['fields']===[]);
echo "Safe profile sync planner: PASS\n";

$empty=$p;$empty['description']=null;$empty['sector']=null;$empty['computed']=['shareholders'=>'[]'];
$emptyPlan=company_profile_sync_plan($co,$empty,'EXA',$now);
checkSync($emptyPlan['fields']===[] && $emptyPlan['available']===[]);
$summary=company_sync_summary([['fields'=>['description'=>'a'],'in_batch'=>true,'reason'=>null]],
 [['status'=>'UPDATED'],['status'=>'UNCHANGED'],['status'=>'STALE']]);
checkSync($summary['updated']===1 && $summary['unchanged']===1 && $summary['not_applied']===1 && $summary['batch']===1);
