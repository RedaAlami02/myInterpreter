"""Explicit, non-activating schedule/cost plan for private hosted runners.

UTC below is a candidate interpretation of retained cron expressions, not proof
of the retired scheduler's timezone. Runner costs include per-job rounding;
account-wide remaining allowance must be supplied independently before approval.
"""
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING


CRONS = {'depth': '*/5 8-15 * * 1-5', 'quotes': '*/15 8-15 * * 1-5',
         'dividends': '0 6 * * 1', 'cleanup': '0 16 * * 1-5'}
RATES = {'linux_2_core': Decimal('0.006'), 'linux_slim_1_core': Decimal('0.002')}


def slots(year, month):
    """Enumerate exact candidate UTC starts; never dispatch or fetch anything."""
    output = {kind: [] for kind in CRONS}
    for day in range(1, monthrange(year, month)[1] + 1):
        start = datetime(year, month, day, tzinfo=timezone.utc)
        if start.weekday() >= 5:
            continue
        for kind, interval in (('depth', 5), ('quotes', 15)):
            output[kind].extend(start + timedelta(hours=8, minutes=minute)
                                for minute in range(0, 8 * 60, interval))
        output['cleanup'].append(start + timedelta(hours=16))
        if start.weekday() == 0:
            output['dividends'].append(start + timedelta(hours=6))
    return output


def estimate(year, month, seconds_per_job, *, remaining_credit=None,
             other_reserved_cost='0', runner='linux_2_core'):
    """Conservative separate-job cost. No unmeasured duration is called verified."""
    if runner not in RATES or set(seconds_per_job) != set(CRONS):
        raise ValueError('EXPLICIT_JOB_DURATIONS_REQUIRED')
    plan = slots(year, month)
    costs = {}; minutes = {}
    for kind, starts in plan.items():
        seconds = Decimal(str(seconds_per_job[kind]))
        if not seconds.is_finite() or seconds <= 0:
            raise ValueError('INVALID_JOB_DURATION')
        minutes[kind] = len(starts) * int((seconds / 60).to_integral_value(rounding=ROUND_CEILING))
        costs[kind] = minutes[kind] * RATES[runner]
    reserved = Decimal(str(other_reserved_cost))
    available = None if remaining_credit is None else Decimal(str(remaining_credit))
    if (not reserved.is_finite() or reserved < 0 or
            (available is not None and (not available.is_finite() or available < 0))):
        raise ValueError('INVALID_BUDGET')
    total = sum(costs.values(), Decimal('0')) + reserved
    return {'contract': 'private-schedule-cost/v1', 'timezone': 'UTC_CANDIDATE',
            'cron_timezone_verified': False, 'counts': {k: len(v) for k, v in plan.items()},
            'billed_minutes': minutes, 'runner': runner,
            'estimated_cost_usd': str(total), 'remaining_credit_usd': None if available is None else str(available),
            'fits_supplied_budget': None if available is None else total <= available,
            'activation_permitted': False,
            'exclusions': ['retries', 'workflow overhead beyond supplied durations',
                           'fundamental jobs', 'daily valuation jobs', 'artifact storage']}
