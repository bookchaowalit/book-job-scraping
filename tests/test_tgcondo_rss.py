import asyncio
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scrape_tgcondo_rss import (
    FEED_URL,
    TGCondoRSSScraper,
    canonical_listing_url,
    collect_listings,
    normalize_feed_url,
    parse_feed,
    parse_public_agent_contact,
)


FIXTURE = Path(__file__).parent / "fixtures" / "tgcondo_condo_rent.xml"


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.text = content.decode("utf-8")

    def raise_for_status(self):
        return None


class TGCondoRSSTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()

    def test_feed_and_listing_urls_are_allowlisted(self):
        self.assertEqual(normalize_feed_url(FEED_URL), FEED_URL)
        self.assertEqual(
            normalize_feed_url(
                "https://tgcondo.com/Property-Types/condo-for-rent/?type=rss&format=feed"
            ),
            FEED_URL.replace("www.", ""),
        )
        self.assertEqual(
            canonical_listing_url(
                "https://www.tgcondo.com/Property/sample-1?utm_source=rss#details"
            ),
            "https://www.tgcondo.com/Property/sample-1",
        )
        with self.assertRaises(ValueError):
            normalize_feed_url("https://tgcondo.com/Property-Types/condo-for-sale?format=feed&type=rss")
        with self.assertRaises(ValueError):
            canonical_listing_url("https://tgcondo.com.evil.example/Property/sample-1")

    def test_parse_feed_keeps_priced_rows_and_extracts_attributes(self):
        parsed, rows = parse_feed(self.raw, limit=10)

        self.assertEqual(parsed.feed.title, "Property Results For Condo for Rent")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["price"], 28000.0)
        self.assertEqual(rows[1]["price"], 22000.0)
        self.assertEqual(rows[0]["listing_type"], "condo_rent_bkk")
        self.assertEqual(rows[0]["source_channel"], "listing")
        self.assertEqual(rows[0]["source_platform"], "tgcondo")
        self.assertEqual(rows[0]["bedrooms"], 1)
        self.assertEqual(rows[0]["bathrooms"], 1)
        self.assertEqual(rows[0]["area_sqm"], 35)
        self.assertEqual(rows[1]["bedrooms"], 1)
        self.assertEqual(rows[0]["location"], "Sukhumvit Road, Bangkok")
        self.assertEqual(
            rows[0]["url"], "https://www.tgcondo.com/Property/sample-sukhumvit-rent-1001"
        )
        self.assertEqual(rows[0]["contact_role"], "unknown")
        self.assertEqual(rows[0]["co_agent_status"], "unknown")
        self.assertEqual(rows[0]["outreach_status"], "not_contacted")

    def test_public_agent_contact_parser_keeps_explicit_card_signals(self):
        details = parse_public_agent_contact(
            """
            <div class='agent-card'>
              <a href='/Agent-Properties/sample-agency'>Sample Agency</a>
              <span>Line ID: sampleline</span>
              <span>M: 081-234-5678</span>
              <a href='mailto:agent@example.test'>agent@example.test</a>
            </div>
            """,
            "https://www.tgcondo.com/Property/sample-1",
        )

        self.assertEqual(details["contact_name"], "Sample Agency")
        self.assertEqual(details["contact_role"], "agent")
        self.assertEqual(details["contact_phone"], "0812345678")
        self.assertEqual(details["contact_line"], "sampleline")
        self.assertEqual(details["contact_email"], "agent@example.test")
        self.assertEqual(details["co_agent_status"], "unknown")
        self.assertEqual(details["lead_review_status"], "needs_human_review")

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.scrape_tgcondo_rss.fetch_public_agent_contact")
    @patch("scripts.scrape_tgcondo_rss.fetch_feed")
    def test_contact_enrichment_is_held_without_governance(self, mock_fetch, mock_contact):
        mock_fetch.return_value = self.raw

        _, rows = collect_listings(include_agent_contact=True, limit=2)

        self.assertEqual(len(rows), 2)
        mock_contact.assert_not_called()
        self.assertTrue(all(row["contact_phone"] == "" for row in rows))

    def test_run_writes_raw_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = TGCondoRSSScraper(limit=2, output_dir=temp_dir)
            with patch(
                "scripts.scrape_tgcondo_rss.httpx.get",
                return_value=FakeResponse(self.raw),
            ):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "tgcondo_condo_rent")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "tgcondo_condo_rent_raw.xml").exists())
            with (output_dir / "tgcondo_condo_rent.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_platform"], "tgcondo")
            with (output_dir / "tgcondo_condo_rent_history.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
