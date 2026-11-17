<?php
require_once __DIR__ . '/../core/SupabaseMarket.php';
require_once __DIR__ . '/../core/SupabaseAdmin.php';
require_once __DIR__ . '/../tools/ReviewedCompany.php';

function checkReviewed(bool $condition, string $description): void {
    if (!$condition) throw new RuntimeException($description);
}
$url = 'https://abcdefghijklmnopqrst.supabase.co';
$key = 'sb_publishable_fixture_only';
$jwt = 'fixture.user.signature';

function harness(array $rows, bool $applyChanges = true): array {
    global $url, $key, $jwt;
    $state = new stdClass();
    $state->rows = $rows;
    $state->calls = [];
    $state->committed = false;
    $reader = new SupabaseMarketReader($url, $key, static function ($requestUrl, $headers) use (&$state): array {
        checkReviewed(str_contains(implode(' ', $headers), 'Authorization: Bearer ' . $GLOBALS['jwt']), 'Reader token missing.');
        parse_str(parse_url($requestUrl, PHP_URL_QUERY) ?? '', $params);
        checkReviewed(($params['name'] ?? '') === 'eq.Alpha', 'Company filter changed.');
        return ['status' => 200, 'body' => json_encode($state->rows), 'headers' => []];
    }, $jwt);
    $admin = new SupabaseAdminClient($url, $key, static function ($method, $requestUrl, $headers, $body) use (&$state, $applyChanges): array {
        $payload = json_decode($body, true);
        $state->calls[] = [$method, $requestUrl, $payload];
        checkReviewed(str_ends_with($requestUrl, '/rpc/admin_update_company'), 'Wrong RPC.');
        checkReviewed(!isset($payload['user_id']) && !isset($payload['p_user_id']), 'Ownership must be database-derived.');
        if ($applyChanges) {
            foreach ($payload['p_fields'] as $field => $value) {
                $state->rows[0][$field] = $value;
            }
            $state->committed = true;
            return ['status' => 200, 'body' => json_encode([
                'status' => 'UPDATED', 'name' => 'Alpha', 'fields' => count($payload['p_fields']),
            ])];
        }
        return ['status' => 200, 'body' => json_encode(['status' => 'UPDATED', 'name' => 'Alpha', 'fields' => 1])];
    });
    return [new ReviewedCompany($reader, $admin, $jwt), $state];
}

function company(array $overrides = []): array {
    return array_merge([
        'id' => 'c1', 'name' => 'Alpha', 'bpa' => 5, 'fiscal_year' => 2023,
        'ext_name' => 'Old name', 'sector' => 'Banks',
    ], $overrides);
}

function review(?array $fields = null): array {
    return [
        'name' => 'Alpha',
        'fields' => $fields ?? ['bpa' => 12.5, 'fiscal_year' => 2023, 'ext_name' => 'Alpha SA'],
    ];
}

[$dry, $state] = harness([company()]);
$summary = $dry->apply(review(), 'AAA', false);
checkReviewed($summary['changes'] === ['bpa', 'ext_name'], 'Dry-run change set changed.');
checkReviewed($summary['applied'] === false && $summary['backup'] === null, 'Dry run must not write.');
checkReviewed($state->calls === [], 'Dry run called the database.');

[$apply, $state] = harness([company()]);
$summary = $apply->apply(review(), 'AAA', true);
checkReviewed($summary['applied'] === true, 'Apply did not commit.');
checkReviewed(count($state->calls) === 1, 'Unexpected number of writes.');
checkReviewed($state->calls[0][2]['p_fields'] === ['bpa' => 12.5, 'ext_name' => 'Alpha SA'], 'Written fields changed.');
checkReviewed(is_string($summary['backup']) && is_file($summary['backup']), 'Backup missing.');
checkReviewed((fileperms($summary['backup']) & 0o077) === 0, 'Backup is not private.');
$restored = json_decode(file_get_contents($summary['backup']), true);
checkReviewed(($restored['bpa'] ?? null) == 5, 'Backup does not hold the previous row.');
unlink($summary['backup']);

[$same, $state] = harness([company(['bpa' => 12])]);
$summary = $same->apply(review(['fiscal_year' => 2023, 'bpa' => 12.0]), 'AAA', true);
checkReviewed($summary['changes'] === [] && $summary['applied'] === false, 'Numeric equivalence wrote a change.');
checkReviewed($state->calls === [], 'Unchanged row was written.');

foreach ([
    'zero rows' => [[], review()],
    'duplicate rows' => [[company(), company(['id' => 'c2'])], review()],
    'newer stored year' => [[company(['fiscal_year' => 2024])], review()],
] as $label => [$rows, $reviewed]) {
    [$subject, $state] = harness($rows);
    $failed = false;
    try {
        $subject->apply($reviewed, 'AAA', true);
    } catch (RuntimeException $error) {
        $failed = true;
    }
    checkReviewed($failed, 'Unsafe case accepted: ' . $label);
    checkReviewed($state->calls === [], 'Unsafe case wrote: ' . $label);
}

[$mismatch, $state] = harness([company()], false);
$failed = false;
try {
    $mismatch->apply(review(), 'AAA', true);
} catch (RuntimeException $error) {
    $failed = str_contains($error->getMessage(), 'Read-back mismatch');
}
checkReviewed($failed, 'Read-back mismatch was accepted.');

[$missing, $state] = harness([company()]);
$missingRow = false;
try {
    $missing->apply(review(['fiscal_year' => 2023, 'bpa' => 1.0]), 'AAA', true);
} catch (RuntimeException $error) {
    $missingRow = true;
}
checkReviewed(!$missingRow, 'Valid apply failed unexpectedly.');

[$invalid, $state] = harness([company()]);
foreach ([[], ['name' => '', 'fields' => ['bpa' => 1]], ['name' => 'Alpha', 'fields' => []]] as $bad) {
    $failed = false;
    try {
        $invalid->apply($bad, 'AAA', false);
    } catch (InvalidArgumentException $error) {
        $failed = true;
    }
    checkReviewed($failed, 'Invalid disclosure accepted.');
}
echo "Reviewed company update tests passed.\n";
