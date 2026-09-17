import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.check_property_capture import validate_capture_rows
from scripts.import_property_leads import import_property_rows, load_rows, write_outputs
from scripts.review_property_leads import (
    apply_review,
    load_capture,
    main,
    write_review_outputs,
)


FIXTURE = Path(__file__).parent / "fixtures" / "property_owner_coagent_export.csv"


class PropertyReviewTests(unittest.TestCase):
    def _snapshot(self, directory: str) -> Path:
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

    def test_apply_review_records_decision_without_authorizing_outreach(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(directory)
            raw, rows = load_capture(path)
            reviewed, audit, stats = apply_review(
                rows,
                row_numbers=[1, 2],
                decision="approved",
                reviewer_id="owner-reviewer",
                reviewed_at="2026-09-14T01:02:03Z",
                input_sha256=hashlib.sha256(raw).hexdigest(),
            )

        self.assertEqual(stats, {"selected": 2, "updated": 2, "pending_remaining": 2})
        self.assertEqual([row["review_decision"] for row in reviewed[:2]], ["approved", "approved"])
        self.assertTrue(all(row["reviewed_at"] == "2026-09-14T01:02:03Z" for row in reviewed[:2]))
        self.assertTrue(all(row["reviewer_id"] == "owner-reviewer" for row in reviewed[:2]))
        self.assertTrue(all(row["outreach_status"] == "not_contacted" for row in reviewed[:2]))
        self.assertEqual(len(audit), 2)
        self.assertNotIn("owner@example.test", str(audit))
        self.assertTrue(validate_capture_rows(reviewed)["ok"])

    def test_cli_writes_reviewed_snapshot_and_redacted_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(directory)
            output = Path(directory) / "reviewed.csv"
            result = main(
                [
                    "--input",
                    str(path),
                    "--output",
                    str(output),
                    "--reviewer-id",
                    "owner-reviewer",
                    "--decision",
                    "rejected",
                    "--rows",
                    "3",
                ]
            )
            self.assertEqual(result, 0)
            self.assertTrue(output.exists())
            audit = output.parent / "property_owner_coagent_review_history.csv"
            self.assertTrue(audit.exists())
            with output.open(newline="", encoding="utf-8") as handle:
                reviewed = list(csv.DictReader(handle))
            self.assertEqual(reviewed[2]["review_decision"], "rejected")
            self.assertEqual(reviewed[2]["outreach_status"], "not_contacted")
            self.assertNotIn("owner@example.test", audit.read_text(encoding="utf-8"))

    def test_cli_refuses_re_review_of_non_pending_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(directory)
            output = Path(directory) / "reviewed.csv"
            self.assertEqual(
                main(
                    [
                        "--input",
                        str(path),
                        "--output",
                        str(output),
                        "--reviewer-id",
                        "owner-reviewer",
                        "--decision",
                        "approved",
                        "--rows",
                        "1",
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "--input",
                        str(output),
                        "--output",
                        str(Path(directory) / "reviewed-again.csv"),
                        "--reviewer-id",
                        "owner-reviewer",
                        "--decision",
                        "rejected",
                        "--rows",
                        "1",
                    ]
                ),
                2,
            )

    def test_cli_list_pending_is_redacted_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._snapshot(directory)
            self.assertEqual(main(["--input", str(path), "--list-pending"]), 0)
            self.assertFalse((Path(directory) / "property_owner_coagent_review_history.csv").exists())


if __name__ == "__main__":
    unittest.main()
