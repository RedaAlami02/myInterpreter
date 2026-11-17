<?php
// Execute the real GET controller with invented rows and no backend/network.
if (PHP_SAPI !== 'cli') exit(1);
$root = dirname(__DIR__); chdir($root);
$mode = $argv[1] ?? 'partial';
$_SERVER['REQUEST_METHOD'] = 'GET'; $_GET = $_POST = [];
if ($mode === 'disabled-post') { $_SERVER['REQUEST_METHOD']='POST'; $_POST['record_valuation']='1'; }
if ($mode === 'invalid-buy') $_POST = ['add_buy'=>'1','NAME'=>[]];
if ($mode === 'zero-buy') $_POST = ['add_buy'=>'1','NAME'=>'Alpha','NUMBER'=>'0','PRIX_ACHAT'=>'10'];
if ($mode === 'both-trades') $_POST = ['add_buy'=>'1','add_sell'=>'1'];
$_SESSION = ['USER_ID'=>'fixture-user'];
define('MYINTERPRETER_PORTFOLIO_VALUATION', false);
define('MYINTERPRETER_MARKET_PREVIEW', false);
require 'core/portfolio_prices.php';
require 'core/sector_allocation.php';
require 'core/i18n.php';
function app_session_start() {}
function csrf_verify() {}
function requireLogin() {}
function aw_user_id() { return 'fixture-user'; }
function aw_session() { return 'fixture-session'; }
function q_equal(...$v) { return json_encode($v); }
function q_limit(...$v) { return json_encode($v); }
function q_order_desc(...$v) { return json_encode($v); }
function q_order_asc(...$v) { return json_encode($v); }
$writeCalls = 0;
function sb_app() { global $writeCalls; $writeCalls++; throw new RuntimeException('No write permitted in GET fixture'); }
function aw_multi_list_docs(...$unused) {
    global $mode;
    $rows = [['c_name'=>'Alpha','quantity'=>2,'total_cost'=>15],['c_name'=>'Beta','quantity'=>1,'total_cost'=>20]];
    if ($mode === 'capped') {
        $rows = [];
        for ($i=0; $i<500; $i++) $rows[] = ['c_name'=>'Position '.$i,'quantity'=>1,'total_cost'=>1];
    }
    return ['holdings'=>$rows,'earnings'=>[]];
}
function aw_list_docs($collection,...$unused) {
    global $mode;
    if ($collection === 'dividends' || $collection === 'company') return [];
    if ($collection !== 'latest_prices') throw new RuntimeException('Unexpected fixture read');
    $rows = [['c_name'=>'Alpha','pa'=>10,'date'=>'2000-01-03T16:00:00Z']];
    if ($mode === 'complete') $rows[] = ['c_name'=>'Beta','pa'=>25,'date'=>'2000-01-03T16:00:00Z'];
    if ($mode === 'capped') {
        $rows=[];
        for ($i=0; $i<500; $i++) $rows[]=['c_name'=>'Position '.$i,'pa'=>2,'date'=>'2000-01-03T16:00:00Z'];
    }
    return $rows;
}
$config = file_get_contents('config/config.php');
foreach (['fmt_date'] as $function) {
    if (!preg_match('/^function '.$function.'\(.*?^\}/ms',$config,$match)) throw new RuntimeException('Formatter missing');
    eval($match[0]);
}
$dividends = preg_replace('/^require_once .*$/m','',file_get_contents('core/dividends.php'));
eval('?>'.$dividends);
$source = file_get_contents('portfolio.php');
$controller = substr($source,0,strpos($source,'<!DOCTYPE html>'));
$controller = preg_replace('/^.*(?:require_once|^require ).*$/m','',$controller);
ob_start();eval('?>'.$controller);ob_end_clean();
echo json_encode(['totals'=>$referenceTotals,'write_calls'=>$writeCalls,'holdings_complete'=>$holdingsComplete,'valuation_status'=>$valuationStatus,'flash'=>$flash],JSON_THROW_ON_ERROR);
