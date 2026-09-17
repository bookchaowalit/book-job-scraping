import csv
import tempfile
import unittest
from pathlib import Path

from property.demand import canonical_topic_url, extract_topic_links, parse_topic, search_url
from scripts.scrape_property_demand import _summary, sort_records_newest_first, write_demand_csv


FIXTURE_DIR = Path(__file__).parent / "fixtures"

DEMAND_HTML = """
<html><head>
  <meta property="article:published_time" content="2026-09-10T04:00:00Z">
  <meta property="og:title" content="หาคอนโดเช่าแถวรังสิต | Pantip">
</head><body>
  <h1>หาคอนโดเช่าแถวรังสิต</h1>
  <div class="display-post-story">กำลังหาคอนโดเช่า แถวรังสิต งบไม่เกิน 7,000 บาทต่อเดือน
    ต้องการย้ายเข้าเดือนหน้า ใครมีแนะนำคอมเมนต์ได้</div>
  <div class="display-post-story">ปล่อยเช่าคอนโด ติดต่อได้ที่โพสต์นี้</div>
</body></html>
"""


LISTING_HTML = """
<html><head><title>คอนโดให้เช่า เจ้าของขายเอง | Pantip</title></head><body>
  <h1>คอนโดให้เช่า เจ้าของขายเอง</h1>
  <div class="display-post-story">ปล่อยเช่าคอนโด กรุงเทพ ห้องพร้อมอยู่ สนใจติดต่อหลังไมค์</div>
</body></html>
"""


class PropertyDemandTests(unittest.TestCase):
    def test_records_are_sorted_newest_first_and_undated_last(self):
        records = [
            {"source_url": "https://pantip.com/topic/1", "posted_at": ""},
            {"source_url": "https://pantip.com/topic/2", "posted_at": "2026-09-10T04:00:00Z"},
            {"source_url": "https://pantip.com/topic/3", "posted_at": "2026-09-16T04:00:00Z"},
            {"source_url": "https://pantip.com/topic/4", "posted_at": "not-a-timestamp"},
        ]

        ordered = sort_records_newest_first(records)

        self.assertEqual(
            [record["source_url"] for record in ordered],
            [
                "https://pantip.com/topic/3",
                "https://pantip.com/topic/2",
                "https://pantip.com/topic/4",
                "https://pantip.com/topic/1",
            ],
        )

    def test_canonical_topic_url_rejects_non_pantip_hosts(self):
        self.assertEqual(
            canonical_topic_url("https://www.pantip.com/topic/44155476?x=1"),
            "https://pantip.com/topic/44155476",
        )
        with self.assertRaises(ValueError):
            canonical_topic_url("https://example.com/topic/44155476")

    def test_search_url_is_direct_http_search(self):
        self.assertEqual(
            search_url("หาคอนโดเช่า"),
            "https://pantip.com/search?q=%E0%B8%AB%E0%B8%B2%E0%B8%84%E0%B8%AD%E0%B8%99%E0%B9%82%E0%B8%94%E0%B9%80%E0%B8%8A%E0%B9%88%E0%B8%B2",
        )

    def test_extract_topic_links_keeps_only_pantip_topics(self):
        html = (
            '<a href="/topic/44155476">one</a>'
            '<a href="https://example.com/topic/2">bad</a>'
            '<a href="/topic/44155476?reply=1">dup</a>'
        )
        self.assertEqual(extract_topic_links(html), ["https://pantip.com/topic/44155476"])

    def test_parse_first_person_demand_keeps_exact_first_post_only(self):
        demand_html = (FIXTURE_DIR / "pantip_demand_topic.html").read_text(encoding="utf-8")
        record = parse_topic(
            demand_html,
            "https://pantip.com/topic/44155476?ref=search",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        self.assertEqual(record["schema_version"], "property-demand.v1")
        self.assertEqual(record["review_status"], "permission_needed")
        self.assertEqual(record["contact_permission"], "public_reply_invited")
        self.assertEqual(record["property_type"], "condo")
        self.assertIn("รังสิต", record["location"])
        self.assertIn("7,000", record["budget"])
        self.assertIn("เดือนหน้า", record["timing"])
        self.assertNotIn("ปล่อยเช่าคอนโด", record["exact_demand_text"])

    def test_first_person_purchase_demand_is_reviewable(self):
        html = """
        <html><head><meta property="article:published_time" content="2026-09-10T04:00:00Z"></head>
        <body><h1>อยากซื้อคอนโดใกล้รถไฟฟ้า</h1>
        <div class="display-post-story">ต้องการซื้อคอนโด ใกล้ BTS งบไม่เกิน 3 ล้านบาท
        พร้อมเข้าอยู่ปลายเดือนนี้</div></body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124616",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        self.assertEqual(record["demand_signal"], "want_to_buy")
        self.assertEqual(record["review_status"], "permission_needed")
        self.assertEqual(record["contact_permission"], "not_stated")
        self.assertEqual(record["property_type"], "condo")

    def test_pantip_lead_published_at_meta_is_used_for_freshness(self):
        html = """
        <html><head><meta name="lead:published_at" content="2026-09-10T04:00:00+07:00"></head>
        <body><h1>หาคอนโดเช่า</h1>
        <div class="display-post-story">กำลังหาคอนโดเช่า งบ 8,000 บาทต่อเดือน</div></body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124618",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        self.assertEqual(record["posted_at"], "2026-09-09T21:00:00Z")
        self.assertEqual(record["review_status"], "permission_needed")

    def test_redacted_summary_exposes_evidence_gate_fields(self):
        record = parse_topic(
            DEMAND_HTML,
            "https://pantip.com/topic/44124619",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        summary = _summary(
            {
                "search_pages": 0,
                "topic_pages": 1,
                "topic_candidates": 1,
                "errors": {},
                "records": [record],
            }
        )
        lead = summary["leads"][0]
        self.assertEqual(lead["posted_at"], "2026-09-10T04:00:00Z")
        self.assertIn("เดือนหน้า", lead["timing"])
        self.assertEqual(lead["next_action"], "human_review_and_request_permission")

    def test_stale_demand_needs_more_evidence(self):
        html = """
        <html><head><meta property="article:published_time" content="2025-01-01T04:00:00Z"></head>
        <body><h1>หาบ้านเช่า</h1>
        <div class="display-post-story">กำลังหาบ้านเช่า งบ 10,000 บาทต่อเดือน</div>
        </body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124617",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        self.assertEqual(record["review_status"], "needs_more_evidence")

    def test_listing_is_not_demand(self):
        record = parse_topic(LISTING_HTML, "https://pantip.com/topic/44124613")
        self.assertEqual(record["review_status"], "not_demand")
        self.assertEqual(record["exact_demand_text"], "")

    def test_mixed_supply_and_demand_language_is_not_demand(self):
        html = """
        <html><head><meta property="article:published_time" content="2026-09-10T04:00:00Z"></head>
        <body><h1>หาคอนโดเช่า</h1>
        <div class="display-post-story">หาคอนโดเช่า แต่มีห้องให้เช่าด้วย ติดต่อเพื่อดูห้อง</div>
        </body></html>
        """
        record = parse_topic(html, "https://pantip.com/topic/44124614")
        self.assertEqual(record["review_status"], "not_demand")

    def test_missing_posted_time_needs_more_evidence(self):
        html = """
        <html><body><h1>หาคอนโดเช่า</h1>
        <div class="display-post-story">กำลังหาคอนโดเช่า งบ 8,000 บาทต่อเดือน</div>
        </body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124615",
            observed_at="2026-09-12T00:00:00Z",
        )
        self.assertEqual(record["review_status"], "needs_more_evidence")

    def test_csv_handoff_is_spreadsheet_compatible_and_excludes_not_demand(self):
        demand_record = parse_topic(
            DEMAND_HTML,
            "https://pantip.com/topic/44155476",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        not_demand_record = parse_topic(
            LISTING_HTML,
            "https://pantip.com/topic/44124613",
            observed_at="2026-09-12T00:00:00Z",
            max_age_days=30,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "property_demand.csv"
            written = write_demand_csv(
                [demand_record, not_demand_record],
                output,
                retention_until="2026-12-31T00:00:00Z",
                terms_basis_ref="test-public-source-review",
            )
            with output.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(written, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["review_status"], "permission_needed")
        self.assertEqual(rows[0]["contact_permission"], "public_reply_invited")
        self.assertEqual(rows[0]["retention_until"], "2026-12-31T00:00:00Z")
        self.assertEqual(rows[0]["terms_basis_ref"], "test-public-source-review")

    def test_budget_ignores_unrelated_numeric_limit_and_bounds_location(self):
        html = """
        <html><body><h1>ขอคำแนะนำอยากเช่าคอนโด 4 แห่ง ย่านพระราม2</h1>
        <div class="display-post-story">กำลังหาเช่าคอนโด ย่านพระราม2 พอดีกำลังหาเช่าคอนโด
        ถ้าซักผ้าครั้งละไม่เกิน 10-15 ควรใช้เครื่องซักผ้าหรือร้านซักอบรีด</div></body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124618",
            observed_at="2026-09-12T00:00:00Z",
        )
        self.assertEqual(record["budget"], "")
        self.assertEqual(record["location"], "พระราม2")

    def test_location_keeps_numeric_ranges(self):
        html = """
        <html><body><h1>หาคอนโดเช่า โซนคลอง 1-2 ธัญบุรี</h1>
        <div class="display-post-story">หาคอนโดเช่า โซนคลอง 1-2 ธัญบุรี งบไม่เกิน 7,000 บาท</div></body></html>
        """
        record = parse_topic(
            html,
            "https://pantip.com/topic/44124619",
            observed_at="2026-09-12T00:00:00Z",
        )
        self.assertEqual(record["location"], "คลอง 1-2 ธัญบุรี")


if __name__ == "__main__":
    unittest.main()
