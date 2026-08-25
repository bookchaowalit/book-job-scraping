import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news.thai_tech_scraper import ThaiTechNewsScraper, canonical_url, parse_feed


FIXTURE = Path(__file__).parent / "fixtures" / "blognone_atom.xml"


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class ThaiTechNewsScraperTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://www.blognone.com/node/151453?utm_source=atom"),
            "https://www.blognone.com/node/151453",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://blognone.com.evil.example/node/151453")

    def test_parse_feed_preserves_topics_and_drops_invalid_entries(self):
        parsed, rows = parse_feed(self.raw, limit=10)

        self.assertIn("Blognone", parsed.feed.title)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["article_id"], "151453")
        self.assertEqual(rows[0]["source"], "Blognone")
        self.assertEqual(rows[0]["section"], "technology")
        self.assertEqual(rows[0]["topics"], "AI,ชิป")
        self.assertEqual(rows[0]["published_at"], "2026-08-25T03:11:08Z")

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = ThaiTechNewsScraper(
                feed_url="https://www.blognone.com/atom.xml",
                limit=10,
                output_dir=temp_dir,
            )
            with patch("news.thai_tech_scraper.httpx.get", return_value=FakeResponse(self.raw)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "thai_tech_news")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "thai_tech_news_raw.xml").exists())
            with (output_dir / "thai_tech_news.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source"], "Blognone")
            with (output_dir / "thai_tech_news_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
