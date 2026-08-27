import asyncio
import csv
import email.utils
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_defi_yields import (
    DeFiYieldScraper,
    fetch_pools,
    normalize_chains,
    normalize_provider_timestamp,
    parse_payload,
    validate_freshness,
)


FIXTURE = Path(__file__).parent / "fixtures" / "defillama_pools.json"


class FakeResponse:
    def __init__(self, payload, provider_date="Tue, 25 Aug 2026 09:00:00 GMT"):
        self._payload = payload
        self.content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.headers = {"date": provider_date}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DeFiYieldScraperTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.now = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)

    def test_normalize_chains_maps_optimism_provider_alias(self):
        self.assertEqual(normalize_chains(["Ethereum", "Optimism", "ethereum"]), ["Ethereum", "OP Mainnet"])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            normalize_chains(["Mars"])

    def test_parse_filters_deduplicates_and_sorts_valid_pools(self):
        rows = parse_payload(
            self.payload, ["Ethereum", "Optimism", "Base"], min_apy=5,
            min_tvl_usd=1_000_000, max_apy=100,
            provider_updated_at="Tue, 25 Aug 2026 09:00:00 GMT", now=self.now,
        )
        self.assertEqual([row["pool_id"] for row in rows], ["pool-ethereum-1", "pool-optimism-1"])
        self.assertEqual(rows[1]["chain"], "OP Mainnet")
        self.assertEqual(rows[0]["provider_updated_at"], "2026-08-25T09:00:00Z")
        self.assertEqual(rows[0]["apy_base"], 7.5)
        self.assertTrue(rows[0]["stablecoin"])

    def test_freshness_rejects_stale_provider_timestamp(self):
        with self.assertRaisesRegex(ValueError, "older"):
            validate_freshness("2026-08-23T09:00:00Z", 24, now=self.now)

    def test_parse_rejects_bad_status_and_empty_data(self):
        with self.assertRaisesRegex(ValueError, "status"):
            parse_payload({"status": "error", "data": []}, ["Ethereum"], provider_updated_at="2026-08-25T09:00:00Z", now=self.now)
        with self.assertRaisesRegex(ValueError, "non-empty"):
            parse_payload({"status": "success", "data": []}, ["Ethereum"], provider_updated_at="2026-08-25T09:00:00Z", now=self.now)

    def test_fetch_pools_rejects_non_json_and_missing_success(self):
        class TextResponse:
            content = b"GET,HEAD"
            headers = {"date": "Tue, 25 Aug 2026 09:00:00 GMT"}

            def raise_for_status(self):
                return None

            def json(self):
                raise json.JSONDecodeError("Expecting value", "GET,HEAD", 0)

        class AllowResponse:
            content = b'{"Allow":"GET,HEAD"}'
            headers = {"date": "Tue, 25 Aug 2026 09:00:00 GMT"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"Allow": "GET,HEAD"}

        with patch("scripts.scrape_defi_yields.httpx.get", return_value=TextResponse()):
            with self.assertRaisesRegex(ValueError, "not JSON"):
                fetch_pools()
        with patch("scripts.scrape_defi_yields.httpx.get", return_value=AllowResponse()):
            with self.assertRaisesRegex(ValueError, "successful pools payload"):
                fetch_pools()

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = DeFiYieldScraper(
                chains=["Ethereum", "Optimism"], min_tvl_usd=1_000_000,
                max_apy=100, min_rows=2, output_dir=temp_dir,
            )
            live_date = email.utils.format_datetime(datetime.now(timezone.utc), usegmt=True)
            expected_provider_time = normalize_provider_timestamp(live_date)
            with patch(
                "scripts.scrape_defi_yields.httpx.get",
                return_value=FakeResponse(self.payload, provider_date=live_date),
            ):
                result = asyncio.run(scraper.run())
            self.assertEqual(result[0]["source"], "defi_yields")
            self.assertEqual(result[0]["count"], 2)
            self.assertEqual(result[0]["provider_updated_at"], expected_provider_time)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "defi_yields_raw.json").exists())
            with (output_dir / "defi_yields.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["pool_id"], "pool-ethereum-1")
            self.assertEqual(rows[0]["provider_updated_at"], expected_provider_time)
            with (output_dir / "defi_yields_history.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 2)


if __name__ == "__main__":
    unittest.main()
