import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSourceCoverageRegistry(unittest.TestCase):
    def test_registry_matches_scheduler_configuration(self):
        result = subprocess.run(
            [sys.executable, "scripts/source_coverage.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
