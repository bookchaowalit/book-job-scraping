import csv
import tempfile
import unittest
from pathlib import Path

from scripts.audit_property_demand_sources import (
    SOURCE_AUDIT_FIELDS,
    SOURCE_REGISTRY,
    write_audit_csv,
)


class PropertyDemandSourceAuditTests(unittest.TestCase):
    def test_registry_separates_listing_only_and_demand_sources(self):
        decisions = {row["collection_decision"] for row in SOURCE_REGISTRY}
        self.assertIn("include_demand", decisions)
        self.assertIn("exclude_demand", decisions)
        self.assertIn("blocked", decisions)
        self.assertIn("manual_export_only", decisions)

    def test_audit_csv_writes_metadata_without_page_payload(self):
        rows = [
            {
                "observed_at": "2026-09-16T00:00:00Z",
                "source_platform": "pantip",
                "source_url": "https://pantip.com/search?q=test",
                "source_role": "public_forum",
                "demand_capability": "demand_capable",
                "collection_decision": "include_demand",
                "http_status": "200",
                "robots_status": "200",
                "robots_allowed": "yes",
                "access_status": "reachable",
                "evidence": "public demand topic",
                "next_action": "human review",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "source-audit.csv"
            self.assertEqual(write_audit_csv(rows, output), 1)
            with output.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, SOURCE_AUDIT_FIELDS)
                saved = next(reader)

        self.assertEqual(saved["source_platform"], "pantip")
        self.assertNotIn("<html", saved["evidence"].lower())


if __name__ == "__main__":
    unittest.main()
