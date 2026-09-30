"""Scheduled tick: lock skip, exit codes, per-step timeout, log rotation."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scheduled_run  # noqa: E402
from file_lock import exclusive_lock  # noqa: E402

PY = sys.executable


def _step(code: str, timeout: float = 30):
    return ([PY, "-c", code], timeout)


class ScheduledRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.lock = self.tmp / "tick.lock"
        self.log = self.tmp / "logs" / "cron.log"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, steps):
        return scheduled_run.main(steps, lock_file=self.lock, log_file=self.log, cwd=self.tmp)

    def test_steps_run_in_order_and_first_failure_code_wins(self):
        code = self._run([
            _step("print('one')"),
            _step("import sys; print('two'); sys.exit(3)"),
            _step("import sys; print('three'); sys.exit(5)"),
        ])
        self.assertEqual(code, 3)
        text = self.log.read_text(encoding="utf-8")
        self.assertIn("=== tick", text)
        self.assertLess(text.index("one"), text.index("two"))
        self.assertIn("three", text)  # later steps (health monitor) still run

    def test_children_get_utf8_environment(self):
        self.assertEqual(self._run([_step("import os, sys; sys.exit(0 if os.environ['PYTHONUTF8'] == '1' else 9)")]), 0)

    def test_busy_lock_skips_the_tick(self):
        with exclusive_lock(self.lock):
            # Another in-process holder: the non-blocking tick must not run.
            if sys.platform != "win32":
                import subprocess
                probe = subprocess.run(
                    [PY, "-c", (
                        "import sys; sys.path.insert(0, %r); import scheduled_run, pathlib;"
                        "sys.exit(scheduled_run.main([([sys.executable, '-c', 'print(1)'], 5)],"
                        " lock_file=pathlib.Path(%r), log_file=pathlib.Path(%r)))"
                    ) % (str(ROOT / "scripts"), str(self.lock), str(self.log))],
                    check=False,
                )
                self.assertEqual(probe.returncode, 0)
        self.assertFalse(self.log.exists() and "=== tick" in self.log.read_text(encoding="utf-8"))

    def test_overrunning_step_is_killed_with_its_children(self):
        marker = self.tmp / "grandchild-survived"
        grandchild = f"import time, pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).write_text('x')"
        parent = (
            "import subprocess, sys, time;"
            f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]);"
            "time.sleep(30)"
        )
        start = time.monotonic()
        code = self._run([([PY, "-c", parent], 0.5), _step("print('health ran')")])
        self.assertEqual(code, scheduled_run.TIMEOUT_EXIT_CODE)
        self.assertLess(time.monotonic() - start, 15)
        time.sleep(2.5)
        self.assertFalse(marker.exists(), "grandchild outlived the timed-out step")
        text = self.log.read_text(encoding="utf-8")
        self.assertIn("timed out", text)
        self.assertIn("health ran", text)

    def test_log_rotates_when_over_limit(self):
        self.log.parent.mkdir(parents=True)
        self.log.write_text("x" * 100, encoding="utf-8")
        self.assertFalse(scheduled_run.rotate_log(self.log, max_bytes=1000))
        self.assertTrue(scheduled_run.rotate_log(self.log, max_bytes=10))
        self.assertEqual(self.log.with_name("cron.log.1").read_text(encoding="utf-8"), "x" * 100)
        self.assertFalse(self.log.exists())
        self.assertFalse(scheduled_run.rotate_log(self.log, max_bytes=10))  # missing file is fine

    def test_default_steps_fit_inside_task_limit(self):
        self.assertLess(sum(timeout for _argv, timeout in scheduled_run.STEPS), 60 * 60)


if __name__ == "__main__":
    unittest.main()
