<?php
// CLI-only, explicit audited-company update. Never deploy this tool.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require __DIR__ . '/../config/config.php';
require __DIR__ . '/../core/Appwrite.php';
require __DIR__ . '/../core/SupabaseApp.php';
require __DIR__ . '/../core/SupabaseMarket.php';
require __DIR__ . '/../core/SupabaseAdmin.php';
require __DIR__ . '/../core/company_disclosures.php';
require __DIR__ . '/ReviewedCompany.php';

try {
    $symbol = $argv[1] ?? '';
    $apply = in_array('--apply', $argv, true);
    $review = reviewed_company_disclosure($symbol);
    if (!$review) throw new RuntimeException('No reviewed disclosure for this symbol');
    $email = getenv('MI_ADMIN_EMAIL');
    $password = getenv('MI_ADMIN_PASSWORD');
    if (!is_string($email) || $email === '' || !is_string($password) || $password === '') {
        throw new RuntimeException('Set MI_ADMIN_EMAIL and MI_ADMIN_PASSWORD');
    }
    $tokens = sb_app()->signIn($email, $password);
    $token = $tokens['access_token'] ?? null;
    if (!is_string($token) || $token === '') {
        throw new RuntimeException('Administrator sign-in did not return a session');
    }
    try {
        $result = (new ReviewedCompany(
            new SupabaseMarketReader(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY, null, $token),
            new SupabaseAdminClient(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY),
            $token
        ))->apply($review, $symbol, $apply);
    } finally {
        try {
            sb_app()->signOut($token);
        } catch (Throwable $ignored) {
            // The operator's session expires on its own.
        }
    }
    echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . PHP_EOL;
    exit(0);
} catch (SupabaseRequestException $error) {
    fwrite(STDERR, 'Request rejected (' . $error->httpStatus . '); check administrator access.' . PHP_EOL);
} catch (Throwable $error) {
    fwrite(STDERR, $error->getMessage() . PHP_EOL);
}
exit(1);
