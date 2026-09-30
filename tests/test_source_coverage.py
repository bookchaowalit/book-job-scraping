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



class TestBoardTermsDecisions(unittest.TestCase):
    def test_scheduling_a_blocked_board_fails_validation(self):
        import tempfile
        import yaml
        from unittest.mock import patch

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import source_coverage

        jobs = yaml.safe_load((REPO_ROOT / "config" / "jobs.yaml").read_text(encoding="utf-8"))
        for job in jobs["jobs"]:
            if job["name"] == "job_postings":
                job["params"]["boards"].append("landing-jobs")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.yaml"
            path.write_text(yaml.safe_dump(jobs), encoding="utf-8")
            with patch.object(source_coverage, "JOBS_CONFIG", path):
                _, errors, _ = source_coverage.validate()
        self.assertTrue(any("landing-jobs" in e and "blocked" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
