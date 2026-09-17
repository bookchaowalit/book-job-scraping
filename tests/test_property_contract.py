import json
import unittest
from pathlib import Path

from property.social_leads import SOCIAL_FIELDNAMES
from scripts.scrape_property_listings import PROPERTY_FIELDNAMES


CONTRACT = Path(__file__).parents[1] / "contracts" / "property-capture.v1.json"


class PropertyCaptureContractTests(unittest.TestCase):
    def test_contract_declares_reviewable_contact_and_social_fields(self):
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        properties = payload["properties"]

        for field in (
            "contact_role",
            "co_agent_status",
            "contact_phone",
            "contact_email",
            "contact_line",
            "contact_facebook",
            "contact_instagram",
            "contact_tiktok",
            "contact_source_url",
            "contact_evidence",
            "contact_confidence",
            "lead_review_status",
            "review_decision",
            "reviewed_at",
            "reviewer_id",
            "outreach_status",
            "retention_until",
            "terms_basis_ref",
        ):
            self.assertIn(field, properties)
        self.assertEqual(payload["x-privacy-class"], "public_source_with_terms")
        self.assertTrue(payload["x-human-review-required"])
        self.assertEqual(payload["schema_version"], "property.v1")
        self.assertIn("scraped_at", payload["required"])
        self.assertIn("scraped_at", properties)
        # Review fields are emitted by current producers but remain optional in
        # property.v1 so older captures can still be replayed.
        self.assertNotIn("review_decision", payload["required"])
        self.assertNotIn("outreach_status", payload["required"])
        for field in (*PROPERTY_FIELDNAMES, *SOCIAL_FIELDNAMES):
            self.assertIn(field, properties, field)


if __name__ == "__main__":
    unittest.main()
