import importlib.util
import json
from pathlib import Path
import unittest
from datetime import datetime

spec = importlib.util.spec_from_file_location('daily_pnl', Path(__file__).parents[1] / 'src/main.py')
pnl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnl)


class Database:
    def __init__(self):
        self.rows = {
            'portefeuille': [{'$id': 'h1', 'user_id': 'demo', 'c_name': 'Fiction', 'quantity': 10, 'total_cost': 80}],
            'latest_prices': [{'$id': 'q1', 'c_name': 'Fiction', 'pa': 12, 'date': '2026-10-19T15:45:00+00:00'}],
            'benefits': [],
        }
        self.writes = []
        self.conflict = False

    def list_documents(self, database, collection, queries):
        rows = list(self.rows[collection])
        limit = 100
        for raw in queries:
            query = json.loads(raw)
            method = query['method']
            values = query.get('values', [])
            field = query.get('attribute')
            if method == 'equal':
                rows = [r for r in rows if r[field] in values]
            elif method == 'greaterThanEqual':
                rows = [r for r in rows if r[field] >= values[0]]
            elif method == 'lessThan':
                rows = [r for r in rows if r[field] < values[0]]
            elif method == 'cursorAfter':
                rows = rows[next(i for i, r in enumerate(rows) if r['$id'] == values[0]) + 1:]
            elif method == 'limit':
                limit = values[0]
        return {'documents': rows[:limit]}

    def create_document(self, database, collection, doc_id, data, permissions):
        if self.conflict:
            raise pnl.AppwriteException('Conflict', 409)
        self.rows[collection].append({'$id': doc_id, **data})
        self.writes.append((doc_id, data, permissions))


class DailyPnlTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.now = datetime.fromisoformat('2026-10-19T16:15:00+00:00')

    def test_value_permissions_and_retry(self):
        result = pnl.run(self.db, self.now)
        self.assertEqual(result['created'], 1)
        doc_id, data, permissions = self.db.writes[0]
        self.assertEqual(data['value'], 40)
        self.assertEqual(data['user_id'], 'demo')
        self.assertEqual(len(doc_id), 36)
        self.assertEqual(permissions, ['read("user:demo")', 'write("user:demo")'])
        self.assertEqual(pnl.run(self.db, self.now)['existing'], 1)
        self.assertEqual(len(self.db.writes), 1)

    def test_weekend_and_before_close(self):
        for date in ['2026-10-18T16:15:00+00:00', '2026-10-19T14:15:00+00:00']:
            self.assertEqual(pnl.run(self.db, datetime.fromisoformat(date))['status'], 'outside_window')
        self.assertFalse(self.db.writes)

    def test_ramadan_utc_offset(self):
        self.db.rows['latest_prices'][0]['date'] = '2026-03-02T15:45:00+00:00'
        self.assertEqual(pnl.run(self.db, datetime.fromisoformat('2026-03-02T16:15:00+00:00'))['status'], 'outside_window')
        self.assertEqual(pnl.run(self.db, datetime.fromisoformat('2026-03-02T17:15:00+00:00'))['created'], 1)

    def test_missing_price_skips_whole_portfolio(self):
        self.db.rows['portefeuille'].append({'$id': 'h2', 'user_id': 'demo', 'c_name': 'Missing', 'quantity': 1, 'total_cost': 10})
        self.assertEqual(pnl.run(self.db, self.now)['skipped'], 1)
        self.assertFalse(self.db.writes)

    def test_stale_morning_future_and_invalid_quotes(self):
        for date in ['2026-10-16T15:45:00+00:00', '2026-10-19T09:00:00+00:00', '2026-10-19T18:00:00+00:00', 'invalid']:
            with self.subTest(date=date):
                self.db.rows['latest_prices'][0]['date'] = date
                self.assertEqual(pnl.run(self.db, self.now)['skipped'], 1)
        self.assertFalse(self.db.writes)

    def test_non_finite_and_zero_price(self):
        for value in [float('nan'), float('inf'), 0, -1]:
            self.db.rows['latest_prices'][0]['pa'] = value
            self.assertEqual(pnl.run(self.db, self.now)['skipped'], 1)

    def test_legacy_record_is_not_overwritten(self):
        self.db.rows['benefits'].append({'$id': 'old', 'user_id': 'demo', 'date': '2026-10-19T00:00:00.000+00:00', 'value': 15})
        self.assertEqual(pnl.run(self.db, self.now)['existing'], 1)
        self.assertFalse(self.db.writes)

    def test_sold_out_portfolio_is_zero(self):
        self.db.rows['portefeuille'] = []
        self.db.rows['benefits'].append({'$id': 'old', 'user_id': 'demo', 'date': '2026-10-16T00:00:00.000+00:00', 'value': 15})
        self.assertEqual(pnl.run(self.db, self.now)['created'], 1)
        self.assertEqual(self.db.writes[0][1]['value'], 0)

    def test_concurrent_create_conflict_is_idempotent(self):
        self.db.conflict = True
        self.assertEqual(pnl.run(self.db, self.now)['existing'], 1)

    def test_cursor_pagination(self):
        self.db.rows['latest_prices'] = [{'$id': str(i)} for i in range(205)]
        self.assertEqual(len(list(pnl.all_docs(self.db, 'latest_prices'))), 205)

    def test_duplicate_quotes_skip(self):
        self.db.rows['latest_prices'].append(dict(self.db.rows['latest_prices'][0]))
        self.assertEqual(pnl.run(self.db, self.now)['skipped'], 1)

    def test_users_are_isolated(self):
        self.db.rows['portefeuille'].append({'$id': 'h2', 'user_id': 'other', 'c_name': 'Fiction', 'quantity': 2, 'total_cost': 30})
        self.assertEqual(pnl.run(self.db, self.now)['created'], 2)
        self.assertEqual(self.db.writes[1][1]['value'], -6)
        self.assertNotEqual(self.db.writes[0][0], self.db.writes[1][0])
        self.assertEqual(self.db.writes[1][2], ['read("user:other")', 'write("user:other")'])


if __name__ == '__main__':
    unittest.main()
