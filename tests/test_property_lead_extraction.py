import unittest

from property.lead_extraction import extract_contact_details, enrich_listing
from property.listing_config import build_page_url, property_source_platform, resolve_listing_type
from scripts.scrape_property_listings import extract_listings


class PropertyLeadExtractionTests(unittest.TestCase):
    def test_extracts_public_contact_and_co_agent_signal(self):
        text = (
            "ขายเอง เจ้าของห้อง รับ co-agent\n"
            "ติดต่อ: คุณสมชาย โทร 081-234-5678\n"
            "LINE: @homecondo https://www.facebook.com/homecondo"
        )

        details = extract_contact_details(text, "https://example.com/listing/123")

        self.assertEqual(details["contact_role"], "owner")
        self.assertEqual(details["co_agent_status"], "yes")
        self.assertEqual(details["contact_phone"], "0812345678")
        self.assertEqual(details["contact_line"], "@homecondo")
        self.assertEqual(details["contact_facebook"], "https://facebook.com/homecondo")
        self.assertEqual(details["contact_source_url"], "https://example.com/listing/123")
        self.assertTrue(details["contact_public"])
        self.assertIn("รับ co-agent", details["contact_evidence"])

    def test_no_co_agent_signal_wins_over_generic_agent_text(self):
        details = extract_contact_details(
            "Agent: Jane Doe โทร 02 123 4567 — ไม่รับ co-agent",
            "https://example.com/listing/456",
        )

        self.assertEqual(details["contact_role"], "agent")
        self.assertEqual(details["co_agent_status"], "no")
        self.assertEqual(details["contact_phone"], "021234567")
        self.assertEqual(
            extract_contact_details("รับเอเจ้นร่วมขาย", "https://example.com/agent")["co_agent_status"],
            "yes",
        )

    def test_email_and_url_slugs_do_not_infer_a_role(self):
        details = extract_contact_details(
            "คอนโดใกล้รถไฟฟ้า ติดต่อ agent@example.test https://example.com/owner-listing",
            "https://example.com/listing/1",
        )
        self.assertEqual(details["contact_role"], "unknown")
        self.assertEqual(details["co_agent_status"], "unknown")

    def test_enrich_listing_keeps_listing_data_and_marks_unknown(self):
        listing = {"title": "Condo near BTS", "description": "ราคา 2 ล้านบาท"}

        enriched = enrich_listing(listing, source_url="https://example.com/1")

        self.assertEqual(enriched["title"], listing["title"])
        self.assertEqual(enriched["contact_role"], "unknown")
        self.assertEqual(enriched["co_agent_status"], "unknown")
        self.assertEqual(enriched["contact_confidence"], "low")
        self.assertEqual(enriched["contact_source_url"], "https://example.com/1")
        self.assertEqual(enriched["review_decision"], "pending")
        self.assertEqual(enriched["outreach_status"], "not_contacted")
        self.assertEqual(enriched["reviewed_at"], "")
        self.assertEqual(enriched["reviewer_id"], "")

        untrusted = enrich_listing({"title": "Condo"}, source_url="example.com/1")
        self.assertEqual(untrusted["contact_source_url"], "")
        self.assertFalse(untrusted["contact_public"])

    def test_scheduler_alias_resolves_to_a_single_known_type(self):
        self.assertEqual(resolve_listing_type("condo_sale"), "condo_sale_bkk")
        self.assertEqual(resolve_listing_type("condo"), "condo_rent_bkk")

    def test_build_page_url_is_bounded_and_preserves_existing_query(self):
        self.assertEqual(
            build_page_url("https://example.com/search", 1),
            "https://example.com/search",
        )

    def test_property_source_allowlist_rejects_lookalike_hosts(self):
        self.assertEqual(property_source_platform("https://www.ddproperty.com/property/1"), "ddproperty")
        self.assertEqual(property_source_platform("https://www.tgcondo.com/Property/sample-1"), "tgcondo")
        self.assertEqual(property_source_platform("https://ddproperty.com.evil.example/property/1"), "")
        self.assertEqual(
            build_page_url("https://example.com/search?type=condo", 3),
            "https://example.com/search?type=condo&page=3",
        )

    def test_enrich_listing_reads_structured_public_contact_text(self):
        enriched = enrich_listing(
            {
                "title": "Condo",
                "contact_text": "เจ้าของห้อง โทร 081-555-1212 รับ co-agent",
            },
            source_url="https://example.com/listing/789",
        )

        self.assertEqual(enriched["contact_role"], "owner")
        self.assertEqual(enriched["contact_phone"], "0815551212")
        self.assertEqual(enriched["co_agent_status"], "yes")

    def test_listing_parser_keeps_contact_lines_with_the_listing(self):
        listings = extract_listings(
            "# Condo near BTS\n"
            "฿5,000,000\n"
            "ขายเอง เจ้าของห้อง รับ co-agent\n"
            "ติดต่อ: คุณเอ โทร 081-222-3333\n"
            "https://www.ddproperty.com/property/example",
            "condo_sale_bkk",
        )

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["contact_role"], "owner")
        self.assertEqual(listings[0]["co_agent_status"], "yes")
        self.assertEqual(listings[0]["contact_phone"], "0812223333")


if __name__ == "__main__":
    unittest.main()
