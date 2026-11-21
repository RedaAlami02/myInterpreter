<?php
// Actual controller/template with invented records and network stubs, CLI only.
if (PHP_SAPI !== 'cli') exit;
chdir(dirname(__DIR__));
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['SCRIPT_NAME'] = $_SERVER['PHP_SELF'] = '/infoAction.php';
$_GET = ['name'=>'ADDOHA']; $_POST = [];
$_SESSION = [];
define('MYINTERPRETER_MARKET_PREVIEW', false);
define('SUPABASE_ADMIN_USER_ID', 'fixture-admin');
function app_session_start(): void {}
function app_uses_supabase(): bool { return true; }
function aw_user_id(): ?string { return null; }
function sb_access_token(): string { return 'fixture.user.signature'; }
$config = file_get_contents('config/config.php');
$config = preg_replace('/^require_once .*backend\.php.*$/m', '', $config);
eval('?>'.$config);
require 'core/i18n.php';
require 'core/sector_allocation.php';
require 'core/latest_sessions.php';
require 'core/current_prices.php';
require 'core/company_market.php';
// Dividends helpers are pure once their compatibility include is removed.
$dividends = preg_replace('/^require_once .*$/m', '', file_get_contents('core/dividends.php'));
eval('?>'.$dividends);
function q_equal($field, $value): string { return json_encode(['field'=>$field,'value'=>$value]); }
function q_order_desc($field): string { return $field; }
function q_order_asc($field): string { return $field; }
function q_limit($value): string { return 'limit:'.$value; }
function aw_multi_list_docs($requests): array {
    return ['companies'=>[['name'=>'ADDOHA','na'=>100000,'net_profit'=>1,'fiscal_year'=>2025]],
            'symbols'=>[['name'=>'ADDOHA','symbol'=>'ADH']]];
}
function aw_list_docs(...$args): array { throw new RuntimeException('Unexpected serial read in initial page'); }
function sb_market(): object {
    return new class {
        function listDocumentsBatch($requests, $partial): array {
            if (!$partial || !in_array('limit:1', $requests['newest'][1], true)) throw new RuntimeException('Unbounded history on initial page');
            return ['newest'=>[['c_name'=>'ADDOHA','pa'=>30,'cb'=>3000000,'date'=>'2026-11-17T10:00:00Z']],
                    'price'=>[['c_name'=>'ADDOHA','pa'=>31,'date'=>'2026-11-18T10:00:00Z']],
                    'book'=>[], 'dividends'=>[]];
        }
    };
}
function sb_app(): object {
    return new class {
        function recentMarketSessions($token,$symbol): array {
            return ['contract'=>'recent-market-sessions/v1','symbol'=>$symbol,'candidates'=>[]];
        }
    };
}
$source = file_get_contents('infoAction.php');
$source = preg_replace('/^require_once .*$/m', '', $source);
// The layout's session navigation is outside this controller fixture.
$source = str_replace("<?php include 'core/sidebar.php'; ?>", '', $source);
eval('?>'.$source);
