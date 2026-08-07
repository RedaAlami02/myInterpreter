"""Parser for the upstream dividend calendar.

Kept separate from main.py so the same code serves the scheduled function and
the one-off backfill script, and so it can be tested without Appwrite.

Named `div_parser` rather than the obvious `parser`: Python 3.9 — the Appwrite
runtime — still ships a built-in `parser` C extension, which shadows a local
file of that name and makes the import fail at load time. It does not reproduce
on a modern local Python, where the module was removed, so this only surfaced
on a real execution.

Source shape (verified stable across the 2022-2026 calendars — identical header
and exactly 7 cells in every one of the ~300 rows):

    Émetteur | Montant (MAD) | Dividende % | Détachement | Paiement | Type | Fréquence

Two things about this source drive the design:

  * It distinguishes confirmed from estimated itself. A confirmed entry has a
    real ex-date and a single payment date; an unannounced one leaves the
    ex-date blank and gives the payment as a *range* ("23/09/2026 – 29/09/2026").
    We carry that distinction through rather than inventing our own prediction —
    measured year-over-year drift of the ex-date is a 7-day median with a 26%
    tail beyond two weeks, so our own guess would be worse than theirs.

  * A calendar year's dividend is paid out of the *previous* fiscal year. The
    2026 amounts match the fundamentals feed's dpa-corpo 2025 column exactly,
    which is what makes the cross-check in main.py possible.
"""

import html
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sources import CALENDAR_URL as CAL_URL
except ImportError:  # no sources.py — copy sources.example.py, or set this in
    # the function's environment variables (Console → Settings → Variables).
    CAL_URL = os.environ.get("CALENDAR_URL", "")

DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4})')
CELL_RE = re.compile(r'<t[dh].*?</t[dh]>', re.S)
ROW_RE = re.compile(r'<tr.*?</tr>', re.S)
TABLE_RE = re.compile(r'<table.*?</table>', re.S)

# The yield and date cells carry a tooltip whose text is concatenated into the
# cell by the tag strip ("Cours action : 1 279,00 MAD Calcul: 4,85 %"). Cut it
# off at the first tooltip marker rather than trying to match the tooltip markup,
# which changes more often than this prose does.
TOOLTIP_CUT = re.compile(
    r'\s*(Date de détachement|Cours action|Calcul\s*:|Cours au détachement)', re.I)

# Some issuers are written with their ticker appended: "MAROC TELECOM (IAM)".
TICKER_SUFFIX = re.compile(r'\s*\(([A-Z0-9]{2,6})\)\s*$')


def _clean(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', fragment))).strip()


def _amount(text: str):
    """French-formatted money to float. '1 279,00' -> 1279.0, '—' -> None."""
    t = text.replace('\xa0', '').replace(' ', '').replace(' ', '')
    # French format: comma is the decimal mark, dot groups thousands. Only treat
    # a dot as a group separator when a comma proves the format is French —
    # otherwise a future '8.44' would silently become 844.
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    t = re.sub(r'[^\d.\-]', '', t)
    if not t or t in ('.', '-'):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def _iso(d: str):
    """'04/09/2026' -> '2026-09-04'."""
    m = DATE_RE.search(d or '')
    if not m:
        return None
    dd, mm, yy = m.group(1).split('/')
    return f"{yy}-{mm}-{dd}"


def normalise_name(s: str) -> str:
    """Fold an issuer name to a comparison key.

    Strips accents, case, punctuation and the corporate-suffix noise that the
    two sources disagree about ('Total Energies Maroc' vs 'TOTALENERGIES',
    'AtlantaSanad Assurance' vs 'ATLANTASANAD'). Measured 59/61 exact matches
    against the company collection; the remaining two are handled by ALIASES.
    """
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = TICKER_SUFFIX.sub('', s)          # "MINIERE TOUISSIT (CMT)" -> "MINIERE TOUISSIT"
    s = re.sub(r'\b(S\.?A\.?|SA|GROUP|GROUPE|ASSURANCES?|MAROC|DU MAROC|AUTOMOBILES?'
               r'|DE|DU|DES|D)\b', '', s)  # French particles: "Miniere de Touissit"
    return re.sub(r'[^A-Z0-9]', '', s)


def ticker_of(name: str):
    """The ticker some issuer names carry in brackets: 'MAROC TELECOM (IAM)' -> 'IAM'."""
    m = TICKER_SUFFIX.search(unicodedata.normalize('NFKD', name or '')
                             .encode('ascii', 'ignore').decode().upper())
    return m.group(1) if m else None


# The two issuers whose names share no normalised form with ours. Mirrors
# COMPANY_ALIASES in config/config.php — keep the two in step.
ALIASES = {
    normalise_name('MAROC TELECOM'): 'IAM',
    normalise_name('Total Energies Maroc'): 'TOTALENERGIES MAROC',
}


def parse_calendar(page: str, year: int) -> list:
    """Rows from one calendar page. Raises if the page shape is not what we expect.

    Raising matters: a silent empty list here would look exactly like "no company
    paid a dividend this year", which is the failure mode this whole audit has
    been about.
    """
    tables = TABLE_RE.findall(page)
    if not tables:
        raise ValueError(f"no <table> in the {year} calendar — page shape changed")

    rows = ROW_RE.findall(tables[0])
    if len(rows) < 2:
        raise ValueError(f"{year} calendar table has no data rows")

    header = [_clean(c) for c in CELL_RE.findall(rows[0])]
    if len(header) != 7 or 'metteur' not in header[0]:
        raise ValueError(f"{year} calendar header changed: {header}")

    out = []
    for r in rows[1:]:
        cells = [_clean(c) for c in CELL_RE.findall(r)]
        if len(cells) < 7:
            continue

        name = cells[0].strip()
        if not name:
            continue

        ex_dates = DATE_RE.findall(cells[3])
        pay_dates = DATE_RE.findall(cells[4])

        # An ex-date is the source's own marker that the AGM has voted. Without
        # it the payment window is their estimate, not a commitment.
        confirmed = bool(ex_dates)

        out.append({
            'issuer':      name,
            'key':         normalise_name(name),
            'ticker':      ticker_of(name),
            'year':        year,
            'amount':      _amount(cells[1]),
            'yield_src':   TOOLTIP_CUT.split(cells[2])[0].strip() or None,
            'ex_date':     _iso(ex_dates[0]) if ex_dates else None,
            'pay_date':    _iso(pay_dates[0]) if pay_dates else None,
            'pay_date_end': _iso(pay_dates[1]) if len(pay_dates) > 1 else None,
            'confirmed':   confirmed,
            'type':        cells[5] or None,
            'frequency':   cells[6] or None,
        })
    return out


def resolve(key: str, index: dict, ticker: str = None):
    """Map a normalised issuer key to our stored company name, or None.

    Falls back to the bracketed ticker, which `index` also carries via the
    `format` collection's symbols — that is what rescues "MAROC TELECOM (IAM)"
    when the name itself normalises to something we do not store.
    """
    if key in ALIASES:
        return ALIASES[key]
    hit = index.get(key)
    if hit:
        return hit
    return index.get(normalise_name(ticker)) if ticker else None


def dedupe(rows: list) -> list:
    """Collapse the source's own duplicate listings.

    The calendar lists some issuers twice under two spellings — one complete entry
    and one dateless stub:

        AFMA      54,00  ex=None         <- stub
        AFMA SA   54,00  ex=12/07/2022   <- real

    Present in 2022-2024 and cleaned up by 2025, but it can recur, and storing
    both would double-count the holding in the portfolio income panel.

    A company can legitimately have several rows in one year (an ordinary and an
    exceptional dividend), so the grouping key includes `type`; only rows that
    agree on company, year *and* type are treated as the same payment. Within a
    group the most complete row wins: confirmed beats unconfirmed, having a
    payment date beats not having one.
    """
    best = {}
    for r in rows:
        gk = (r.get('c_name') or r['key'], r['year'], r['type'])
        rank = (bool(r['confirmed']), bool(r['pay_date']), bool(r['amount']))
        if gk not in best or rank > best[gk][0]:
            best[gk] = (rank, r)
    return [r for _, r in best.values()]
