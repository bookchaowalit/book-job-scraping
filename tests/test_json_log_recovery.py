"""An unreadable JSON run log must be kept, not overwritten with defaults."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import (
    company_intel,
    cron_scheduler,
    followup_tracker,
    multi_resume_manager,
    networking_event_tracker,
    send_followup_emails,
    weekly_report,
)

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

    def test_followup_tracker_leaves_unreadable_log_in_place(self):
        # The sender reads the same file and refuses to run on an unreadable
        # one; renaming it would make the sender see no log at all.
        path = self.dir / "followup_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(followup_tracker, "FOLLOWUP_LOG", path):
            followup_tracker.log_followup_run([{"company": "Acme"}], [])
        self.assertEqual(path.read_text(encoding="utf-8"), CORRUPT)
        self.assertEqual(list(self.dir.glob("*.corrupt-*")), [])

    def test_followup_tracker_keeps_legacy_list_log_for_sender(self):
        path = self.dir / "followup_log.json"
        sent = [{"company": "Acme", "to": "jane@acme.example", "sent_at": "2026-01-10T09:00:00"}]
        path.write_text(json.dumps(sent), encoding="utf-8")
        with mock.patch.object(followup_tracker, "FOLLOWUP_LOG", path):
            followup_tracker.log_followup_run([{"company": "Acme"}], [])
        self.assertEqual(list(self.dir.glob("*.corrupt-*")), [], "valid legacy log was renamed")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["sent"], sent)
        self.assertEqual(len(saved["runs"]), 1)

        send_log = [{
            "status": "sent",
            "company": "Acme",
            "title": "Data Engineer",
            "to": "jane@acme.example",
            "sent_at": "2026-01-01T09:00:00",
        }]
        with mock.patch.object(send_followup_emails, "FOLLOWUP_LOG_FILE", path):
            followup_log = send_followup_emails.load_followup_log()
        self.assertEqual(send_followup_emails.build_followup_candidates(send_log, followup_log), [])

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

    def test_networking_events_are_kept(self):
        path = self.dir / "networking_events.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(networking_event_tracker, "EVENTS_FILE", path):
            networking_event_tracker.add_event("Meetup")
        self._assert_kept(path)
        self.assertEqual(len(json.loads(path.read_text())["events"]), 1)

    def test_resume_registry_is_kept(self):
        path = self.dir / "resume_registry.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(multi_resume_manager, "REGISTRY_FILE", path):
            multi_resume_manager.save_registry(multi_resume_manager.load_registry())
        self._assert_kept(path)

    def test_unreadable_followup_send_log_stops_sending(self):
        path = self.dir / "followup_emails_log.json"
        path.write_text(CORRUPT, encoding="utf-8")
        with mock.patch.object(send_followup_emails, "FOLLOWUP_LOG_FILE", path):
            with self.assertRaises(RuntimeError):
                send_followup_emails.load_followup_log()
        self.assertEqual(path.read_text(encoding="utf-8"), CORRUPT)

    def test_followup_send_log_without_runs_keeps_sent_entries(self):
        path = self.dir / "followup_emails_log.json"
        path.write_text(json.dumps({"sent": [{"company": "Acme"}]}), encoding="utf-8")
        with mock.patch.object(send_followup_emails, "FOLLOWUP_LOG_FILE", path):
            log = send_followup_emails.load_followup_log()
        self.assertEqual(log["sent"], [{"company": "Acme"}])
        self.assertEqual(log["runs"], [])


if __name__ == "__main__":
    unittest.main()
