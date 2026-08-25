import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ecommerce.kaidee_scraper import KaideeScraper, canonical_url, parse_html


FIXTURE = Path(__file__).parent / "fixtures" / "kaidee_home.html"


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class KaideeScraperTests(unittest.TestCase):
    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("/product-12345?utm_source=test"),
            "https://www.kaidee.com/product-12345",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://example.com/product-12345")

    def test_parse_html_deduplicates_and_requires_positive_price(self):
        payload, rows = parse_html(self.html)

        self.assertIn("props", payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["listing_id"], "12345")
        self.assertEqual(rows[0]["price_thb"], 125000.0)
        self.assertEqual(rows[0]["url"], "https://www.kaidee.com/product-12345")

        _, filtered = parse_html(self.html, categories=["บ้าน"])
        self.assertEqual([row["listing_id"] for row in filtered], ["67890"])

    def test_run_writes_raw_snapshot_and_history(self):
        html = self.html
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = KaideeScraper(urls=["https://www.kaidee.com/"], output_dir=temp_dir)
            with patch("ecommerce.kaidee_scraper.httpx.get", return_value=FakeResponse(html)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "kaidee_classifieds")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "kaidee_classifieds_raw.json").exists())
            with (output_dir / "kaidee_classifieds.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["category"], "บ้าน")
            with (output_dir / "kaidee_classifieds_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)
            raw = json.loads((output_dir / "kaidee_classifieds_raw.json").read_text(encoding="utf-8"))
            self.assertIn("pages", raw)


if __name__ == "__main__":
    unittest.main()
