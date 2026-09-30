"""Portable scheduler lock: a second holder must see LockBusy, not block."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from file_lock import LockBusy, exclusive_lock  # noqa: E402

HOLD = """
import sys, time
sys.path.insert(0, {scripts!r})
from file_lock import exclusive_lock
with exclusive_lock({path!r}):
    print("held", flush=True)
    time.sleep(5)
"""


class FileLockTest(unittest.TestCase):
    def test_second_process_sees_busy_lock(self):
        # Windows may hold the killed holder's handle briefly; cleanup is incidental.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = str(Path(tmp) / "x.lock")
            code = HOLD.format(scripts=str(ROOT / "scripts"), path=path)
            holder = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "held")
                with self.assertRaises(LockBusy):
                    with exclusive_lock(path, blocking=False):
                        pass
            finally:
                holder.kill()
                holder.wait()
                holder.stdout.close()
            # Windows releases a dead process's byte-range lock asynchronously.
            deadline = time.monotonic() + 5
            while True:
                try:
                    with exclusive_lock(path, blocking=False):
                        break
                except LockBusy:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
