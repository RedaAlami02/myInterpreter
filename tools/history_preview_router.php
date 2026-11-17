<?php
// Development router: expose only sanitized history pages, never private files.
if (PHP_SAPI !== 'cli-server') { http_response_code(404); exit; }
$root = dirname(__DIR__);
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if ($path === '/' || $path === '/history-preview.php') {
    require $root . '/history-preview.php';
    return true;
}
if ($path === '/handlers/recovered_history.php') {
    require $root . '/handlers/recovered_history.php';
    return true;
}
if ($path === '/assets/css/history-preview.css') {
    header('Content-Type: text/css');
    header('X-Content-Type-Options: nosniff');
    readfile($root . '/assets/css/history-preview.css');
    return true;
}
if ($path === '/favicon.ico') { http_response_code(204); return true; }
http_response_code(404);
header('Content-Type: text/plain; charset=utf-8');
echo 'Not found';
return true;
