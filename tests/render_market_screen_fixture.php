<?php
// CLI only. Real controllers/templates with synthetic data and network stubs.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
$root = dirname(__DIR__); chdir($root);
$page = $argv[1] ?? 'index';
if (!in_array($page, ['index','screener'], true)) throw new RuntimeException('Unknown fixture');
$enabled = ($argv[2] ?? 'true') === 'true';
$state = $argv[3] ?? 'AVAILABLE';
$_GET = ['lang'=>$argv[5] ?? 'fr']; $_POST = [];
$_SESSION = ['logged_in'=>true,'USER_ID'=>'fixture-user','USER_EMAIL'=>'fixture@example.invalid'];
$_SERVER['REQUEST_METHOD']='GET'; $_SERVER['PHP_SELF']=$_SERVER['SCRIPT_NAME']='/'.$page.'.php';
define('MYINTERPRETER_MARKET_PREVIEW',$enabled); define('BASE_URL','');
define('MYINTERPRETER_DIRECT_SOURCE_REQUESTS', false);
define('ADMIN_USER_ID','fixture-admin'); define('MARKET_TZ','Africa/Casablanca');
require_once $root.'/core/i18n.php';
require_once $root.'/core/ShadowMarketFeed.php';
$legacyRequests=0; $previewRequests=0; $sourceRequests=0;
function app_session_start(): void {}
function csrf_token(): string { return 'fixture-csrf'; }
function is_admin(): bool { return false; }
function csrf_field(): string { return '<input type="hidden" name="csrf_token" value="fixture-csrf">'; }
function q_order_desc(...$unused): string { return 'fixture'; }
function q_order_asc(...$unused): string { return 'fixture'; }
function q_limit(...$unused): string { return 'fixture'; }
function q_equal(...$unused): string { return 'fixture'; }
function q_greater_equal(...$unused): string { return 'fixture'; }
function q_offset(...$unused): string { return 'fixture'; }
function display_name(string $name, ?string $extName = null): string { return $extName ?: $name; }
foreach (['PER_GREEN'=>15,'PER_ORANGE'=>25,'PEG_GREEN'=>1.0,'PEG_ORANGE'=>1.5,
          'PR_GREEN'=>1.0,'PR_ORANGE'=>2.0,'PB_GREEN'=>1.0,'PB_ORANGE'=>2.0] as $constant => $value) {
    define($constant, $value);
}
$fixtureData = [
    ['$id'=>'fx-1','c_name'=>'Alpha','symbol'=>'ALP','sector'=>'Banks','date'=>'2026-10-27T10:00:00.000+00:00',
     'pa'=>100,'per'=>10,'peg'=>1,'pr'=>1,'pb'=>1,'variation'=>2.5,'qty_traded'=>1000],
    ['$id'=>'fx-2','c_name'=>'Beta','symbol'=>'BET','sector'=>'Industry','date'=>'2026-10-27T10:00:00.000+00:00',
     'pa'=>50,'per'=>20,'peg'=>2,'pr'=>2,'pb'=>2,'variation'=>-1.5,'qty_traded'=>500],
    ['$id'=>'fx-3','c_name'=>'MASI','symbol'=>'MASI','sector'=>'','date'=>'2026-10-27T10:00:00.000+00:00','pa'=>12345.67],
];
function aw_multi_list_docs(array $requests): array {
    global $legacyRequests, $fixtureData;
    $legacyRequests++;
    $out = [];
    foreach ($requests as $name => $request) $out[$name] = $request[0] === 'data' ? $fixtureData : [];
    return $out;
}
function aw_list_docs(string $collection, array $queries = []): array {
    global $legacyRequests, $fixtureData;
    $legacyRequests++;
    if ($collection === 'company') return [
        ['$id'=>'c1','name'=>'Alpha','sector'=>'Banks','ext_name'=>'Alpha'],
        ['$id'=>'c2','name'=>'Beta','sector'=>'Industry','ext_name'=>'Beta'],
    ];
    return $collection === 'data' ? $fixtureData : [];
}
function aw_count_docs(string $collection): int {
    global $legacyRequests;
    $legacyRequests++;
    return 3;
}
function sb_market_preview(): ShadowMarketSnapshot {
    global $previewRequests,$state,$root;
    $previewRequests++;
    if ($state==='ERROR') throw new RuntimeException('private-fixture-diagnostic');
    $payload=json_decode(file_get_contents($root.'/tests/fixtures/market_screen_preview.json'),true,64,JSON_THROW_ON_ERROR);
    if ($state!=='AVAILABLE') { $payload['status']=$state; $payload['rows']=[]; }
    return new ShadowMarketSnapshot($payload);
}
// Execute the real pure date formatters without loading runtime credentials.
$config=file_get_contents($root.'/config/config.php');
foreach (['fmt_date','fmt_datetime','fmt_time'] as $function) {
    if (!preg_match('/^function '.$function.'\(.*?^\}/ms',$config,$match)) throw new RuntimeException('Formatter missing');
    eval($match[0]);
}
$source=file_get_contents($root.'/'.$page.'.php');
$controller=substr($source,0,strpos($source,'<!DOCTYPE html>'));
$controller=preg_replace('/^.*(?:require_once|^require ).*$/m','',$controller);
$controller=preg_replace('/^function _live_market_status\(\): array \{.*?^\}/ms',
    'function _live_market_status(): array { global $sourceRequests; if (!MYINTERPRETER_DIRECT_SOURCE_REQUESTS) return []; $sourceRequests++; throw new RuntimeException("Source access forbidden in fixture"); }',$controller);
$loginError=''; $isSignUp=false; $sessionValidated=true;
ob_start(); eval('?>'.$controller); ob_end_clean();
if (($argv[4] ?? 'report')==='report') {
    echo json_encode(['legacy_requests'=>$legacyRequests,'preview_requests'=>$previewRequests,
        'source_requests'=>$sourceRequests,'snapshot_status'=>$marketPreviewSnapshot?->status,
        'snapshot_rows'=>count($marketPreviewSnapshot?->rowsAt(new DateTimeImmutable('2026-10-28T12:05:00Z')) ?? [])]);
    exit;
}
if (!$enabled) throw new RuntimeException('Render fixture only supports preview');
$fixtureAsOf=new DateTimeImmutable('2026-10-28T12:05:00Z');
$template=substr($source,strpos($source,'<!DOCTYPE html>'));
$template=str_replace('__DIR__',var_export($root,true),$template);
$template=str_replace('render_market_preview($marketPreviewSnapshot);','render_market_preview($marketPreviewSnapshot, $fixtureAsOf);',$template);
// Use local styles only; screenshots and browser checks require no CDN access.
$template=preg_replace('~<link[^>]+href="https://[^>]+>~','',$template);
ob_start(); eval('?>'.$template); $html=ob_get_clean();
echo str_replace('<main class="main">','<main class="main"><p class="muted">Données fictives — démonstration.</p>',$html);
