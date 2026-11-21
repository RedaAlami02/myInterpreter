<?php
/** Explicit runtime selection. Migration credentials are never loaded by the site. */
$localBackend = [];
if (is_file(__DIR__ . '/../config/supabase.local.php')) {
    $localBackend = require __DIR__ . '/../config/supabase.local.php';
    if (!is_array($localBackend)) throw new RuntimeException('Invalid backend configuration.');
}
$selectedBackend = getenv('MYINTERPRETER_BACKEND') ?: ($localBackend['backend'] ?? 'supabase');
if ($selectedBackend !== 'supabase') throw new RuntimeException('The retired backend is unavailable. Configure Supabase.');
define('MYINTERPRETER_BACKEND', $selectedBackend);
define('SUPABASE_PROJECT_URL', getenv('SUPABASE_PROJECT_URL') ?: ($localBackend['url'] ?? ''));
define('SUPABASE_PUBLISHABLE_KEY', getenv('SUPABASE_PUBLISHABLE_KEY') ?: ($localBackend['publishable_key'] ?? ''));
define('SUPABASE_ADMIN_USER_ID', getenv('SUPABASE_ADMIN_USER_ID') ?: ($localBackend['admin_user_id'] ?? ''));
$anonymousSetting = getenv('SUPABASE_ALLOW_ANONYMOUS_MARKET');
if ($anonymousSetting === false) $anonymousSetting = $localBackend['allow_anonymous_market'] ?? false;
if (!in_array($anonymousSetting, [true,false,'true','false'], true)) throw new RuntimeException('Invalid anonymous market setting.');
define('SUPABASE_ALLOW_ANONYMOUS_MARKET', $anonymousSetting === true || $anonymousSetting === 'true');
unset($anonymousSetting);
define('MYINTERPRETER_PUBLIC_URL', getenv('MYINTERPRETER_PUBLIC_URL') ?: ($localBackend['public_url'] ?? 'https://myinterpreter.infinityfree.me'));
$marketPreviewSetting = getenv('MYINTERPRETER_MARKET_PREVIEW');
if ($marketPreviewSetting === false) $marketPreviewSetting = $localBackend['market_preview'] ?? false;
if (!in_array($marketPreviewSetting, [true,false,'true','false'], true)) throw new RuntimeException('Invalid market preview setting.');
define('MYINTERPRETER_MARKET_PREVIEW', $marketPreviewSetting === true || $marketPreviewSetting === 'true');
$recurringSetting = getenv('MYINTERPRETER_RECURRING_FEED');
if ($recurringSetting === false) $recurringSetting = $localBackend['recurring_feed'] ?? false;
if (!in_array($recurringSetting, [true,false,'true','false'], true)) throw new RuntimeException('Invalid recurring feed setting.');
define('MYINTERPRETER_RECURRING_FEED', $recurringSetting === true || $recurringSetting === 'true');
unset($recurringSetting);
$valuationSetting = getenv('MYINTERPRETER_PORTFOLIO_VALUATION');
if ($valuationSetting === false) $valuationSetting = $localBackend['portfolio_valuation'] ?? false;
if (!in_array($valuationSetting, [true,false,'true','false'], true)) throw new RuntimeException('Invalid portfolio valuation setting.');
define('MYINTERPRETER_PORTFOLIO_VALUATION', $valuationSetting === true || $valuationSetting === 'true');
$directSourceSetting = getenv('MYINTERPRETER_DIRECT_SOURCE_REQUESTS');
if ($directSourceSetting === false) $directSourceSetting = 'false';
if (!in_array($directSourceSetting, ['true','false'], true)) throw new RuntimeException('Invalid direct source setting.');
define('MYINTERPRETER_DIRECT_SOURCE_REQUESTS', $directSourceSetting === 'true');
unset($directSourceSetting);
unset($valuationSetting);
unset($marketPreviewSetting);
unset($localBackend, $selectedBackend);

function app_uses_supabase(): bool { return MYINTERPRETER_BACKEND === 'supabase'; }

function sb_app(): SupabaseAppClient {
    require_once __DIR__ . '/SupabaseApp.php';
    static $client;
    return $client ??= new SupabaseAppClient(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY, null, true);
}

function sb_market(): SupabaseMarketReader {
    require_once __DIR__ . '/SupabaseMarket.php';
    static $reader;
    $anonymous = defined('SUPABASE_ALLOW_ANONYMOUS_MARKET')
        && SUPABASE_ALLOW_ANONYMOUS_MARKET === true;
    return $reader ??= new SupabaseMarketReader(
        SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY, null, sb_access_token(),
        MYINTERPRETER_RECURRING_FEED, $anonymous);
}

function sb_market_preview(): ShadowMarketSnapshot {
    if (!MYINTERPRETER_MARKET_PREVIEW) throw new RuntimeException('Market preview is disabled.');
    require_once __DIR__ . '/ShadowMarketFeed.php';
    return (new ShadowMarketFeedReader(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY,
        sb_access_token(), null, true, MYINTERPRETER_RECURRING_FEED))->read();
}

function sb_admin(): SupabaseAdminClient {
    require_once __DIR__ . '/SupabaseAdmin.php';
    static $client;
    return $client ??= new SupabaseAdminClient(SUPABASE_PROJECT_URL, SUPABASE_PUBLISHABLE_KEY);
}

require_once __DIR__ . '/supabase_session.php';

/**
 * Opt-in render timing: add ?timing=1 to a page and the response ends with an
 * HTML comment giving milliseconds between marks. Nothing is emitted without
 * the parameter, and no personal data is involved.
 */
function app_timing_mark(string $label): void {
    if (($_GET['timing'] ?? '') !== '1') return;
    $GLOBALS['app_timing_marks'][$label] = microtime(true);
}

if (($_GET['timing'] ?? '') === '1') {
    app_timing_mark('start');
    register_shutdown_function(static function (): void {
        $marks = $GLOBALS['app_timing_marks'] ?? [];
        if (count($marks) < 2) return;
        $parts = [];
        $previous = null;
        foreach ($marks as $label => $at) {
            $parts[] = $previous === null
                ? $label
                : $label . '=' . (int) round(($at - $previous) * 1000) . 'ms';
            $previous = $at;
        }
        $first = reset($marks);
        $last  = end($marks);
        echo "\n<!-- timing: " . implode(' ', $parts)
            . ' total=' . (int) round(($last - $first) * 1000) . "ms -->\n";
    });
}
