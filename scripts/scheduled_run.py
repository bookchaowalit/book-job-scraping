#!/usr/bin/env python3
"""One scheduled tick: run due jobs, then the pipeline health monitor.

Cross-platform replacement for the cron line
``flock -n data/scraper-scheduler.lock sh -c 'main.py run; pipeline_health_monitor.py'``.
A tick that finds the lock held exits 0 without running, so overlapping
schedulers (cron, Windows Task Scheduler) never run two collections at once.

Windows assumptions handled here:

* Task Scheduler's ``ExecutionTimeLimit`` (1 h in ``ops/windows``) kills only
  this process. Windows does not kill its children, so an overrunning
  ``main.py run`` would outlive the tick, release the lock, and overlap the
  next tick. Every step therefore has its own timeout (together well under the
  task limit) and a timed-out step is killed with its whole process tree.
* There is no logrotate on Windows, so ``cron.log`` is rotated here once it
  passes ``LOG_MAX_BYTES`` (one ``cron.log.1`` generation is kept).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from file_lock import LockBusy, exclusive_lock  # noqa: E402
from repo_paths import DATA_DIR, REPO_ROOT  # noqa: E402

LOCK_FILE = DATA_DIR / "scraper-scheduler.lock"
LOG_FILE = DATA_DIR / "logs" / "cron.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_EXIT_CODE = 124  # same convention as coreutils `timeout`

# (argv, timeout seconds). 45 + 5 min stays below the 1 h task limit.
STEPS: list[tuple[list[str], float]] = [
    ([sys.executable, str(REPO_ROOT / "main.py"), "run"], 45 * 60),
    ([sys.executable, str(REPO_ROOT / "scripts" / "pipeline_health_monitor.py")], 5 * 60),
]


def rotate_log(log_file: Path, max_bytes: int = LOG_MAX_BYTES) -> bool:
    """Move ``log_file`` to ``<name>.1`` when it is larger than ``max_bytes``."""
    try:
        if log_file.stat().st_size <= max_bytes:
            return False
        os.replace(log_file, log_file.with_name(log_file.name + ".1"))
        return True
    except OSError:
        # Missing file, or another process holds it open on Windows: keep going.
        return False


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.kill()


def run_step(argv: Sequence[str], timeout: float, *, env: dict, log: IO[str], cwd: Path) -> int:
    """Run one step with a timeout; on timeout kill its process tree."""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        list(argv), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **kwargs
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        process.wait()
        log.write(f"--- step timed out after {timeout:g}s and was killed: {Path(argv[-1]).name}\n")
        log.flush()
        return TIMEOUT_EXIT_CODE


def main(
    steps: Sequence[tuple[Sequence[str], float]] | None = None,
    *,
    lock_file: Path = LOCK_FILE,
    log_file: Path = LOG_FILE,
    cwd: Path = REPO_ROOT,
) -> int:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with exclusive_lock(lock_file, blocking=False):
            rotate_log(log_file)
            with log_file.open("a", encoding="utf-8") as log:
                log.write(f"\n=== tick {datetime.now().isoformat(timespec='seconds')} ===\n")
                log.flush()
                code = 0
                for argv, timeout in STEPS if steps is None else steps:
                    result = run_step(argv, timeout, env=env, log=log, cwd=cwd)
                    code = code or result
                return code
    except LockBusy:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
