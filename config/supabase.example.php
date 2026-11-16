<?php
// Copy to config/supabase.local.php (ignored) OR supply environment variables.
// Public key only. Never place the database URL or secret key in site config.
return [
    'public_url' => 'https://myinterpreter.infinityfree.me',
    'backend' => 'supabase',
    'url' => 'https://YOUR_PROJECT_REF.supabase.co',
    'publishable_key' => 'sb_publishable_REPLACE_LOCALLY',
    // New Supabase Auth user UUID; blank means no web administrator.
    'admin_user_id' => '',
    // Leave off until the approved session-price writer is installed/accepted.
    'portfolio_valuation' => false,
    // Opt-in public read-only market tables. Requires the
    // 20261116_public_market_anon_read.sql migration; default off.
    'allow_anonymous_market' => false,
];
