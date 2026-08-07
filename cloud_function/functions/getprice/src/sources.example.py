"""Template for sources.py, which is gitignored and holds the real endpoints.

Copy this file to sources.py and fill in the market data API you have access
to, then deploy. sources.py is not committed but IS uploaded by the Appwrite
CLI, which packages the whole function directory.

The upstream rejects requests whose Origin/Referer is not its own host, which
is why the origin is configured separately from the API URL.
"""

MARKET_API_URL = "https://example.invalid/api/"
MARKET_ORIGIN  = "https://example.invalid"
