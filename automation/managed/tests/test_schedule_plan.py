import unittest
from datetime import datetime,timezone
import schedule_plan


class SchedulePlanTests(unittest.TestCase):
    def test_original_cadence_and_monday_calendar(self):
        plan = schedule_plan.slots(2026,11)
        self.assertEqual({k:len(v) for k,v in plan.items()},
                         {'depth':2016,'quotes':672,'dividends':5,'cleanup':21})
        self.assertEqual(plan['depth'][1]-plan['depth'][0], __import__('datetime').timedelta(minutes=5))
        self.assertTrue(all(v.weekday()==0 and v.hour==6 for v in plan['dividends']))
        self.assertEqual(plan['quotes'][0],datetime(2026,11,2,8,tzinfo=timezone.utc))
        self.assertEqual(plan['quotes'][31].hour,15)
        self.assertEqual(plan['quotes'][31].minute,45)

    def test_round_each_job_not_month_total(self):
        result = schedule_plan.estimate(2026,11,{k:61 for k in schedule_plan.CRONS},remaining_credit='18')
        self.assertEqual(result['estimated_cost_usd'],'32.568')
        self.assertFalse(result['fits_supplied_budget'])
        self.assertFalse(result['activation_permitted'])

    def test_unknown_shared_allowance_not_approved(self):
        result = schedule_plan.estimate(2026,11,{k:60 for k in schedule_plan.CRONS})
        self.assertEqual(result['estimated_cost_usd'],'16.284')
        self.assertIsNone(result['fits_supplied_budget'])
        self.assertFalse(result['cron_timezone_verified'])

    def test_reserved_work_counts(self):
        result = schedule_plan.estimate(2026,11,{k:60 for k in schedule_plan.CRONS},
                                        remaining_credit='18',other_reserved_cost='2')
        self.assertFalse(result['fits_supplied_budget'])

    def test_invalid_unbounded_or_missing_inputs(self):
        for durations in ({}, {k:'NaN' for k in schedule_plan.CRONS},
                          {k:-1 for k in schedule_plan.CRONS}):
            with self.assertRaises(ValueError):
                schedule_plan.estimate(2026,11,durations)
