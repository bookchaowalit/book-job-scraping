"""job_postings history is append-once per job; main() reports real counts."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scrape_job_postings as sjp  # noqa: E402

JOB_A = {"title": "Dev A", "company": "A", "location": "", "salary": "", "url": "https://a.io/1",
         "source": "Remotive", "keyword": "python", "posted": "", "tags": ""}
JOB_B = {**JOB_A, "title": "Dev B", "url": "https://b.io/1"}


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class HistoryDedupTest(unittest.TestCase):
    def test_second_run_appends_only_new_jobs_and_counts_them(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sjp, "OUTPUT_DIR", Path(tmp)):
            with patch.object(sjp, "fetch_remotive", return_value=[JOB_A]):
                first = sjp.main(boards="remotive", keywords="python")
            with patch.object(sjp, "fetch_remotive", return_value=[JOB_A, JOB_B]):
                second = sjp.main(boards="remotive", keywords="python")
            history = rows(Path(tmp) / "job_postings_history.csv")
        self.assertEqual([r["url"] for r in history], ["https://a.io/1", "https://b.io/1"])
        self.assertEqual((first["unique"], first["new"]), (1, 1))
        self.assertEqual((second["unique"], second["new"]), (2, 1))
        self.assertEqual(second["per_board"], {"remotive": 2})

    def test_urlless_jobs_dedup_on_source_company_title(self):
        job = {**JOB_A, "url": ""}
        self.assertEqual(sjp.history_key(job), sjp.history_key({**job, "keyword": "other"}))
        self.assertNotEqual(sjp.history_key(job), sjp.history_key({**job, "title": "Other"}))


if __name__ == "__main__":
    unittest.main()
