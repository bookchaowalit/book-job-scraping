#!/usr/bin/env python3
"""One scheduled tick: run due jobs, then the pipeline health monitor.

Cross-platform replacement for the cron line
``flock -n data/scraper-scheduler.lock sh -c 'main.py run; pipeline_health_monitor.py'``.
A tick that finds the lock held exits 0 without running, so overlapping
schedulers (cron, Windows Task Scheduler) never run two collections at once.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from file_lock import LockBusy, exclusive_lock  # noqa: E402
from repo_paths import DATA_DIR, REPO_ROOT  # noqa: E402

LOCK_FILE = DATA_DIR / "scraper-scheduler.lock"
LOG_FILE = DATA_DIR / "logs" / "cron.log"

STEPS = [
    [sys.executable, str(REPO_ROOT / "main.py"), "run"],
    [sys.executable, str(REPO_ROOT / "scripts" / "pipeline_health_monitor.py")],
]


def main() -> int:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with exclusive_lock(LOCK_FILE, blocking=False):
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(f"\n=== tick {datetime.now().isoformat(timespec='seconds')} ===\n")
                log.flush()
                code = 0
                for argv in STEPS:
                    result = subprocess.run(
                        argv, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
                    )
                    code = code or result.returncode
                return code
    except LockBusy:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
