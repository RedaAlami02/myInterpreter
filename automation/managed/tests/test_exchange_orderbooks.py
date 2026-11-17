import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import exchange_orderbooks as books


def at(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class CleanLevelsTests(unittest.TestCase):
    def test_bids_are_sorted_descending_and_asks_ascending(self):
        bids = books.clean_levels([{"price": 10.0, "quantity": 5},
                                   {"price": 11.0, "quantity": 2}], "bids")
        asks = books.clean_levels([{"price": 13.0, "quantity": 5},
                                   {"price": 12.0, "quantity": 2}], "asks")
        self.assertEqual([level["price"] for level in bids], [11.0, 10.0])
        self.assertEqual([level["price"] for level in asks], [12.0, 13.0])

    def test_invalid_quantities_and_prices_are_dropped_not_repaired(self):
        levels = books.clean_levels([
            {"price": "10,5", "quantity": "100"},
            {"price": None, "quantity": 10},
            {"price": 0, "quantity": 10},
            {"price": 10.5, "quantity": -1},
            {"price": 9.9, "quantity": 4},
        ], "bids")
        self.assertEqual([level["price"] for level in levels], [10.5, 9.9])
        self.assertEqual(levels[0]["quantity"], 100)

    def test_duplicate_prices_keep_the_first_level(self):
        levels = books.clean_levels([{"price": 5, "quantity": 1},
                                     {"price": 5, "quantity": 9}], "asks")
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0]["quantity"], 1)

    def test_levels_are_capped(self):
        rows = [{"price": price, "quantity": 1} for price in range(40, 0, -1)]
        self.assertEqual(len(books.clean_levels(rows, "bids", limit=10)), 10)


class BookRowTests(unittest.TestCase):
    def test_empty_book_is_not_published(self):
        self.assertIsNone(books.book_row("ADH", "CDG_DELAYED", [], [], at("2026-11-17T15:00:00Z")))

    def test_row_carries_source_and_symbol(self):
        row = books.book_row("adh", "MEDIAS24_PUBLIC",
                             [{"price": 39, "quantity": 10}], [], at("2026-11-17T15:00:00Z"))
        self.assertEqual(row["symbol"], "ADH")
        self.assertEqual(row["source"], "MEDIAS24_PUBLIC")
        self.assertEqual(row["captured_at"], "2026-11-17T15:00:00Z")
        self.assertEqual(row["asks"], [])


class SessionWindowTests(unittest.TestCase):
    def test_weekday_midday_is_open(self):
        self.assertTrue(books.session_open(at("2026-11-17T11:00:00Z")))  # 12:00 Casablanca

    def test_weekend_is_closed(self):
        self.assertFalse(books.session_open(at("2026-11-21T11:00:00Z")))

    def test_early_morning_is_closed(self):
        self.assertFalse(books.session_open(at("2026-11-17T06:00:00Z")))  # 07:00 local

    def test_evening_is_closed(self):
        self.assertFalse(books.session_open(at("2026-11-17T16:00:00Z")))  # 17:00 local


class CaptureTests(unittest.TestCase):
    def fetch(self, url):
        if "getAllStocks" in url:
            return {"result": [{"name": "ADDOHA", "ISIN": "MA0000011512", "datetime": "20261117 154139"}]}
        if "getBidAsk" in url:
            return {"result": {"orderBook": [
                {"bidValue": "38.8", "bidQte": "10", "bidOrder": 1,
                 "askValue": "39.2", "askQte": "20", "askOrder": 2},
                {"bidValue": "38.7", "bidQte": "30", "bidOrder": 3,
                 "askValue": "", "askQte": "", "askOrder": None},
            ]}}
        raise AssertionError(url)

    def test_medias24_is_primary(self):
        rows, report = books.capture(["ADH"], {"ADH": "MA0000011512"},
                                     fetch_json_fn=self.fetch,
                                     cdg_post=lambda _payload: self.fail("CDG must not be used"),
                                     moment=at("2026-11-17T15:00:00Z"))
        self.assertEqual(report["medias24"], 1)
        self.assertEqual(rows[0]["source"], "MEDIAS24_PUBLIC")
        self.assertEqual(rows[0]["market_time"], "20261117 154139")
        self.assertEqual(len(rows[0]["bids"]), 2)
        self.assertEqual(len(rows[0]["asks"]), 1)

    def test_cdg_covers_a_symbol_medias24_does_not_list(self):
        def poster(payload):
            return [{"VALEUR-PROFONDEUR": {"Valid": True, "Data": [
                {"Achat": 12.0, "QteAchat": 5, "NbrAchat": 1,
                 "Vente": 12.5, "QteVente": 7, "NbrVente": 2}]}}]
        rows, report = books.capture(["NRJ"], {}, fetch_json_fn=self.fetch,
                                     cdg_post=poster, moment=at("2026-11-17T15:00:00Z"))
        self.assertEqual(report["cdg"], 1)
        self.assertEqual(rows[0]["source"], "CDG_DELAYED")

    def test_medias24_failure_falls_back_without_losing_the_symbol(self):
        def broken(url):
            if "getAllStocks" in url:
                return {"result": [{"ISIN": "MA0000011512"}]}
            raise RuntimeError("boom")

        def poster(payload):
            return [{"VALEUR-PROFONDEUR": {"Valid": True, "Data": [
                {"Achat": 12.0, "QteAchat": 5, "NbrAchat": 1,
                 "Vente": 12.5, "QteVente": 7, "NbrVente": 2}]}}]
        rows, report = books.capture(["ADH"], {"ADH": "MA0000011512"},
                                     fetch_json_fn=broken, cdg_post=poster,
                                     moment=at("2026-11-17T15:00:00Z"))
        self.assertEqual(report["cdg"], 1)
        self.assertEqual(rows[0]["bids"][0]["price"], 12.0)

    def test_a_symbol_failing_on_both_sources_is_reported_not_fabricated(self):
        def broken(url):
            raise RuntimeError("down")

        def poster(payload):
            raise RuntimeError("down too")
        rows, report = books.capture(["ADH"], {"ADH": "MA0000011512"},
                                     fetch_json_fn=broken, cdg_post=poster,
                                     moment=at("2026-11-17T15:00:00Z"))
        self.assertEqual(rows, [])
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["failures"][0]["symbol"], "ADH")


if __name__ == "__main__":
    unittest.main()
