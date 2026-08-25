import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news.thai_business_scraper import (
    ThaiBusinessNewsScraper,
    canonical_url,
    parse_feed,
)


FIXTURE = Path(__file__).parent / "fixtures" / "bangkok_post_business.xml"


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class ThaiBusinessNewsScraperTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://www.bangkokpost.com/business/general/123?utm_source=rss"),
            "https://www.bangkokpost.com/business/general/123",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://bangkokpost.com.evil.example/business/123")

    def test_parse_feed_normalizes_source_timezone_and_drops_invalid_entries(self):
        parsed, rows = parse_feed(self.raw, limit=10)

        self.assertEqual(parsed.feed.title, "Bangkokpost.com : Business")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "Bangkok Post Business")
        self.assertEqual(rows[0]["section"], "business")
        self.assertEqual(rows[0]["published_at"], "2026-08-25T06:45:00Z")
        self.assertEqual(rows[1]["published_at"], "2026-08-25T02:15:00Z")

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = ThaiBusinessNewsScraper(
                feed_url="https://www.bangkokpost.com/rss/data/business.xml",
                limit=10,
                output_dir=temp_dir,
            )
            with patch("news.thai_business_scraper.httpx.get", return_value=FakeResponse(self.raw)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "thai_business_news")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "thai_business_news_raw.xml").exists())
            with (output_dir / "thai_business_news.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source"], "Bangkok Post Business")
            with (output_dir / "thai_business_news_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
