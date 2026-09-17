import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_facebook_group_capture import validate_group_capture_file, validate_group_capture_rows
from scripts.import_facebook_group_posts import (
    GROUP_FIELDNAMES,
    canonical_group_url,
    canonical_post_url,
    import_facebook_group_rows,
    load_group_rows,
    write_group_outputs,
)
from scripts.review_facebook_group_posts import apply_review, load_capture, write_review_outputs


FIXTURE = Path(__file__).parent / "fixtures" / "facebook_group_posts_export.csv"


class FacebookGroupCaptureTests(unittest.TestCase):
    def test_public_rows_are_kept_and_duplicate_post_urls_are_removed(self):
        raw, source_rows = load_group_rows(FIXTURE)
        rows, stats, quarantine = import_facebook_group_rows(
            source_rows,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            captured_at="2026-09-14T00:00:00Z",
        )

        self.assertEqual(stats["input_rows"], 6)
        self.assertEqual(stats["accepted_rows"], 3)
        self.assertEqual(stats["candidate_rows"], 2)
        self.assertEqual(stats["duplicate_rows"], 1)
        self.assertEqual(stats["quarantined_rows"], 2)
        self.assertEqual({row["post_id"] for row in rows}, {"1001", "1002", "1003"})
        self.assertTrue(all(row["visibility"] == "public" for row in rows))
        self.assertTrue(all(row["contact_public"] == "True" for row in rows))
        self.assertEqual(len(quarantine), 2)
        self.assertEqual({item["reason"] for item in quarantine}, {"nonpublic_visibility"})

    def test_private_rows_require_gate_and_governance_metadata(self):
        raw, source_rows = load_group_rows(FIXTURE)
        private = [row for row in source_rows if row["visibility"] == "private"]
        rows, stats, quarantine = import_facebook_group_rows(
            private,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            captured_at="2026-09-14T00:00:00Z",
            allow_private=True,
            retention_until="2026-12-31T00:00:00Z",
            terms_basis_ref="group-owner-approved-2026-09-14",
        )

        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(quarantine, [])
        self.assertEqual(rows[0]["visibility"], "private")
        self.assertEqual(rows[0]["contact_public"], "False")
        self.assertEqual(rows[0]["retention_until"], "2026-12-31T00:00:00Z")
        self.assertEqual(rows[0]["terms_basis_ref"], "group-owner-approved-2026-09-14")
        self.assertEqual(rows[0]["outreach_status"], "not_contacted")

    def test_unknown_visibility_is_held_until_operator_labels_it(self):
        _, source_rows = load_group_rows(FIXTURE)
        unknown = [row for row in source_rows if row["visibility"] == "unknown"]
        rows, stats, quarantine = import_facebook_group_rows(unknown)

        self.assertEqual(rows, [])
        self.assertEqual(stats["accepted_rows"], 0)
        self.assertEqual(quarantine[0]["reason"], "nonpublic_visibility")

    def test_urls_are_canonical_and_caller_contact_columns_are_ignored(self):
        self.assertEqual(
            canonical_group_url("https://www.facebook.com/groups/sample/?utm_source=feed"),
            "https://facebook.com/groups/sample",
        )
        self.assertEqual(
            canonical_post_url("https://m.facebook.com/story.php?story_fbid=77&id=9&utm_source=feed")[1],
            "77",
        )
        rows, stats, quarantine = import_facebook_group_rows(
            [
                {
                    "group_url": "https://facebook.com/groups/sample",
                    "post_url": "https://facebook.com/groups/sample/posts/77",
                    "text": "สอบถามราคาเท่านั้น",
                    "visibility": "public",
                    "text_complete": "true",
                    "capture_method": "chrome_extension_visible_tab",
                    "contact_email": "attacker@example.test",
                }
            ],
            captured_at="2026-09-14T00:00:00Z",
        )
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(quarantine, [])
        self.assertEqual(rows[0]["contact_email"], "")
        self.assertEqual(rows[0]["lead_review_status"], "unqualified")

    def test_unknown_gate_still_requires_governance(self):
        _, source_rows = load_group_rows(FIXTURE)
        unknown = [row for row in source_rows if row["visibility"] == "unknown"]
        rows, stats, quarantine = import_facebook_group_rows(
            unknown,
            allow_unknown=True,
        )
        self.assertEqual(rows, [])
        self.assertEqual(stats["accepted_rows"], 0)
        self.assertEqual(quarantine[0]["reason"], "nonpublic_governance_required")

    def test_validator_reports_incomplete_visibility_and_strict_quality_mode(self):
        _, source_rows = load_group_rows(FIXTURE)
        unknown = [row for row in source_rows if row["visibility"] == "unknown"]
        rows, stats, quarantine = import_facebook_group_rows(
            unknown,
            allow_unknown=True,
            retention_until="2026-12-31T00:00:00Z",
            terms_basis_ref="group-owner-approved-2026-09-14",
        )
        self.assertEqual(stats["accepted_rows"], 1)
        self.assertEqual(quarantine, [])

        report = validate_group_capture_rows(rows)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["quality"]["incomplete_text_rows"], 1)
        self.assertEqual(report["quality"]["visibility_counts"]["unknown"], 1)
        self.assertEqual(
            {warning["code"] for warning in report["warnings"]},
            {"text_incomplete", "visibility_unknown"},
        )

        strict_report = validate_group_capture_rows(rows, require_complete=True)
        self.assertFalse(strict_report["ok"])
        self.assertIn("text_incomplete", {error["code"] for error in strict_report["errors"]})

    def test_review_updates_only_pending_rows_and_keeps_outreach_locked(self):
        raw, source_rows = load_group_rows(FIXTURE)
        rows, stats, quarantine = import_facebook_group_rows(
            source_rows[:2],
            captured_at="2026-09-14T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = write_group_outputs(
                rows,
                quarantine,
                stats,
                output_dir=Path(directory),
                raw_input=raw,
                input_path=FIXTURE,
                input_sha256=hashlib.sha256(raw).hexdigest(),
                captured_at="2026-09-14T00:00:00Z",
            )
            _, loaded = load_capture(Path(paths["snapshot"]))
            reviewed, audit, review_stats = apply_review(
                loaded,
                row_numbers=[1],
                decision="approved",
                reviewer_id="reviewer-1",
                reviewed_at="2026-09-14T10:00:00Z",
            )
            reviewed_paths = write_review_outputs(Path(directory) / "reviewed.csv", reviewed, audit)
            self.assertEqual(review_stats["pending_remaining"], 1)
            self.assertEqual(reviewed[0]["review_decision"], "approved")
            self.assertEqual(reviewed[0]["outreach_status"], "not_contacted")
            self.assertNotIn("agent@example.test", Path(reviewed_paths["audit"]).read_text(encoding="utf-8"))

    def test_group_output_has_contract_headers_and_passes_validator(self):
        raw, source_rows = load_group_rows(FIXTURE)
        rows, stats, quarantine = import_facebook_group_rows(
            source_rows[:2],
            input_sha256=hashlib.sha256(raw).hexdigest(),
            captured_at="2026-09-14T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = write_group_outputs(
                rows,
                quarantine,
                stats,
                output_dir=Path(directory),
                raw_input=raw,
                input_path=FIXTURE,
                input_sha256=hashlib.sha256(raw).hexdigest(),
                captured_at="2026-09-14T00:00:00Z",
            )
            path = Path(paths["snapshot"])
            report = validate_group_capture_file(path)
            self.assertTrue(report["ok"], report)
            with path.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), GROUP_FIELDNAMES)
            manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
            self.assertTrue(manifest["human_review_required"])
            self.assertNotIn("owner@example.test", Path(paths["manifest"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
