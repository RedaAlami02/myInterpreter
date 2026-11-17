<?php
require __DIR__.'/../core/latest_sessions.php';
function check_session(bool $condition): void { if (!$condition) throw new RuntimeException('Session regression failed.'); }
function document_sessions(array $rows): array { return ['contract'=>'recent-market-sessions/v1','symbol'=>'AAA','candidates'=>$rows]; }
function bar_session(string $day='2026-10-20',array $overrides=[]): array {
    return array_replace(['day'=>$day,'tier'=>0,'identity'=>'fixture','price'=>'10.00','open'=>'9','high'=>'11','low'=>'8','quantity'=>'2','issues'=>[]],$overrides);
}
$today='2026-11-01';
check_session(latest_session_symbol([['name'=>'Alpha','symbol'=>'AAA']],'Alpha')==='AAA');
check_session(latest_session_symbol([['name'=>'Alpha','symbol'=>'AAA'],['name'=>'Beta','symbol'=>'AAA']],'Alpha')===null);
check_session(latest_session_symbol([['name'=>'Alpha','symbol'=>'AAA'],['name'=>'Alpha','symbol'=>'BBB']],'Alpha')===null);
check_session(latest_session_symbol([['name'=>'Beta','symbol'=>'AAA']],'Alpha')===null);
$rows=[];foreach (range(15,21) as $day) $rows[]=bar_session('2026-10-'.$day);
$result=latest_sessions(document_sessions($rows),'AAA',$today);
check_session(count($result)===5 && $result[0]['day']==='2026-10-21' && $result[4]['day']==='2026-10-17');
$result=latest_sessions(document_sessions([bar_session(),bar_session('2026-10-20',['price'=>'10.000'])]),'AAA',$today);
check_session(count($result)===1 && !$result[0]['conflict'] && $result[0]['price']==='10');
$result=latest_sessions(document_sessions([bar_session(),bar_session('2026-10-20',['price'=>'9'])]),'AAA',$today);
check_session($result[0]['conflict'] && $result[0]['price']===null);
$result=latest_sessions(document_sessions([bar_session(),bar_session('2026-10-20',['tier'=>1,'price'=>'12'])]),'AAA',$today);
check_session($result[0]['price']==='10' && !$result[0]['fallback']);
$result=latest_sessions(document_sessions([bar_session('2026-10-21',['tier'=>1,'quantity'=>'0','volume_mad'=>'9999'])]),'AAA',$today);
check_session($result[0]['fallback'] && $result[0]['quantity']==='0');
$result=latest_sessions(document_sessions([bar_session('2026-10-21',['quantity'=>null,'volume_mad'=>'9999','open'=>null])]),'AAA',$today);
check_session($result[0]['quantity']===null && $result[0]['open']===null);
$result=latest_sessions(document_sessions([bar_session('2026-10-21',['high'=>'5','low'=>'12'])]),'AAA',$today);
check_session($result[0]['price']==='10' && $result[0]['open']===null && $result[0]['low']===null);
check_session(latest_sessions(document_sessions([bar_session('2099-01-01'),bar_session('2026-02-30'),bar_session('2026-10-21',['price'=>'NaN'])]),'AAA',$today)===[]);
$result=latest_sessions(document_sessions([bar_session('2026-10-21',['quantity'=>'2.5'])]),'AAA',$today);
check_session($result[0]['quantity']===null);
try { latest_sessions(document_sessions([]),'BBB',$today);throw new LogicException('Mismatch accepted'); } catch (RuntimeException $error) {}
echo "14 recent-session identity/normalization/coverage cases passed.\n";
