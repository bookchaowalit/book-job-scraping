import unittest
from pathlib import Path

from restaurants.wongnai_scraper import (
    build_page_url,
    canonical_url,
    normalize_locations,
    parse_html,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "wongnai_restaurants.html"


class WongnaiScraperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = FIXTURE.read_text(encoding="utf-8")

    def test_parse_filters_to_bangkok_and_deduplicates(self):
        state, rows = parse_html(
            self.html,
            "https://www.wongnai.com/restaurants?locationKey=1",
            locations=["bangkok"],
            page_number=2,
        )

        self.assertEqual(state["store"]["searchResult"]["value"]["p"], 1)
        self.assertEqual([row["restaurant_id"] for row in rows], ["1001", "1003"])
        self.assertEqual(rows[0]["city"], "กรุงเทพมหานคร")
        self.assertEqual(rows[0]["district"], "ปทุมวัน")
        self.assertEqual(rows[0]["review_count"], 120)
        self.assertEqual(rows[0]["price_range_value"], 2)
        self.assertEqual(rows[0]["page_number"], 2)
        self.assertTrue(all(row["location"] == "bangkok" for row in rows))
        self.assertTrue(all(row["url"].startswith("https://www.wongnai.com/restaurants/") for row in rows))
        self.assertFalse(any("Chiang" in row["name"] for row in rows))

    def test_canonical_and_page_urls_strip_tracking_and_bound_pagination(self):
        self.assertEqual(
            canonical_url("/restaurants/123Ab-my-place?_st=tracking"),
            "https://www.wongnai.com/restaurants/123Ab-my-place",
        )
        page_url = build_page_url(
            "https://www.wongnai.com/restaurants?locationKey=1",
            page_number=3,
            page_size=100,
        )
        self.assertIn("page.number=3", page_url)
        self.assertIn("page.size=100", page_url)
        self.assertIn("rerank=false", page_url)

    def test_rejects_missing_or_unknown_contract_values(self):
        with self.assertRaises(ValueError):
            parse_html("<html><body>no embedded state</body></html>")
        with self.assertRaises(ValueError):
            normalize_locations(["mars"])
        with self.assertRaises(ValueError):
            canonical_url("https://example.com/restaurants/123-place")


if __name__ == "__main__":
    unittest.main()
