import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news.notebookspec_scraper import NotebookspecScraper, canonical_url, parse_feed


FIXTURE = Path(__file__).parent / "fixtures" / "notebookspec_feed.xml"


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class NotebookspecScraperTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://notebookspec.com/web/885001-sample-notebook-review?utm_source=rss"),
            "https://notebookspec.com/web/885001-sample-notebook-review",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://notebookspec.com.evil.example/web/news")

    def test_parse_feed_keeps_attribution_and_drops_invalid_entries(self):
        parsed, rows = parse_feed(self.raw, limit=10)

        self.assertEqual(parsed.feed.title, "Notebookspec")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "Notebookspec")
        self.assertEqual(rows[0]["categories"], "Review,Notebook")
        self.assertEqual(
            rows[0]["url"],
            "https://notebookspec.com/web/885001-sample-notebook-review",
        )
        self.assertEqual(rows[0]["published_at"], "2026-08-25T05:25:33Z")

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = NotebookspecScraper(
                feed_url="https://notebookspec.com/web/feed",
                limit=10,
                output_dir=temp_dir,
            )
            with patch("news.notebookspec_scraper.httpx.get", return_value=FakeResponse(self.raw)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "notebookspec_tech")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "notebookspec_tech_raw.xml").exists())
            with (output_dir / "notebookspec_tech.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source"], "Notebookspec")


if __name__ == "__main__":
    unittest.main()
