"""Explicit short-lived capture recovery; never alters reported event dates."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

def slot(now, until):
    if not until or now.tzinfo is None:
        return None
    try:
        expiry = datetime.fromisoformat(until)
    except (TypeError, ValueError):
        return None
    if expiry.tzinfo is None or not now < expiry <= now + timedelta(minutes=30):
        return None
    local = now.astimezone(ZoneInfo('Africa/Casablanca'))
    if local.weekday() >= 5:
        return None
    return local.replace(minute=local.minute//15*15,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
