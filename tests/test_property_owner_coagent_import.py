import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_property_leads import (
    IMPORT_FIELDNAMES,
    canonical_source_url,
    import_property_rows,
    load_rows,
    main,
    write_outputs,
)


FIXTURE = Path(__file__).parent / "fixtures" / "property_owner_coagent_export.csv"


class PropertyOwnerCoAgentImportTests(unittest.TestCase):
    def test_fixture_keeps_explicit_owner_and_coagent_rows_and_deduplicates(self):
        raw, rows = load_rows(FIXTURE)
        accepted, stats, quarantine = import_property_rows(
            rows,
            captured_at="2026-09-14T00:00:00Z",
            input_sha256=hashlib.sha256(raw).hexdigest(),
        )

        self.assertEqual(stats["input_rows"], 6)
        self.assertEqual(stats["candidate_rows"], 5)
        self.assertEqual(stats["accepted_rows"], 4)
        self.assertEqual(stats["duplicate_rows"], 1)
        self.assertEqual(stats["quarantined_rows"], 1)
        self.assertEqual(len(accepted), 4)
        self.assertEqual({row["source_platform"] for row in accepted}, {"zmyhome", "meezub", "ennxo", "facebook"})
        self.assertEqual(accepted[0]["url"], "https://zmyhome.com/buy/condo/sample-owner-1")
        self.assertEqual(accepted[0]["contact_role"], "owner")
        self.assertEqual(accepted[0]["co_agent_status"], "yes")
        self.assertEqual(accepted[0]["price"], "5500000")
        self.assertEqual(accepted[0]["contact_phone"], "0810000000")
        self.assertEqual(accepted[0]["review_decision"], "pending")
        self.assertEqual(accepted[0]["outreach_status"], "not_contacted")
        self.assertEqual(accepted[3]["source_channel"], "social_search")
        self.assertEqual(quarantine[0]["reason"], "missing_owner_or_coagent_signal")
        self.assertNotIn("url", quarantine[0])

    def test_include_unqualified_keeps_a_review_row(self):
        _, rows = load_rows(FIXTURE)
        accepted, stats, quarantine = import_property_rows(
            rows,
            captured_at="2026-09-14T00:00:00Z",
            include_unqualified=True,
        )

        self.assertEqual(stats["accepted_rows"], 5)
        self.assertEqual(stats["duplicate_rows"], 1)
        self.assertEqual(stats["quarantined_rows"], 0)
        self.assertEqual(len(quarantine), 0)
        unqualified = next(row for row in accepted if row["source_platform"] == "livinginsider")
        self.assertEqual(unqualified["contact_role"], "unknown")
        self.assertEqual(unqualified["lead_review_status"], "unqualified")

    def test_url_allowlist_is_https_only_and_strips_tracking(self):
        self.assertEqual(
            canonical_source_url("https://www.meezub.com/member/1/?utm_source=x&sort=latest"),
            ("https://meezub.com/member/1?sort=latest", "meezub"),
        )
        self.assertEqual(
            canonical_source_url("https://m.facebook.com/public/1?fbclid=x"),
            ("https://facebook.com/public/1", "facebook"),
        )
        for value in (
            "http://zmyhome.com/listing/1",
            "https://zmyhome.com.evil.example/listing/1",
            "https://unknown.example/listing/1",
            "https://ddproperty.com/property/1",
            "https://user:pass@zmyhome.com/listing/1",
            "https://zmyhome.com:443/listing/1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_source_url(value)

    def test_json_data_items_and_structured_contact_fields_are_supported(self):
        payload = {
            "items": [
                {
                    "headline": "Public owner listing",
                    "href": "https://ennxo.com/product/structured-1",
                    "content": "owner sells direct; co-agent welcome",
                    "contact_phone": "081 111 2222",
                    "listing_type": "condo_sale_bkk",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            _, rows = load_rows(path)
        accepted, stats, _ = import_property_rows(rows, captured_at="2026-09-14T00:00:00Z")
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(accepted[0]["contact_role"], "owner")
        self.assertEqual(accepted[0]["co_agent_status"], "yes")
        self.assertEqual(accepted[0]["contact_phone"], "0811112222")
        self.assertEqual(accepted[0]["listing_type"], "condo_sale_bkk")

    def test_phone_number_is_not_mistaken_for_price_when_price_is_absent(self):
        accepted, stats, _ = import_property_rows(
            [
                {
                    "title": "Owner sample without price",
                    "url": "https://zmyhome.com/buy/condo/no-price",
                    "description": "เจ้าของขายเอง โทร 081-111-2222 รับ co-agent",
                }
            ],
            captured_at="2026-09-14T00:00:00Z",
        )
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(accepted[0]["price"], "")
        self.assertEqual(accepted[0]["contact_phone"], "0811112222")

    def test_csv_multiline_description_is_preserved_for_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            path.write_text(
                'title,url,description\n"Owner listing",https://meezub.com/member/multiline,"เจ้าของขายเอง\nรับ co-agent"\n',
                encoding="utf-8",
            )
            _, rows = load_rows(path)
        accepted, stats, _ = import_property_rows(rows, captured_at="2026-09-14T00:00:00Z")
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertIn("รับ co-agent", accepted[0]["description"])

    def test_outputs_are_contract_fields_and_manifest_does_not_contain_contact_values(self):
        raw, rows = load_rows(FIXTURE)
        accepted, stats, quarantine = import_property_rows(
            rows,
            captured_at="2026-09-14T00:00:00Z",
            input_sha256=hashlib.sha256(raw).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = write_outputs(
                accepted,
                quarantine,
                stats,
                output_dir=Path(directory),
                raw_input=raw,
                input_path=FIXTURE,
                input_sha256=hashlib.sha256(raw).hexdigest(),
                captured_at="2026-09-14T00:00:00Z",
            )
            with Path(paths["snapshot"]).open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, IMPORT_FIELDNAMES)
                output_rows = list(reader)
            self.assertEqual(len(output_rows), 4)
            manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "property.v1")
            self.assertEqual(manifest["stats"]["accepted_rows"], 4)
            self.assertNotIn("0810000000", json.dumps(manifest, ensure_ascii=False))
            self.assertEqual(Path(paths["raw_input"]).read_bytes(), raw)

    def test_cli_dry_run_makes_no_network_or_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            result = main(["--input", str(FIXTURE), "--output-dir", str(output), "--dry-run"])
            self.assertEqual(result, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
