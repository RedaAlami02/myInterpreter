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
/**
 * Short-lived per-session memo for reads a page repeats on every visit.
 *
 * Entries live in the PHP session, so they are scoped to one signed-in account
 * and disappear at logout. Only data that does not depend on the account may be
 * cached; portfolio rows are stored under a key that includes the user id and
 * every write path must forget it.
 */
function app_cache(string $key, int $ttl, callable $producer, bool $bypass = false): mixed {
    $entry = $_SESSION['app_cache'][$key] ?? null;
    $stats = $GLOBALS['app_cache_stats'] ?? [];
    if (!$bypass && is_array($entry) && array_key_exists('value', $entry)
        && ($entry['at'] ?? 0) > time() - $ttl) {
        // Surfaced by ?timing=1: the age of the entry actually reused, so a
        // slow stage can be told apart from one that was never stored.
        $stats[] = '+' . (time() - (int) ($entry['at'] ?? 0)) . 's';
        $GLOBALS['app_cache_stats'] = $stats;
        return $entry['value'];
    }
    if ($bypass) {
        $stats[] = '=post';
    } elseif (!is_array($entry)) {
        $stats[] = '-none';
    } else {
        $stats[] = '!' . (time() - (int) ($entry['at'] ?? 0)) . 's/' . $ttl . 's';
    }
    $GLOBALS['app_cache_stats'] = $stats;
    $value = $producer();
    $_SESSION['app_cache'][$key] = ['at' => time(), 'value' => $value];
    return $value;
}

/** Drop memo entries whose key starts with $prefix (e.g. after a trade). */
function app_cache_forget(string $prefix): void {
    foreach (array_keys($_SESSION['app_cache'] ?? []) as $key) {
        if (str_starts_with((string) $key, $prefix)) unset($_SESSION['app_cache'][$key]);
    }
}

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
        // In call order: "+Ns" a hit aged N seconds, "-none" no entry at all,
        // "!Ns/Ts" an entry older than its T, "=post" a write worth skipping.
        $cache = $GLOBALS['app_cache_stats'] ?? [];
        echo "\n<!-- timing: " . implode(' ', $parts)
            . ' total=' . (int) round(($last - $first) * 1000) . "ms"
            . ($cache !== [] ? ' cache=' . implode(',', $cache) : '') . " -->\n";
    });
}
