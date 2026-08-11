#!/usr/bin/env python3
"""P0 safety tests: paths, status mapping, dry-run, and send gates.

Run from book-job-scraping repo root:
  .venv/bin/python -m pytest tests/ -q
  # or without pytest:
  .venv/bin/python tests/test_paths_and_safety.py
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from repo_paths import DATA_DIR, REPO_ROOT as PATHS_ROOT, SCRIPTS_DIR  # noqa: E402
from safety import (  # noqa: E402
    SEND_UNLOCK_ENV,
    SEND_UNLOCK_VALUE,
    STATUS_PREPARED,
    STATUS_SUBMITTED,
    LIVE_SEND_ENABLED_ENV,
    is_already_handled,
    is_live_send_unlocked,
    is_prepared,
    is_submitted,
    normalize_status,
    require_live_send,
)


class TestPaths(unittest.TestCase):
    def test_repo_root_is_book_job_scraping(self):
        self.assertEqual(PATHS_ROOT, REPO_ROOT)
        self.assertTrue((PATHS_ROOT / "scripts").is_dir())
        self.assertTrue((PATHS_ROOT / "requirements.txt").is_file())

    def test_data_dir_under_repo(self):
        self.assertEqual(DATA_DIR, (REPO_ROOT / "data").resolve())
        self.assertEqual(SCRIPTS_DIR, REPO_ROOT / "scripts")

    def test_core_config_uses_repo_paths(self):
        """core/config.py must not use legacy parents[4] monorepo roots."""
        config_path = REPO_ROOT / "core" / "config.py"
        text = config_path.read_text(encoding="utf-8")
        self.assertNotIn("parents[4]", text)
        self.assertNotIn("parents[5]", text)
        self.assertNotIn("parents[6]", text)
        self.assertIn("repo_paths", text)

        # Import must resolve to this repo
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        import importlib

        if "core.config" in sys.modules:
            del sys.modules["core.config"]
        # Ensure package import works
        if "core" not in sys.modules:
            import core  # noqa: F401
        cfg = importlib.import_module("core.config")
        self.assertEqual(Path(cfg.PROJECT_ROOT).resolve(), REPO_ROOT)
        self.assertEqual(Path(cfg.DATA_DIR).resolve(), (REPO_ROOT / "data").resolve())
        self.assertEqual(Path(cfg.SCRIPTS_DIR).resolve(), (REPO_ROOT / "scripts").resolve())

    def test_no_legacy_path_segments_in_critical_scripts(self):
        critical = [
            "auto_apply.py",
            "ats_auto_apply.py",
            "pipeline_runner.py",
            "cron_scheduler.py",
            "send_application_emails.py",
            "auto_send_email.py",
            "send_followup_emails.py",
        ]
        banned = (
            '"book-scraping"',
            "domains/book-dev",
            "book-everything",
            "parents[4]",
            "parents[5]",
            "parents[6]",
        )
        for name in critical:
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(
                    token,
                    text,
                    f"{name} still contains legacy token: {token}",
                )

    def test_pipeline_runner_dry_run_paths_exist(self):
        """pipeline_runner --dry-run must point commands at real script files."""
        env = os.environ.copy()
        # Ensure no live unlock leaks into test
        env.pop(SEND_UNLOCK_ENV, None)
        env.pop(LIVE_SEND_ENABLED_ENV, None)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline_runner.py"), "--dry-run"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Commands should reference scripts under this repo
        self.assertIn(str(SCRIPTS), proc.stdout)
        self.assertNotIn("domains/book-dev", proc.stdout)
        self.assertNotIn("book-everything", proc.stdout)

        # Every .py path printed should exist
        for line in proc.stdout.splitlines():
            if "/scripts/" in line and line.strip().endswith(".py"):
                # extract path-like token
                for token in line.split():
                    if token.endswith(".py") and "scripts" in token:
                        p = Path(token)
                        if p.is_absolute():
                            self.assertTrue(p.exists(), f"missing pipeline script: {p}")


class TestStatusMapping(unittest.TestCase):
    def test_legacy_auto_applied_is_prepared(self):
        self.assertEqual(normalize_status("auto_applied"), STATUS_PREPARED)
        self.assertTrue(is_prepared("auto_applied"))
        self.assertFalse(is_submitted("auto_applied"))

    def test_applied_maps_to_submitted(self):
        self.assertEqual(normalize_status("applied"), STATUS_SUBMITTED)
        self.assertTrue(is_submitted("applied"))
        self.assertTrue(is_submitted("sent"))

    def test_already_handled_covers_prepared_and_submitted(self):
        self.assertTrue(is_already_handled("prepared"))
        self.assertTrue(is_already_handled("auto_applied"))
        self.assertTrue(is_already_handled("submitted"))
        self.assertTrue(is_already_handled("applied"))
        self.assertFalse(is_already_handled("discovered"))
        self.assertFalse(is_already_handled("new"))


class TestSendSafetyGate(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            LIVE_SEND_ENABLED_ENV: os.environ.get(LIVE_SEND_ENABLED_ENV),
            SEND_UNLOCK_ENV: os.environ.get(SEND_UNLOCK_ENV),
        }
        os.environ.pop(LIVE_SEND_ENABLED_ENV, None)
        os.environ.pop(SEND_UNLOCK_ENV, None)

    def tearDown(self):
        for key, val in self._env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_default_locked(self):
        self.assertFalse(is_live_send_unlocked())
        with self.assertRaises(SystemExit) as ctx:
            require_live_send("test")
        self.assertEqual(ctx.exception.code, 2)

    def test_partial_unlock_still_blocked(self):
        os.environ[SEND_UNLOCK_ENV] = SEND_UNLOCK_VALUE
        self.assertFalse(is_live_send_unlocked())
        os.environ.pop(SEND_UNLOCK_ENV, None)
        os.environ[LIVE_SEND_ENABLED_ENV] = "1"
        self.assertFalse(is_live_send_unlocked())

    def test_full_unlock(self):
        os.environ[LIVE_SEND_ENABLED_ENV] = "1"
        os.environ[SEND_UNLOCK_ENV] = SEND_UNLOCK_VALUE
        self.assertTrue(is_live_send_unlocked())

    def test_send_application_emails_blocks_send_flag(self):
        env = os.environ.copy()
        env.pop(SEND_UNLOCK_ENV, None)
        env.pop(LIVE_SEND_ENABLED_ENV, None)
        # Create minimal fake resume so script gets past resume check if needed;
        # gate should fire first and exit 2.
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            resumes = data / "resumes"
            resumes.mkdir()
            resume = resumes / "Resume_Chaowalit_Greepoke.pdf"
            resume.write_bytes(b"%PDF-1.4 fake")
            env["PIPELINE_DATA_DIR"] = str(data)
            (data / "apply_tracker.csv").write_text(
                "url,status,company,title\n", encoding="utf-8"
            )
            (data / "contact_emails.json").write_text("{}", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "send_application_emails.py"),
                    "--send",
                    "--resume",
                    str(resume),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            combined = proc.stdout + proc.stderr
            self.assertIn("BLOCKED", combined)
            self.assertNotRegex(combined, r"✓ Sent:\s*[1-9]")

    def test_send_followup_emails_blocks_send_even_without_candidates(self):
        """--send must hit the safety gate before early 'no candidates' return."""
        env = os.environ.copy()
        env.pop(SEND_UNLOCK_ENV, None)
        env.pop(LIVE_SEND_ENABLED_ENV, None)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            env["PIPELINE_DATA_DIR"] = str(data)
            (data / "application_send_log.json").write_text("[]", encoding="utf-8")
            (data / "followup_log.json").write_text("[]", encoding="utf-8")
            (data / "apply_tracker.csv").write_text(
                "url,status,company,title\n", encoding="utf-8"
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "send_followup_emails.py"),
                    "--send",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            combined = proc.stdout + proc.stderr
            self.assertIn("BLOCKED", combined)
            self.assertNotIn("No candidates need follow-up", combined)


class TestAtsTestFlagNoSubmit(unittest.TestCase):
    def test_test_flag_does_not_enter_submit_branch_source(self):
        """Static guard: --test alone must not call apply_* without --apply gate."""
        source = (SCRIPTS / "ats_auto_apply.py").read_text(encoding="utf-8")
        # The dangerous old condition must be gone
        self.assertNotIn("if not args.apply and not args.test:", source)
        # live_submit must require apply and not test
        self.assertIn("live_submit = bool(args.apply) and not args.test", source)

    def test_ats_test_cli_exits_without_unlock(self):
        env = os.environ.copy()
        env.pop(SEND_UNLOCK_ENV, None)
        env.pop(LIVE_SEND_ENABLED_ENV, None)
        with tempfile.TemporaryDirectory() as tmp:
            env["PIPELINE_DATA_DIR"] = tmp
            Path(tmp, "apply_tracker.csv").write_text(
                "url,status,company,title\n", encoding="utf-8"
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "ats_auto_apply.py"), "--test"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            combined = proc.stdout + proc.stderr
            self.assertIn("preview", combined.lower())
            self.assertNotIn("Submitting", combined)
            self.assertNotIn("Starting Chrome CDP", combined)


class TestNoRuntimePipInstall(unittest.TestCase):
    def test_critical_scripts_have_no_pip_install_calls(self):
        critical = list(SCRIPTS.glob("*.py"))
        offenders = []
        for path in critical:
            if path.name.startswith("_migrate"):
                continue
            text = path.read_text(encoding="utf-8")
            if "subprocess.check_call" in text and "pip" in text and "install" in text:
                # crude but catches the old pattern
                if 'pip", "install"' in text or "pip install" in text and "check_call" in text:
                    # allow mention in raise SystemExit strings
                    tree = ast.parse(text)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            call_src = ast.get_source_segment(text, node) or ""
                            if "check_call" in call_src and "pip" in call_src and "install" in call_src:
                                offenders.append(path.name)
                                break
        self.assertEqual(offenders, [], f"runtime pip install still present: {offenders}")


class TestAutoApplyStatusPrepared(unittest.TestCase):
    def test_auto_apply_writes_prepared_not_auto_applied(self):
        source = (SCRIPTS / "auto_apply.py").read_text(encoding="utf-8")
        self.assertIn("STATUS_PREPARED", source)
        # should not write legacy auto_applied status string as new writes
        self.assertNotIn('log_apply_status(job["url"], "auto_applied"', source)
        self.assertIn("STATUS_PREPARED", source.split("def main")[-1])
        self.assertNotIn(
            'log_apply_status(\n            job["url"],\n            "auto_applied"',
            source,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
