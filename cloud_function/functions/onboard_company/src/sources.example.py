"""Template for sources.py, which is gitignored and holds the real endpoints.

Copy this file to sources.py and fill in the fundamentals API you have access
to, then deploy. sources.py is not committed but IS uploaded by the Appwrite
CLI, which packages the whole function directory.

FUNDAMENTALS_BASE is the REST root; the Supabase-backed table endpoint hangs
off "{FUNDAMENTALS_BASE}/supabase". The upstream returns 403 without a
same-origin Referer/Origin, hence FUNDAMENTALS_ORIGIN.

Keep in sync with handlers/market_proxy.php on the PHP side, which reads the
same two values from config/sources.php.
"""

FUNDAMENTALS_BASE   = "https://example.invalid/api/proxy"
FUNDAMENTALS_ORIGIN = "https://example.invalid"
