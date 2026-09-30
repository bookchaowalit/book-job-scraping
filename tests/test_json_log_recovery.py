"""An unreadable JSON run log must be kept, not overwritten with defaults."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import company_intel, cron_scheduler, followup_tracker, weekly_report

CORRUPT = '{"runs": [{"type": "daily"}, '  # truncated mid-write


class JsonLogRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch("builtins.print")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_kept(self, log_path: Path):
        backups = list(self.dir.glob(f"{log_path.name}.corrupt-*"))
        self.assertEqual(len(backups), 1, "unreadable log was not kept aside")
        self.assertEqual(backups[0].read_text(encoding="utf-8"), CORRUPT)

    def test_cron_scheduler_log_run(self):
        path = self.dir / "cron_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(cron_scheduler, "CRON_LOG", path):
            cron_scheduler.log_run("daily", {"ok": 1})
        self._assert_kept(path)
        self.assertEqual(len(json.loads(path.read_text())["runs"]), 1)

    def test_cron_scheduler_log_run_appends_to_valid_log(self):
        path = self.dir / "cron_log.json"
        path.write_text(json.dumps({"runs": [{"type": "weekly"}]}), encoding="utf-8")
        with mock.patch.object(cron_scheduler, "CRON_LOG", path):
            cron_scheduler.log_run("daily", {"ok": 1})
        self.assertEqual(len(json.loads(path.read_text())["runs"]), 2)
        self.assertEqual(list(self.dir.glob("*.corrupt-*")), [])

    def test_followup_tracker_log(self):
        path = self.dir / "followup_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(followup_tracker, "FOLLOWUP_LOG", path):
            followup_tracker.log_followup_run([{"company": "Acme"}], [])
        self._assert_kept(path)

    def test_company_intel_log(self):
        path = self.dir / "company_intel_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(company_intel, "COMPANY_INTEL_LOG", path):
            company_intel.log_enrichment([{"company": "Acme"}])
        self._assert_kept(path)

    def test_weekly_report_log_of_wrong_type(self):
        path = self.dir / "weekly_report_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(weekly_report, "WEEKLY_REPORT_LOG", path), mock.patch.object(
            weekly_report, "WEEKLY_REPORT_JSON", self.dir / "weekly_report.json"
        ):
            weekly_report.save_report({"generated_at": "2026-09-30"})
        self._assert_kept(path)
        self.assertEqual(len(json.loads(path.read_text())), 1)


if __name__ == "__main__":
    unittest.main()
