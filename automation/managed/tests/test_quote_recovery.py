import unittest
from datetime import datetime,timezone,timedelta
from quote_recovery import slot
class QuoteRecoveryTests(unittest.TestCase):
 def test_explicit_short_lived_same_day_capture(self):
  now=datetime(2026,11,13,21,10,tzinfo=timezone.utc)
  self.assertEqual(slot(now,(now+timedelta(minutes=20)).isoformat()),'2026-11-13T21:00:00+00:00')
  for value in ['', 'bad', now.isoformat(), (now+timedelta(hours=1)).isoformat(), '2026-11-13T21:20:00']:
   self.assertIsNone(slot(now,value))
 def test_weekend_is_rejected(self):
  now=datetime(2026,11,14,21,tzinfo=timezone.utc)
  self.assertIsNone(slot(now,(now+timedelta(minutes=20)).isoformat()))
