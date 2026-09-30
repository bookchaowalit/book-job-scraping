"""Regression tests for recurring cross-repo bug patterns."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from property.ddproperty_scraper import _price_value, parse_next_data
from scripts import scrape_property_listings as listings_mod
from scripts.find_contact_emails import extract_domain_from_url
from scripts.parse_fb_search_results import extract_emails
from scripts.scrape_hackernews import epoch_to_utc_iso

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts import prepare_applications, scrape_discovered_jobs  # noqa: E402


def _next_data_html(price) -> str:
    payload = {
        "props": {"pageProps": {"pageData": {"data": {"listingsData": [
            {
                "listingData": {
                    "localizedTitle": "คอนโดอโศก",
                    "price": price,
                    "shortAddress": "กรุงเทพ อโศก",
                    "typeCode": "RENT",
                    "url": "https://www.ddproperty.com/property/example",
                },
                "segment": {"parameters": {"metaData": {"listingData": {}}}},
            }
        ]}}}}
    }
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'


class PriceDropHistoryOrderTests(unittest.TestCase):
    """Drops must be detected against history *before* the run is appended."""

    def test_persist_reports_drop_against_prior_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            listing = {"title": "Condo A", "type": "condo_rent", "price": 20000.0}
            with mock.patch("builtins.print"):
                self.assertEqual(listings_mod.persist([dict(listing)], out, 10.0), [])
                drops = listings_mod.persist([{**listing, "price": 15000.0}], out, 10.0)
            self.assertEqual(len(drops), 1)
            self.assertEqual(drops[0]["old_price"], 20000.0)
            self.assertEqual(drops[0]["price_drop_pct"], 25.0)
            history = (out / "property_history.csv").read_text(encoding="utf-8")
            self.assertIn("15000.0", history)


class NonFinitePriceTests(unittest.TestCase):
    def test_price_value_rejects_nan_and_inf(self):
        for raw in ("nan", "NaN", "inf", "-inf", float("nan"), float("inf")):
            self.assertIsNone(_price_value(raw), raw)
        self.assertEqual(_price_value("25000"), 25000.0)

    def test_nan_price_does_not_pass_max_price_filter(self):
        self.assertEqual(parse_next_data(_next_data_html("NaN"), max_price=30000), [])
        self.assertEqual(parse_next_data(_next_data_html(float("nan")), max_price=30000), [])
        self.assertEqual(len(parse_next_data(_next_data_html(20000), max_price=30000)), 1)


class HostMatchTests(unittest.TestCase):
    def test_lookalike_host_is_not_treated_as_ats(self):
        # 'lever.co' is a substring of 'jobs.clever.com'
        self.assertEqual(extract_domain_from_url("https://jobs.lever.co/acme/123"), "acme.com")
        self.assertNotEqual(extract_domain_from_url("https://jobs.clever.com/careers/1"), "careers.com")

    def test_lookalike_host_is_not_treated_as_job_board(self):
        # 'dice.com' is a substring of 'paradice.com'
        self.assertIsNotNone(extract_domain_from_url("https://www.paradice.com/jobs/1"))
        self.assertIsNone(extract_domain_from_url("https://www.dice.com/job/1"))


class DeterministicEmailOrderTests(unittest.TestCase):
    def test_emails_keep_first_seen_order(self):
        text = " ".join(f"person{i}@company{i}.co" for i in range(20))
        self.assertEqual(extract_emails(text), [f"person{i}@company{i}.co" for i in range(20)])


class AtsHostMatchTests(unittest.TestCase):
    def test_url_slug_extraction_ignores_lookalike_hosts(self):
        real = scrape_discovered_jobs.extract_from_url_slug("https://jobs.lever.co/acme/1")
        self.assertEqual(real["company"], "Acme")
        fake = scrape_discovered_jobs.extract_from_url_slug("https://jobs.clever.com/acme/1")
        self.assertNotEqual(fake.get("company"), "Acme")

    def test_ats_bonus_requires_a_real_ats_host(self):
        job = {"title": "engineer", "company": "x", "url": "https://jobs.lever.co/x/1"}
        fake = dict(job, url="https://careers.clever.com/x/1")
        self.assertEqual(
            prepare_applications.score_job(job, {}) - prepare_applications.score_job(fake, {}), 3
        )


@unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset")
class UtcEpochTests(unittest.TestCase):
    def test_epoch_rendered_as_utc_regardless_of_host_tz(self):
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Bangkok"
        time.tzset()
        try:
            self.assertEqual(epoch_to_utc_iso(0), "1970-01-01T00:00:00+00:00")
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()


if __name__ == "__main__":
    unittest.main()
