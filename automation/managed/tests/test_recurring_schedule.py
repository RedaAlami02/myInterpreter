import os,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import recurring_schedule as schedule
import worker,cloud_state
from test_cloud_state import API


class RecurringScheduleTests(unittest.TestCase):
    def test_five_minute_depth_and_quarter_hour_quotes(self):
        for minute in [0,5,10,15,20,25,30,35,40,45,50,55]:
            now=datetime(2026,11,2,10,minute,tzinfo=timezone.utc)
            self.assertIsNotNone(schedule.slot(now,'depth'))
            due=schedule.due(now)
            self.assertEqual('quotes' in due,minute%15==0)
            self.assertIn('depth',due)

    def test_monday_dividends_and_weekday_fundamentals(self):
        self.assertIsNotNone(schedule.slot(datetime(2026,11,2,7,5,tzinfo=schedule.ZONE),'dividends'))
        self.assertIsNone(schedule.slot(datetime(2026,11,6,7,5,tzinfo=schedule.ZONE),'dividends'))
        self.assertIsNotNone(schedule.slot(datetime(2026,11,2,17,5,tzinfo=schedule.ZONE),'fundamentals'))
        self.assertEqual(schedule.due(datetime(2026,11,7,10,0,tzinfo=timezone.utc)),[])

    def test_explicit_contract_keeps_legacy_default(self):
        now=datetime(2026,11,2,10,25,tzinfo=timezone.utc)
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(worker.scheduled_slot(now,'depth'))
        with patch.dict(os.environ,{'APP_SCHEDULE_CONTRACT':schedule.CONTRACT}):self.assertIsNotNone(worker.scheduled_slot(now,'depth'))
        with patch.dict(os.environ,{'APP_SCHEDULE_CONTRACT':'wrong'}),self.assertRaises(worker.AcquisitionError):worker.scheduled_slot(now,'depth')

    def test_scheduled_checkpoints_require_explicit_contract_and_private_branch(self):
        api=API();api.current['event']='schedule'
        with patch.dict(os.environ,{},clear=True),self.assertRaises(worker.AcquisitionError):cloud_state.current(api,20)
        with patch.dict(os.environ,{'APP_SCHEDULE_CONTRACT':schedule.CONTRACT}):
            self.assertEqual(cloud_state.current(api,20)['event'],'schedule')
            api.repository['private']=False
            with self.assertRaises(worker.AcquisitionError):cloud_state.current(api,20)
