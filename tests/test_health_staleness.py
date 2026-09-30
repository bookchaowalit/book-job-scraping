"""Stale or missing collection output is critical; apply-workflow files are not."""
import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pipeline_health_monitor as phm  # noqa: E402


class HealthStalenessTest(unittest.TestCase):
    def run_check(self, tmp):
        with patch.object(phm, "DATA_DIR", Path(tmp)), \
             patch.object(phm, "HEALTH_REPORT", Path(tmp) / "report.json"), \
             redirect_stdout(io.StringIO()):
            return phm.run_health_check()

    def write(self, tmp, name, age_hours):
        path = Path(tmp) / name
        path.write_text("title\nx\n", encoding="utf-8")
        old = time.time() - age_hours * 3600
        os.utime(path, (old, old))

    def test_stale_collection_is_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, "job_postings.csv", 30)
            self.write(tmp, "matched_jobs.csv", 1)
            report = self.run_check(tmp)
        self.assertEqual(report["overall_status"], "critical")
        self.assertTrue(any("job_postings.csv" in i for i in report["issues"]))

    def test_missing_apply_workflow_files_only_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, "job_postings.csv", 1)
            self.write(tmp, "matched_jobs.csv", 1)
            report = self.run_check(tmp)
        self.assertNotEqual(report["overall_status"], "critical")
        self.assertIn("Data missing: apply_tracker.csv", report["warnings"])


if __name__ == "__main__":
    unittest.main()
