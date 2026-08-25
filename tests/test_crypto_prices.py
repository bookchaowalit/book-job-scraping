import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_crypto_prices import (
    CryptoPriceScraper,
    normalize_request,
    price_rows,
    validate_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "coingecko_simple_price.json"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class CryptoPriceScraperTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_normalize_request_bounds_and_deduplicates(self):
        coins, currencies = normalize_request("bitcoin,bitcoin,ethereum", "USD,thb,usd")

        self.assertEqual(coins, ["bitcoin", "ethereum"])
        self.assertEqual(currencies, ["usd", "thb"])
        with self.assertRaises(ValueError):
            normalize_request(["bad coin"], ["usd"])

    def test_validate_payload_rejects_partial_response(self):
        with self.assertRaisesRegex(ValueError, "missing coin"):
            validate_payload(self.payload, ["bitcoin", "solana"], ["usd"])
        with self.assertRaisesRegex(ValueError, "must be greater than zero"):
            validate_payload({"bitcoin": {"usd": 0}}, ["bitcoin"], ["usd"])

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = CryptoPriceScraper(
                coins=["bitcoin", "ethereum"],
                vs_currencies=["usd", "thb"],
                output_dir=temp_dir,
            )
            with patch("scripts.scrape_crypto_prices.httpx.get", return_value=FakeResponse(self.payload)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "crypto_prices")
            self.assertEqual(result[0]["count"], 4)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "crypto_prices_raw.json").exists())
            with (output_dir / "crypto_prices.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["coin_id"], "bitcoin")
            self.assertEqual(rows[0]["currency"], "usd")
            with (output_dir / "crypto_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 4)

    def test_price_rows_preserve_requested_currency_contract(self):
        rows = price_rows(self.payload, ["usd"], "2026-08-25T00:00:00Z")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["updated_at"], "2026-08-25T00:00:00Z")
        self.assertEqual(rows[1]["change_24h_pct"], -0.5)


if __name__ == "__main__":
    unittest.main()
