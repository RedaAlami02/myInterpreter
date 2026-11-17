"""Exact-decimal daily-report reader; parsing never approves or writes valuations.

The report layout follows the existing retained parser. Source configuration,
identity bindings and authority approval remain separate private inputs.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

MAX_BYTES = 8 * 1024 * 1024
_SPLIT = re.compile(r'\s{2,}')
_ISIN = re.compile(r'\b(MA[0-9]{10})\b')


class CloseError(ValueError):
    pass


def decimal_token(token):
    value = token.replace('\u00a0', '').replace('\u202f', '').replace(' ', '').strip()
    if value in {'', '-'}:
        return None
    if not re.fullmatch(r'[0-9]+(?:[,.][0-9]{1,8})?', value):
        raise CloseError('INVALID_CLOSE_NUMBER')
    try:
        number = Decimal(value.replace(',', '.'))
    except InvalidOperation:
        raise CloseError('INVALID_CLOSE_NUMBER') from None
    if not 0 < number <= Decimal('1000000000000'):
        raise CloseError('INVALID_CLOSE_NUMBER')
    return format(number, 'f')


def parse_text(text, session_day, raw_sha256):
    """Keep missing closes explicit and reject wrong-day/conflicting documents."""
    if not isinstance(session_day, str) or date.fromisoformat(session_day).isoformat() != session_day:
        raise CloseError('INVALID_SESSION_DAY')
    if not re.fullmatch('[a-f0-9]{64}', raw_sha256):
        raise CloseError('INVALID_RAW_HASH')
    matches = re.findall(r'S[ée]ance du (\d{2}/\d{2}/\d{4})', text)
    expected = date.fromisoformat(session_day).strftime('%d/%m/%Y')
    if not matches or set(matches) != {expected}:
        raise CloseError('REPORT_SESSION_MISMATCH')
    if not re.search(r'Cl[ôo]t', text):
        raise CloseError('CLOSE_COLUMN_MISSING')
    rows = []
    seen = set()
    for line_number, line in enumerate(text.splitlines()):
        hit = _ISIN.search(line)
        if not hit:
            continue
        before = _SPLIT.split(line[:hit.start()].strip())
        after = _SPLIT.split(line[hit.end():].strip())
        # Some equity rows join the last traded price and date with one space.
        # Expand only this exact table shape; retain the primary-table boundary.
        if len(before) == 6:
            joined = re.fullmatch(r'([0-9][0-9\u00a0\u202f ]*(?:[,.][0-9]+)?) (\d{2}/\d{2}/\d{2})', before[-2])
            if joined:
                before[-2:-1] = [joined[1], joined[2]]
        # Preserve the established primary-equity table boundary. Other tables
        # can contain identifiers but are not silently promoted to equity closes.
        if len(before) < 7 or len(after) < 6 or not after[0] or after[0][0].isdigit():
            continue
        identity = hit.group(1)
        if identity in seen:
            raise CloseError('DUPLICATE_REPORT_IDENTITY')
        seen.add(identity)
        close = decimal_token(after[2])
        reference = decimal_token(before[-1])
        if close is not None and (reference is None or Decimal(close) != Decimal(reference)):
            raise CloseError('REPORT_CLOSE_REFERENCE_CONFLICT')
        observation_id = hashlib.sha256(f'{raw_sha256}:{line_number}:{identity}'.encode()).hexdigest()
        rows.append({'isin': identity, 'designation': after[0],
                     'price_decimal': close, 'next_reference_decimal': reference,
                     'status': after[5], 'raw_line_index': line_number,
                     'observation_id': observation_id, 'raw_sha256': raw_sha256,
                     'availability': 'AVAILABLE' if close is not None else 'MISSING_CLOSE'})
    if not rows or not any(row['price_decimal'] is not None for row in rows):
        raise CloseError('NO_OFFICIAL_CLOSES')
    return {'contract': 'daily-report-closes/v1', 'session_day': session_day,
            'raw_sha256': raw_sha256, 'rows': rows,
            'price_basis': 'OFFICIAL_CLOSE_COLUMN',
            'approval': 'REQUIRES_REVIEWED_SOURCE_AND_IDENTITY_BINDING',
            'published_at': None, 'session_close_at': None}


def parse_pdf(raw, session_day):
    if not isinstance(raw, bytes) or not 10_000 <= len(raw) <= MAX_BYTES or not raw.startswith(b'%PDF'):
        raise CloseError('INVALID_REPORT_BYTES')
    with tempfile.TemporaryDirectory(prefix='private-close-') as folder:
        source = Path(folder) / 'report.pdf'
        source.write_bytes(raw)
        try:
            result = subprocess.run(['pdftotext', '-layout', str(source), '-'],
                                    capture_output=True, timeout=20, check=True)
            if len(result.stdout) > 4 * MAX_BYTES:
                raise CloseError('REPORT_TEXT_TOO_LARGE')
            text = result.stdout.decode('utf-8')
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise CloseError('REPORT_TEXT_EXTRACTION_FAILED') from None
    return parse_text(text, session_day, hashlib.sha256(raw).hexdigest())
