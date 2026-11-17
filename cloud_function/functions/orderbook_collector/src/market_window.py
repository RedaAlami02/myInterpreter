"""The Casablanca session window, resolved without trusting this container's clock.

Why this is not just `ZoneInfo("Africa/Casablanca")`
---------------------------------------------------
Morocco moved from UTC+1 to UTC+0 on 2026-09-20. This function's container
carries an older time zone database and still resolves the zone to UTC+1, so a
gate written as `"09:00" <= local <= "15:55"` opened at 08:00 UTC and closed at
14:55 UTC. The result was an hour of pre-open noise at the start and, far worse,
no capture at all of the closing auction or the Closing Price Cross — the
collector's own run log shows it refusing at 15:34, 15:39, 15:44, 15:49, 15:54
and 15:59 UTC on 2026-09-28, when the session was still open.

The fix is not an offset constant. A hardcoded `+1` or `-1` would be wrong the
next time Morocco changes, and silently so. Instead the authoritative IANA rule
is vendored beside this file as a compiled TZif binary — the same transition
data the host uses — and read with `ZoneInfo.from_file`, which bypasses whatever
the container happens to have installed.

So the offset is derived from the date, per the authoritative rule, and the
window is handed to the caller as explicit UTC instants.

Every run reports which zone source it actually used, so a container that
quietly stopped shipping the vendored file is visible in the log rather than
inferred from a wrong capture window.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


TZ_FILE = Path(__file__).with_name("tzdata") / "Africa_Casablanca"

# The session as the operator declares it, in Casablanca local time. These are
# clock readings, not offsets; the zone data decides what they mean in UTC.
SESSION_START_LOCAL = time(9, 0)
SESSION_CLOSE_LOCAL = time(15, 55)

OPEN = "OPEN"
CLOSED_BEFORE_OPEN = "CLOSED_BEFORE_OPEN"
CLOSED_AFTER_CLOSE = "CLOSED_AFTER_CLOSE"
CLOSED_NON_SESSION_DAY = "CLOSED_NON_SESSION_DAY"


def load_zone() -> tuple[ZoneInfo, str, str]:
    """The zone, where it came from, and its digest. Never raises."""
    if TZ_FILE.exists():
        try:
            with TZ_FILE.open("rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            with TZ_FILE.open("rb") as handle:
                return ZoneInfo.from_file(handle, key="Africa/Casablanca"), "VENDORED_TZIF", digest
        except Exception:
            pass
    try:
        # Deliberately a fallback, and deliberately labelled: if this path is
        # taken the container's stale data is in play again and the gate may be
        # an hour out, which is exactly the condition worth seeing in the log.
        return ZoneInfo("Africa/Casablanca"), "CONTAINER_TZDATA", ""
    except Exception:
        return ZoneInfo("UTC"), "UTC_FALLBACK", ""


def market_mode(on_date: date, ramadan_periods: list[dict] | None = None) -> str:
    for period in ramadan_periods or []:
        try:
            if date.fromisoformat(period["start"]) <= on_date <= date.fromisoformat(period["end"]):
                return "RAMADAN"
        except (KeyError, ValueError):
            continue
    return "NORMAL"


def session_window(on_date: date, *, ramadan_periods: list[dict] | None = None,
                   zone: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    """The session's open and close as explicit UTC instants for that date."""
    zone = zone or load_zone()[0]
    close_local = time(13, 55) if market_mode(on_date, ramadan_periods) == "RAMADAN" \
        else SESSION_CLOSE_LOCAL
    start = datetime.combine(on_date, SESSION_START_LOCAL, tzinfo=zone)
    stop = datetime.combine(on_date, close_local, tzinfo=zone)
    return start.astimezone(timezone.utc), stop.astimezone(timezone.utc)


def gate(now_utc: datetime | None = None, *, ramadan_periods: list[dict] | None = None,
         zone: ZoneInfo | None = None, source: str | None = None,
         digest: str | None = None) -> dict:
    """Decide whether to collect right now, and explain the decision.

    The comparison is between two UTC instants. Nothing here asks the container
    what the local time is. When no zone is supplied the real source is resolved
    here, so a fallback to the container's stale data is reported as such rather
    than labelled as the vendored rule.
    """
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if zone is None:
        zone, source, digest = load_zone()
    else:
        source = source or "INJECTED"
        digest = digest or ""
    local_date = now.astimezone(zone).date()
    offset = int(now.astimezone(zone).utcoffset().total_seconds())
    start, stop = session_window(local_date, ramadan_periods=ramadan_periods, zone=zone)

    if now.astimezone(zone).weekday() >= 5:
        state = CLOSED_NON_SESSION_DAY
    elif now < start:
        state = CLOSED_BEFORE_OPEN
    elif now > stop:
        state = CLOSED_AFTER_CLOSE
    else:
        state = OPEN

    return {
        "open": state == OPEN,
        "state": state,
        "market_date": local_date.isoformat(),
        "market_mode": market_mode(local_date, ramadan_periods),
        "casablanca_offset_seconds": offset,
        "session_open_utc": start.isoformat(),
        "session_close_utc": stop.isoformat(),
        "now_utc": now.isoformat(),
        "zone_source": source,
        "tzdata_sha256": digest,
    }


def container_offset_seconds(now: datetime | None = None) -> int | None:
    """What the container's own tz database says, bypassing the vendored file.

    This exists so that the two can be compared in the log. It deliberately does
    NOT consult the vendored rule: a diagnostic that reported the vendored offset
    under a name suggesting the container's would be unfalsifiable, and would
    hide the very staleness it is meant to expose. None means the container has
    no such zone at all.
    """
    try:
        zone = ZoneInfo("Africa/Casablanca")
    except Exception:
        return None
    return int((now or datetime.now(timezone.utc)).astimezone(zone).utcoffset().total_seconds())


def diagnostics() -> dict:
    """Both clocks, side by side, for the run log."""
    zone, source, digest = load_zone()
    now = datetime.now(timezone.utc)
    vendored = int(now.astimezone(zone).utcoffset().total_seconds())
    container = container_offset_seconds(now)
    return {
        "zone_source": source,
        "tzdata_sha256": digest,
        "vendored_offset_seconds": vendored,
        "container_offset_seconds": container,
        "tz_sources_agree": container == vendored,
    }
