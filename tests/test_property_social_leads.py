import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from property.social_leads import extract_social_leads
from scripts.scrape_property_social import BRAVE_SEARCH_API_URL, collect_social_leads


FIXTURE = Path(__file__).parent / "fixtures" / "property_social_results.json"


class PropertySocialLeadTests(unittest.TestCase):
    def test_keeps_public_social_results_and_extracts_co_agent_contact(self):
        rows = extract_social_leads(
            [
                {
                    "title": "คอนโดอโศก รับ co-agent",
                    "url": "https://www.facebook.com/groups/example/posts/123/?utm_source=search",
                    "description": "เจ้าของขายเอง โทร 081-234-5678 LINE: @อโศก",
                },
                {
                    "title": "Agent condo listing",
                    "url": "https://www.instagram.com/condo.agent/",
                    "description": "รับ co-agent ติดต่อ agent@example.com",
                },
                {"title": "Unrelated result", "url": "https://example.com/1"},
            ],
            query="คอนโด อโศก รับ co-agent",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source_channel"], "social_search")
        self.assertEqual(rows[0]["source_platform"], "facebook")
        self.assertEqual(rows[0]["type"], "social_property_lead")
        self.assertEqual(rows[0]["contact_facebook"], "https://facebook.com/groups/example/posts/123")
        self.assertEqual(rows[0]["scraped_at"], rows[0]["captured_at"])
        self.assertEqual(rows[0]["co_agent_status"], "yes")
        self.assertEqual(rows[0]["contact_phone"], "0812345678")
        self.assertTrue(rows[0]["contact_public"])
        self.assertEqual(rows[1]["source_platform"], "instagram")
        self.assertEqual(rows[1]["contact_email"], "agent@example.com")

    def test_deduplicates_tracking_variants_and_does_not_infer_role(self):
        rows = extract_social_leads(
            [
                {"title": "Listing", "url": "https://facebook.com/page/1?utm_campaign=x"},
                {"title": "Listing duplicate", "url": "https://www.facebook.com/page/1"},
            ],
            query="property Bangkok",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contact_role"], "unknown")
        self.assertEqual(rows[0]["co_agent_status"], "unknown")

    @patch.dict(
        os.environ,
        {"BRAVE_SEARCH_API_KEY": "test-key", "BRAVE_SEARCH_STORAGE_APPROVED": "1"},
        clear=True,
    )
    @patch("scripts.scrape_property_social.httpx.get")
    def test_collection_uses_official_api_and_bounds_results(self, mock_get):
        response = Mock()
        response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "คอนโดรับ co-agent",
                        "url": "https://facebook.com/property/1",
                        "description": "เจ้าของขายเอง โทร 081-234-5678",
                    },
                    {
                        "title": "Second result",
                        "url": "https://facebook.com/property/2",
                        "description": "นายหน้า",
                    },
                ]
            }
        }
        mock_get.return_value = response

        rows = collect_social_leads("condo Bangkok", platforms=["facebook"], limit=1)

        self.assertEqual(len(rows), 1)
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], BRAVE_SEARCH_API_URL)
        self.assertEqual(kwargs["params"]["count"], 1)
        self.assertEqual(kwargs["params"]["country"], "TH")
        self.assertEqual(kwargs["headers"]["X-Subscription-Token"], "test-key")

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.scrape_property_social.httpx.get")
    def test_missing_storage_approval_fails_closed_before_network(self, mock_get):
        self.assertEqual(
            collect_social_leads("condo Bangkok", platforms=["facebook"], limit=5), []
        )
        mock_get.assert_not_called()

    @patch.dict(
        os.environ,
        {"BRAVE_SEARCH_API_KEY": "test-key", "BRAVE_SEARCH_STORAGE_APPROVED": "1"},
        clear=True,
    )
    @patch("scripts.scrape_property_social.httpx.get")
    def test_malformed_api_results_fail_closed(self, mock_get):
        response = Mock()
        response.json.return_value = {"web": {"results": None}}
        mock_get.return_value = response

        self.assertEqual(
            collect_social_leads("condo Bangkok", platforms=["facebook"], limit=5), []
        )

    @patch.dict(
        os.environ,
        {
            "BRAVE_SEARCH_API_KEY": "test-key",
            "BRAVE_SEARCH_STORAGE_APPROVED": "1",
            "PROPERTY_SOCIAL_RETENTION_UNTIL": "2026-10-14T00:00:00+00:00",
            "PROPERTY_SOCIAL_TERMS_BASIS_REF": "decision/property-social-2026-09-14",
        },
        clear=True,
    )
    @patch("scripts.scrape_property_social.httpx.get")
    def test_collection_attaches_governance_metadata(self, mock_get):
        response = Mock()
        response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Public property listing",
                        "url": "https://facebook.com/property/1",
                        "description": "รับ co-agent",
                    }
                ]
            }
        }
        mock_get.return_value = response

        rows = collect_social_leads("condo Bangkok", platforms=["facebook"], limit=5)

        self.assertEqual(rows[0]["retention_until"], "2026-10-14T00:00:00+00:00")
        self.assertEqual(
            rows[0]["terms_basis_ref"], "decision/property-social-2026-09-14"
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.scrape_property_social.httpx.get")
    def test_fixture_mode_is_offline_and_extracts_all_supported_platforms(self, mock_get):
        rows = collect_social_leads(fixture_path=FIXTURE, limit=20)

        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["source_platform"] for row in rows},
            {"facebook", "instagram", "tiktok", "line"},
        )
        self.assertTrue(all(row["review_decision"] == "pending" for row in rows))
        self.assertTrue(all(row["outreach_status"] == "not_contacted" for row in rows))
        self.assertTrue(any(row["co_agent_status"] == "yes" for row in rows))
        mock_get.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.scrape_property_social.httpx.get")
    def test_malformed_fixture_fails_closed_without_network(self, mock_get):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "malformed.json"
            fixture.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixture must be a JSON list"):
                collect_social_leads(fixture_path=fixture)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
