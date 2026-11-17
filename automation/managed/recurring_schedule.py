"""Versioned recurring application cadence, explicitly in Casablanca wall time."""
from datetime import timezone
from zoneinfo import ZoneInfo

CONTRACT = 'recurring-casablanca/v1'
ZONE = ZoneInfo('Africa/Casablanca')


def slot(now, kind):
    if now.tzinfo is None or kind not in {'quotes','depth','dividends','fundamentals','official_close'}:
        raise ValueError('INVALID_RECURRING_SCHEDULE_INPUT')
    local = now.astimezone(ZONE)
    if local.weekday() >= 5:
        return None
    if kind in {'quotes','depth'}:
        if not 9 <= local.hour < 17:
            return None
        interval = 15 if kind == 'quotes' else 5
        return local.replace(minute=local.minute//interval*interval,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
    if kind == 'official_close' and not (17 <= local.hour < 19 and (local.hour != 17 or local.minute >= 35)):
        return None
    if kind == 'dividends' and not (local.weekday() == 0 and local.hour == 7):
        return None
    if kind == 'fundamentals' and not 17 <= local.hour < 19:
        return None
    return local.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()


def due(now):
    return [kind for kind in ['official_close','quotes','depth','dividends','fundamentals'] if slot(now,kind) is not None
            and (kind != 'quotes' or now.astimezone(ZONE).minute % 15 < 5)]
