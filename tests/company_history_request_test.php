<?php
if (isset($argv[1])) {
    $case = $argv[1];
    $_GET = ['name'=>'Alpha'];
    $_SERVER['REQUEST_METHOD'] = $case === 'post' ? 'POST' : 'GET';
    if ($case === 'array') $_GET['name'] = [];
    if ($case === 'extra') $_GET['user_id'] = 'other';
    function app_session_start(): void {}
    function sb_restore_session(): bool { return $GLOBALS['case'] !== 'guest'; }
    function sb_access_token(): string { return 'fixture.user.signature'; }
    function sb_app(): object {
        return new class {
            function companyDailyHistory($token, $name): array {
                if ($GLOBALS['case'] === 'failure') throw new RuntimeException('private-diagnostic');
                return ['contract'=>'company-daily-history/v1','company'=>$name,'rows'=>[['day'=>'2026-11-17','price'=>'10']]];
            }
        };
    }
    require __DIR__ . '/../core/company_history.php';
    register_shutdown_function(function () { echo '\nSTATUS:' . (http_response_code() ?: 200); });
    $source = file_get_contents(__DIR__ . '/../handlers/company_history.php');
    $source = preg_replace('/^require_once .*$/m', '', $source);
    eval('?>' . $source);
    exit;
}
foreach (['ok'=>200,'post'=>405,'guest'=>401,'array'=>400,'extra'=>400,'failure'=>503] as $case=>$status) {
    $output = shell_exec(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(__FILE__) . ' ' . escapeshellarg($case));
    if (!str_contains($output, 'STATUS:' . $status) || str_contains($output, 'private-diagnostic')) {
        throw new RuntimeException('History HTTP regression failed: ' . $case);
    }
}
echo "Company history HTTP validation, auth and failure cases passed.\n";
