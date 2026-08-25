import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news.matichon_scraper import MatichonScraper, canonical_url, parse_feed


FIXTURE = Path(__file__).parent / "fixtures" / "matichon_feed.xml"


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class MatichonScraperTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://www.matichon.co.th/economy/news_12345?utm_source=rss"),
            "https://www.matichon.co.th/economy/news_12345",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://matichon.co.th.evil.example/news")

    def test_parse_feed_keeps_attribution_and_drops_invalid_entries(self):
        parsed, rows = parse_feed(self.raw, limit=10)

        self.assertEqual(parsed.feed.title, "มติชนออนไลน์")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["article_id"], "matichon-12345")
        self.assertEqual(rows[0]["source"], "Matichon")
        self.assertEqual(rows[0]["categories"], "เศรษฐกิจ,ข่าวเด่น")
        self.assertEqual(rows[0]["url"], "https://www.matichon.co.th/economy/news_12345")
        self.assertEqual(rows[0]["published_at"], "2026-08-25T08:30:00Z")

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = MatichonScraper(
                feed_url="https://www.matichon.co.th/feed",
                limit=10,
                output_dir=temp_dir,
            )
            with patch("news.matichon_scraper.httpx.get", return_value=FakeResponse(self.raw)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "matichon_news")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "matichon_news_raw.xml").exists())
            with (output_dir / "matichon_news.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source"], "Matichon")
            with (output_dir / "matichon_news_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
