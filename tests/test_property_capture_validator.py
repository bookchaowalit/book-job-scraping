import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.check_property_capture import validate_capture_file, validate_capture_rows
from scripts.import_property_leads import IMPORT_FIELDNAMES, import_property_rows, load_rows, write_outputs


FIXTURE = Path(__file__).parent / "fixtures" / "property_owner_coagent_export.csv"


class PropertyCaptureValidatorTests(unittest.TestCase):
    def _write_snapshot(self, directory: str) -> Path:
        raw, source_rows = load_rows(FIXTURE)
        rows, stats, quarantine = import_property_rows(
            source_rows,
            captured_at="2026-09-14T00:00:00Z",
            input_sha256=hashlib.sha256(raw).hexdigest(),
        )
        paths = write_outputs(
            rows,
            quarantine,
            stats,
            output_dir=Path(directory),
            raw_input=raw,
            input_path=FIXTURE,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            captured_at="2026-09-14T00:00:00Z",
        )
        return Path(paths["snapshot"])

    def test_imported_snapshot_passes_redacted_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            report = validate_capture_file(self._write_snapshot(directory))
        self.assertTrue(report["ok"])
        self.assertEqual(report["row_count"], 4)
        self.assertEqual(report["errors"], [])

    def test_validator_requires_governance_when_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_snapshot(directory)
            report = validate_capture_file(path, require_governance=True)
        self.assertFalse(report["ok"])
        self.assertTrue({error["code"] for error in report["errors"]} >= {"retention_until_required", "terms_basis_ref_required"})

    def test_validator_rejects_duplicate_or_mismatched_source_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_snapshot(directory)
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[1]["url"] = rows[0]["url"]
            rows[1]["contact_source_url"] = rows[0]["url"] + "/other"
            report = validate_capture_rows(rows)
        codes = {error["code"] for error in report["errors"]}
        self.assertIn("duplicate_source_url", codes)
        self.assertIn("source_url_mismatch", codes)

    def test_validator_rejects_noncanonical_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("title,url\nA,https://zmyhome.com/1\n", encoding="utf-8")
            report = validate_capture_file(path)
        self.assertFalse(report["ok"])
        self.assertIn("headers_do_not_match_property_v1", {error["code"] for error in report["errors"]})


if __name__ == "__main__":
    unittest.main()
