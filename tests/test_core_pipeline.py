#!/usr/bin/env python3
"""Unit tests for the domain pipeline: DataCleaner and Deduplicator.

Run from the repo root:
  .venv/bin/python -m pytest tests/test_core_pipeline.py -q
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.pipeline.cleaner import DataCleaner  # noqa: E402
from core.pipeline.deduplicator import Deduplicator  # noqa: E402


class DataCleanerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cleaner = DataCleaner()

    def test_removes_empty_items_and_counts_them(self) -> None:
        out = self.cleaner.clean([{}, {"a": "  ", "b": None}, {"title": "x"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(self.cleaner.stats["removed_empty"], 2)
        self.assertEqual(self.cleaner.report()["removal_rate"], "66.7%")

    def test_normalizes_whitespace_control_chars_and_trailing_ellipsis(self) -> None:
        out = self.cleaner.clean([{"t": "  a\x00b\n\n c...", "tags": [" x  y "]}])
        self.assertEqual(out[0]["t"], "ab c")
        self.assertEqual(out[0]["tags"], ["x y"])
        self.assertEqual(out[0]["_schema"], "generic")

    def test_job_title_keeps_hyphenated_words(self) -> None:
        out = self.cleaner.clean(
            [{"title": "Front-End Developer"}, {"title": "Data Engineer - Bangkok"},
             {"title": "Senior SRE | Acme Co."}],
            schema="job",
        )
        self.assertEqual(
            [i["title"] for i in out],
            ["Front-End Developer", "Data Engineer", "Senior SRE"],
        )

    def test_job_salary_range_and_single_value(self) -> None:
        out = self.cleaner.clean(
            [{"salary": "30,000 - 50,000 บาท"}, {"salary": "฿45000"}],
            schema="job",
        )
        self.assertEqual(out[0]["salary"], "30,000-50,000")
        self.assertEqual(out[1]["salary"], "45,000")

    def test_job_salary_without_digits_does_not_crash(self) -> None:
        out = self.cleaner.clean([{"salary": "Negotiable, DOE"}], schema="job")
        self.assertEqual(out[0]["salary"], "Negotiable, DOE")

    def test_job_salary_with_decimals(self) -> None:
        out = self.cleaner.clean([{"salary": "1.5 - 2.5 THB"}], schema="job")
        self.assertEqual(out[0]["salary"], "1.5-2.5")

    def test_product_price_and_name_suffix(self) -> None:
        out = self.cleaner.clean(
            [{"price": "฿1,299.50", "name": "Kettle | ส่งฟรี ทั่วไทย"}], schema="product"
        )
        self.assertEqual(out[0]["price"], "1299.50")
        self.assertEqual(out[0]["name"], "Kettle")

    def test_business_phone_extracted_from_description(self) -> None:
        out = self.cleaner.clean(
            [{"name": "Cafe", "description": "Call 081-234-5678 today",
              "address": "Bangkok  จังหวัด  นนทบุรี"}],
            schema="business",
        )
        self.assertEqual(out[0]["phone"], "081-234-5678")
        self.assertEqual(out[0]["address"], "Bangkok จ.นนทบุรี")

    def test_unknown_schema_passes_through(self) -> None:
        out = self.cleaner.clean([{"title": "A - B"}], schema="unknown")
        self.assertEqual(out[0]["title"], "A - B")

    def test_extract_contacts(self) -> None:
        got = self.cleaner.extract_contacts(
            "mail hr@example.co.th or +66 81 234 5678, see https://example.com/jobs"
        )
        self.assertEqual(got["emails"], ["hr@example.co.th"])
        self.assertEqual(got["urls"], ["https://example.com/jobs"])
        self.assertEqual(len(got["phones"]), 1)

    def test_normalize_thai_dates(self) -> None:
        cases = {
            "13 มิ.ย. 2569": "2026-06-13",
            "1 มกราคม 2570": "2027-01-01",
            "13มิ.ย.2569": "2026-06-13",
            "5 ธ.ค 2026": "2026-12-05",
            "13 มิ.ย. 2569 14:30": "2026-06-13T14:30:00",
            "13 มิ.ย. 2569 เวลา 14.30 น.": "2026-06-13T14:30:00",
            "1 ม.ค. 2570 09:05:07": "2027-01-01T09:05:07",
            "13 มิ.ย. 2569 25:00": "13 มิ.ย. 2569 25:00",  # invalid time: kept
            # ISO dates/datetimes keep their time and timezone untouched.
            "2026-09-30": "2026-09-30",
            "2026-09-30T08:00:00Z": "2026-09-30T08:00:00Z",
            "2026-09-30T08:00:00+07:00": "2026-09-30T08:00:00+07:00",
            "2026-09-30 08:00:00.123456": "2026-09-30 08:00:00.123456",
            "Tue, 30 Sep 2026 08:00:00 +0700": "Tue, 30 Sep 2026 08:00:00 +0700",
            "  31 ก.พ. 2569 ": "31 ก.พ. 2569",  # invalid day: kept as-is
            "yesterday": "yesterday",
            "": "",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.cleaner._normalize_date(raw), expected)

    def test_news_schema_normalizes_published(self) -> None:
        got = self.cleaner.clean(
            [{"title": "ข่าว", "url": "https://example.com/a", "published": "13 มิ.ย. 2569"}],
            schema="news",
        )
        self.assertEqual(got[0]["published"], "2026-06-13")

    def test_news_schema_keeps_iso_published_time_and_timezone(self) -> None:
        published = "2026-09-30T08:15:00+07:00"
        got = self.cleaner.clean(
            [{"title": "ข่าว", "url": "https://example.com/b", "published": published}],
            schema="news",
        )
        self.assertEqual(got[0]["published"], published)

    def test_clean_does_not_mutate_caller_items(self) -> None:
        item = {"title": "Engineer", "url": "https://example.com/j", "salary": "30,000 - 40,000"}
        before = dict(item)
        for normalize in (True, False):
            with self.subTest(normalize_text=normalize):
                self.cleaner.clean([item], schema="job", normalize_text=normalize)
                self.assertEqual(item, before)


class DeduplicatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "hash_db.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dedup_is_case_and_whitespace_insensitive(self) -> None:
        d = Deduplicator(hash_db=self.db)
        items = [{"url": "https://x/1", "t": 1}, {"url": " HTTPS://X/1 ", "t": 2},
                 {"url": "https://x/2", "t": 3}]
        out = d.deduplicate(items, key_fields=["url"])
        self.assertEqual([i["t"] for i in out], [1, 3])

    def test_keep_last_keeps_latest_duplicate_in_original_order(self) -> None:
        d = Deduplicator(hash_db=self.db)
        items = [{"url": "a", "t": 1}, {"url": "b", "t": 2}, {"url": "a", "t": 3}]
        out = d.deduplicate(items, key_fields=["url"], keep="last")
        self.assertEqual([i["t"] for i in out], [2, 3])

    def test_persisted_hashes_filter_future_runs_and_count_repeats(self) -> None:
        d = Deduplicator(hash_db=self.db)
        d.deduplicate([{"url": "a"}], key_fields=["url"])
        d.save()
        d2 = Deduplicator(hash_db=self.db)
        self.assertTrue(d2.is_duplicate({"url": "a"}, ["url"]))
        self.assertEqual(d2.deduplicate([{"url": "a"}, {"url": "b"}], ["url"]), [{"url": "b"}])
        (entry,) = [v for v in d2.seen_hashes.values() if v["key"] == {"url": "a"}]
        self.assertEqual(entry["count"], 2)

    def test_auto_key_fields_prefers_url_then_title(self) -> None:
        d = Deduplicator(hash_db=self.db)
        self.assertEqual(d._auto_key_fields({"title": "t", "url": "u", "x": 1}), ["url", "title"])
        self.assertEqual(d._auto_key_fields({"a": "s", "b": 2}), ["a"])
        self.assertEqual(d._auto_key_fields({"a": 1, "b": 2, "c": 3}), ["a", "b"])

    def test_empty_input(self) -> None:
        self.assertEqual(Deduplicator(hash_db=self.db).deduplicate([]), [])

    def test_merge_files_roundtrips_utf8(self) -> None:
        f1 = self.tmp / "a.json"
        f2 = self.tmp / "b.json"
        f1.write_text(json.dumps([{"title": "วิศวกร", "url": "1"}], ensure_ascii=False), encoding="utf-8")
        f2.write_text(json.dumps({"title": "วิศวกร", "url": "1"}, ensure_ascii=False), encoding="utf-8")
        out = self.tmp / "out" / "merged.json"
        merged = Deduplicator(hash_db=self.db).merge_files([f1, f2, self.tmp / "missing.json"], out, ["url"])
        self.assertEqual(len(merged), 1)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))[0]["title"], "วิศวกร")

    def test_clear_resets_db(self) -> None:
        d = Deduplicator(hash_db=self.db)
        d.deduplicate([{"url": "a"}], ["url"])
        d.clear()
        self.assertEqual(d.stats()["total_hashes"], 0)
        self.assertEqual(json.loads(self.db.read_text(encoding="utf-8")), {})


if __name__ == "__main__":
    unittest.main()
