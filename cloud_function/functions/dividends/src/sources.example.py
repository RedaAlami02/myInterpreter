"""Template for sources.py, which is gitignored and holds the real endpoints.

Copy this file to sources.py and fill in the dividend calendar you have access
to, then deploy. sources.py is not committed but IS uploaded by the Appwrite
CLI, which packages the whole function directory.

CALENDAR_URL is a format string taking {year}. The parser expects an HTML page
with one table whose rows are seven cells:

    issuer | amount (MAD) | yield % | ex-date | payment date | type | frequency

CALENDAR_SOURCE_NAME is written verbatim into the `source` field of every
dividend row, so changing it makes new rows disagree with old ones.

FUNDAMENTALS_* is the second, independent feed used only to cross-check
amounts; leave it as the placeholder to skip the cross-check.
"""

CALENDAR_URL         = "https://example.invalid/calendrier-des-dividendes/annee/{year}/"
CALENDAR_SOURCE_NAME = "calendar"

FUNDAMENTALS_SUPABASE = "https://example.invalid/api/proxy/supabase"
FUNDAMENTALS_ORIGIN   = "https://example.invalid"
