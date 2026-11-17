<?php
require_once __DIR__ . '/../core/SupabaseApp.php';
function requireClaim(bool $condition): void { if (!$condition) throw new RuntimeException('Recovery adapter assertion failed.'); }
$url='https://abcdefghijklmnopqrst.supabase.co'; $key='sb_publishable_fixture';
$id='a0000000-0000-4000-8000-000000000001';
foreach (['CLAIMED','DISABLED','NOT_AVAILABLE','PASSWORD_REQUIRED','REVIEW_REQUIRED','INVALID'] as $status) {
    $claims=0; $trades=0;
    $client=new SupabaseAppClient($url,$key,function($method,$url,$headers,$body) use (&$claims,&$trades,$status,$id) {
        requireClaim(in_array('Authorization: Bearer fixture.user.signature',$headers,true));
        if (str_contains($url,'claim_saved_portfolio')) {
            $claims++;requireClaim($body==='{}');
            $receipt=['status'=>$status];
            if ($status==='CLAIMED') $receipt['counts']=['achats'=>1,'ventes'=>0,'portefeuille'=>1,'benefits'=>0];
            return ['status'=>200,'body'=>json_encode($receipt)];
        }
        $trades++;return ['status'=>200,'body'=>json_encode($id)];
    },true);
    if (in_array($status,['PASSWORD_REQUIRED','REVIEW_REQUIRED','INVALID'],true)) {
        $rejected=false;
        try { $client->recordTrade('fixture.user.signature',$id,'buy','Fixture','1','10'); }
        catch (RuntimeException $failure) { $rejected=true; }
        requireClaim($rejected && $trades===0);
    } else {
        $client->recordTrade('fixture.user.signature',$id,'buy','Fixture','1','10');
        $client->recordTrade('fixture.user.signature',$id,'buy','Fixture','1','10');
        requireClaim($trades===2 && $claims===($status==='CLAIMED'?1:2));
    }
}
echo "Supabase portfolio claim client tests passed.\n";
