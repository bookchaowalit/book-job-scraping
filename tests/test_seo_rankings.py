import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_seo_rankings import (
    SEORankingScraper,
    normalize_request,
    parse_page,
)


FIXTURE = Path(__file__).parent / "fixtures" / "seo_bookchaowalit_home.html"


class FakeResponse:
    def __init__(self, html, status_code=200, url="https://bookchaowalit.com/"):
        self.text = html
        self.content = html.encode("utf-8")
        self.status_code = status_code
        self.url = url


class FakeClient:
    def __init__(self, response, *args, **kwargs):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        return self._response


class SEORankingScraperTests(unittest.TestCase):
    def test_normalize_request_strips_www_and_bounds_lists(self):
        domains, keywords = normalize_request(
            ["https://www.bookchaowalit.com/path", "bookchaowalit.com"],
            "next.js developer bangkok,next.js developer bangkok",
        )
        self.assertEqual(domains, ["bookchaowalit.com"])
        self.assertEqual(keywords, ["next.js developer bangkok"])
        with self.assertRaises(ValueError):
            normalize_request(["not a domain"], ["python"])

    def test_parse_page_keeps_title_and_canonical_without_claiming_rank(self):
        row = parse_page(
            "bookchaowalit.com",
            "https://bookchaowalit.com/",
            200,
            FIXTURE.read_text(encoding="utf-8"),
        )
        self.assertEqual(row["data_status"], "ok")
        self.assertEqual(row["source"], "public_page_check")
        self.assertEqual(row["rank"], "")
        self.assertEqual(row["canonical"], "https://bookchaowalit.com/")
        self.assertIn("Software", row["title"])

    def test_run_writes_snapshot_and_refuses_empty_reachability(self):
        html = FIXTURE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = SEORankingScraper(
                domains=["bookchaowalit.com"],
                keywords=["python developer thailand"],
                output_dir=temp_dir,
            )
            with patch(
                "scripts.scrape_seo_rankings.httpx.Client",
                lambda *args, **kwargs: FakeClient(FakeResponse(html)),
            ):
                result = asyncio.run(scraper.run())
            self.assertEqual(result[0]["source"], "seo_rankings")
            self.assertEqual(result[0]["count"], 1)
            with (Path(temp_dir) / "seo_rankings.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["http_status"], "200")
            raw = json.loads((Path(temp_dir) / "seo_rankings_raw.json").read_text(encoding="utf-8"))
            self.assertFalse(raw["rank_collected"])

            scraper_fail = SEORankingScraper(
                domains=["bookchaowalit.com"],
                keywords=["python developer thailand"],
                output_dir=temp_dir,
            )
            with patch(
                "scripts.scrape_seo_rankings.httpx.Client",
                lambda *args, **kwargs: FakeClient(FakeResponse("", status_code=403)),
            ):
                with self.assertRaisesRegex(ValueError, "no reachable"):
                    asyncio.run(scraper_fail.run())


if __name__ == "__main__":
    unittest.main()
