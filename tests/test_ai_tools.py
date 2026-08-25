import unittest
from pathlib import Path

from scripts.scrape_ai_tools import (
    build_page_url,
    canonical_tool_url,
    normalize_categories,
    parse_html,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "futurepedia_ai_tools.html"


class AIToolScraperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = FIXTURE.read_text(encoding="utf-8")

    def test_parse_cards_keeps_canonical_tools_and_fields(self):
        rows = parse_html(
            self.html,
            "https://www.futurepedia.io/ai-tools",
            "ai-agents",
            page_number=2,
        )

        self.assertEqual([row["tool_id"] for row in rows], ["alpha-ai", "beta-code"])
        self.assertEqual(rows[0]["name"], "Alpha AI")
        self.assertEqual(rows[0]["categories"], "ai agents,workflows")
        self.assertEqual(rows[0]["rating"], 4.5)
        self.assertEqual(rows[0]["rating_count"], 12)
        self.assertEqual(rows[0]["bookmark_count"], 240)
        self.assertEqual(rows[0]["pricing"], "Free Trial")
        self.assertEqual(rows[0]["website_url"], "https://alpha.example.com/")
        self.assertEqual(rows[0]["source_category"], "ai-agents")
        self.assertEqual(rows[0]["page_number"], 2)
        self.assertEqual(rows[1]["rating_count"], 0)

    def test_url_and_request_bounds(self):
        self.assertEqual(
            canonical_tool_url("https://www.futurepedia.io/tool/alpha-ai?ref=card"),
            "https://www.futurepedia.io/tool/alpha-ai",
        )
        page_url = build_page_url("https://www.futurepedia.io/ai-tools", "ai-agents", 3)
        self.assertEqual(page_url, "https://www.futurepedia.io/ai-tools/ai-agents?page=3")
        self.assertEqual(normalize_categories("ai-agents,productivity"), ["ai-agents", "productivity"])

    def test_rejects_invalid_contract_values(self):
        with self.assertRaises(ValueError):
            canonical_tool_url("https://example.com/tool/alpha-ai")
        with self.assertRaises(ValueError):
            normalize_categories(["not a slug"])
        with self.assertRaises(ValueError):
            build_page_url("https://www.futurepedia.io/ai-tools", "ai-agents", 0)


if __name__ == "__main__":
    unittest.main()
