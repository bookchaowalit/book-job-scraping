import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_stock_prices import (
    StockPriceScraper,
    normalize_request,
    validate_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "yahoo_chart_aapl_msft.json"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class StockPriceScraperTests(unittest.TestCase):
    def setUp(self):
        self.payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_normalize_request_bounds_tickers_and_chart_params(self):
        symbols, interval, lookback = normalize_request("aapl,AAPL,msft", "1D", "5D")

        self.assertEqual(symbols, ["AAPL", "MSFT"])
        self.assertEqual(interval, "1d")
        self.assertEqual(lookback, "5d")
        with self.assertRaises(ValueError):
            normalize_request(["bad ticker!"], "1d", "5d")
        with self.assertRaises(ValueError):
            normalize_request(["AAPL"], "5m", "5d")

    def test_validate_payload_rejects_symbol_timestamp_and_close_errors(self):
        with self.assertRaisesRegex(ValueError, "symbol mismatch"):
            validate_payload(self.payloads["AAPL"], "MSFT", "1d")
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            invalid = json.loads(json.dumps(self.payloads["AAPL"]))
            invalid["chart"]["result"][0]["timestamp"] = [1787146200, 1787059800]
            validate_payload(invalid, "AAPL", "1d")
        with self.assertRaisesRegex(ValueError, "no valid close"):
            invalid = json.loads(json.dumps(self.payloads["AAPL"]))
            invalid["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [None, None, None]
            validate_payload(invalid, "AAPL", "1d")

    def test_validate_payload_uses_latest_close_and_provider_previous_close(self):
        row = validate_payload(self.payloads["AAPL"], "AAPL", "1d")

        self.assertEqual(row["date"], "2026-08-20")
        self.assertEqual(row["price"], 306.0)
        self.assertEqual(row["previous_close"], 300.0)
        self.assertAlmostEqual(row["change_pct"], 2.0, places=3)
        self.assertEqual(row["volume"], 1200000)

    def test_run_writes_raw_snapshot_and_history(self):
        def fake_get(url, **_kwargs):
            symbol = url.rsplit("/", 1)[-1]
            return FakeResponse(self.payloads[symbol])

        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = StockPriceScraper(
                symbols=["AAPL", "MSFT"],
                interval="1d",
                range="5d",
                output_dir=temp_dir,
            )
            with patch("scripts.scrape_stock_prices.httpx.get", side_effect=fake_get):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "stock_prices")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "stock_prices_raw.json").exists())
            with (output_dir / "stock_prices.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["symbol"], "AAPL")
            self.assertEqual(rows[0]["price"], "306.0")
            with (output_dir / "stock_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
