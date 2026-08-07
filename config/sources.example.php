<?php
/**
 * Template for config/sources.php, which holds the upstream data-source
 * endpoints and is never committed. Copy this file to sources.php and fill in
 * the real hosts, then upload sources.php to the host by hand.
 *
 * SRC_MARKET_* is the live quote / market-status feed used by index.php.
 * SRC_FUND_*   is the fundamentals feed used by handlers/market_proxy.php.
 * Both upstreams reject requests whose Origin/Referer is not their own host,
 * which is why the origin is configured separately from the API root.
 */

define('SRC_MARKET_API',    'https://example.invalid/api/');
define('SRC_MARKET_ORIGIN', 'https://example.invalid');

define('SRC_FUND_BASE',     'https://example.invalid/api/proxy');
define('SRC_FUND_ORIGIN',   'https://example.invalid');
