"""Payment-period validation shared with the PHP/Dart fixture contract."""
from datetime import date
import re


def verification_issue(row):
    year = row.get('year', 0)
    if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 9999:
        return 'invalid_payment_year'
    dates = {}
    for field in ('ex_date', 'pay_date', 'pay_date_end'):
        value = (row.get(field) or '').strip()
        if not value:
            continue
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return 'invalid_calendar_date'
            parsed = date.fromisoformat(value)
        except ValueError:
            return 'invalid_calendar_date'
        dates[field] = parsed
        if field != 'ex_date' and parsed.year != year:
            return 'payment_year_mismatch'
    ex, pay, end = (dates.get(field) for field in ('ex_date', 'pay_date', 'pay_date_end'))
    if ex and ex.year != year and not (pay and ex.year == year-1):
        return 'payment_year_mismatch'
    if (ex and pay and pay < ex) or (end and (not pay or end < pay)):
        return 'invalid_date_order'
    if row.get('confirmed') and not ex:
        return 'missing_confirmation_date'
    return None
