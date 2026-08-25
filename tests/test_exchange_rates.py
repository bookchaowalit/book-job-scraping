import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_exchange_rates import (
    ExchangeRateScraper,
    normalize_request,
    rate_rows,
    validate_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "frankfurter_latest.json"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class ExchangeRateScraperTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_normalize_request(self):
        base, symbols = normalize_request("thb", "usd,EUR,usd")

        self.assertEqual(base, "THB")
        self.assertEqual(symbols, ["USD", "EUR"])
        with self.assertRaises(ValueError):
            normalize_request("THB", ["THB"])

    def test_validate_payload_rejects_wrong_base_and_missing_symbol(self):
        with self.assertRaisesRegex(ValueError, "base mismatch"):
            validate_payload(self.payload, "USD", ["EUR"])
        with self.assertRaisesRegex(ValueError, "missing symbol"):
            validate_payload(self.payload, "THB", ["USD", "GBP"])
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            invalid = {**self.payload, "date": "25-08-2026"}
            validate_payload(invalid, "THB", ["USD"])

    def test_rate_rows_keep_provider_date_and_previous_change(self):
        payload = validate_payload(self.payload, "THB", ["USD", "EUR", "JPY"])
        rows = rate_rows(payload, {"USD": 0.03}, 0.5, "2026-08-25T00:00:00Z")

        self.assertEqual(rows[0]["date"], "2026-08-25")
        self.assertEqual(rows[0]["currency"], "USD")
        self.assertAlmostEqual(rows[0]["change_pct"], 1.667, places=3)
        self.assertEqual(rows[1]["trend_7d"], "unknown")

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = ExchangeRateScraper(
                base="THB",
                symbols=["USD", "EUR", "JPY"],
                output_dir=temp_dir,
            )
            with patch("scripts.scrape_exchange_rates.httpx.get", return_value=FakeResponse(self.payload)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "exchange_rates")
            self.assertEqual(result[0]["count"], 3)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "exchange_rates_raw.json").exists())
            with (output_dir / "exchange_rates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["base"], "THB")
            with (output_dir / "exchange_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 3)


if __name__ == "__main__":
    unittest.main()

