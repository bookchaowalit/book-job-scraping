import unittest

from property.social_leads import SOCIAL_FIELDNAMES
from scripts.check_property_social_capture import validate_capture_rows


def _row(**overrides):
    row = {field: "" for field in SOCIAL_FIELDNAMES}
    row.update(
        {
            "captured_at": "2026-09-14T00:00:00+00:00",
            "scraped_at": "2026-09-14T00:00:00+00:00",
            "social_query": "site:facebook.com condo Bangkok",
            "title": "Public property listing",
            "type": "social_property_lead",
            "url": "https://facebook.com/property/1",
            "description": "รับ co-agent",
            "source_channel": "social_search",
            "source_platform": "facebook",
            "contact_source_url": "https://facebook.com/property/1",
            "contact_role": "unknown",
            "co_agent_status": "yes",
            "contact_confidence": "medium",
            "contact_public": "True",
            "lead_review_status": "co_agent_candidate",
            "review_decision": "pending",
            "outreach_status": "not_contacted",
        }
    )
    row.update(overrides)
    return row


class PropertySocialQualityTests(unittest.TestCase):
    def test_accepts_pending_public_row_with_contract_fields(self):
        report = validate_capture_rows([_row()])

        self.assertTrue(report["ok"])
        self.assertEqual(report["row_count"], 1)
        self.assertEqual(report["errors"], [])

    def test_rejects_invalid_source_and_outreach_before_review(self):
        report = validate_capture_rows(
            [
                _row(
                    url="https://evil.example/property/1",
                    contact_source_url="https://evil.example/property/1",
                    source_platform="x",
                    contact_public="False",
                    captured_at="not-a-timestamp",
                    outreach_status="contacted",
                )
            ]
        )

        self.assertFalse(report["ok"])
        self.assertGreaterEqual(len(report["errors"]), 4)
        self.assertIn(
            {"row": 2, "code": "invalid_source_platform"}, report["errors"]
        )
        self.assertIn({"row": 2, "code": "outreach_not_approved"}, report["errors"])

    def test_rejects_non_https_social_source(self):
        report = validate_capture_rows(
            [_row(url="http://facebook.com/property/1", contact_source_url="http://facebook.com/property/1")]
        )

        self.assertFalse(report["ok"])
        self.assertIn({"row": 2, "code": "invalid_source_url"}, report["errors"])

    def test_reviewed_outreach_requires_reviewer_and_timestamp(self):
        pending = validate_capture_rows([_row(review_decision="approved")])
        self.assertFalse(pending["ok"])
        self.assertIn(
            {"row": 2, "code": "reviewer_required"}, pending["errors"]
        )

        reviewed = validate_capture_rows(
            [
                _row(
                    review_decision="approved",
                    reviewed_at="2026-09-14T01:00:00+00:00",
                    reviewer_id="reviewer-1",
                    outreach_status="approved_to_contact",
                )
            ]
        )
        self.assertTrue(reviewed["ok"])

    def test_governance_gate_requires_retention_and_terms_reference(self):
        missing = validate_capture_rows([_row()], require_governance=True)
        self.assertFalse(missing["ok"])
        self.assertIn(
            {"row": 2, "code": "retention_until_required"}, missing["errors"]
        )
        self.assertIn(
            {"row": 2, "code": "terms_basis_ref_required"}, missing["errors"]
        )

        governed = validate_capture_rows(
            [
                _row(
                    retention_until="2026-10-14T00:00:00+00:00",
                    terms_basis_ref="decision/property-social-2026-09-14",
                )
            ],
            require_governance=True,
        )
        self.assertTrue(governed["ok"])


if __name__ == "__main__":
    unittest.main()
