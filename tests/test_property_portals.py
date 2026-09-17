import csv
import tempfile
import unittest
from pathlib import Path

from property.listing_config import property_source_platform
from property.portal_scrapers import (
    PORTAL_FIELDNAMES,
    PortalPropertyScraper,
    parse_portal_html,
)


FIXTURES = Path(__file__).parent / "fixtures"


class PropertyPortalScraperTests(unittest.TestCase):
    def test_allowlist_recognises_major_listing_hosts(self):
        self.assertEqual(property_source_platform("https://www.ennxo.com/product/1"), "ennxo")
        self.assertEqual(property_source_platform("https://www.renthub.in.th/room/1"), "renthub")
        self.assertEqual(property_source_platform("https://www.baania.com/listing-rent"), "baania")

    def test_ennxo_parser_canonicalises_and_deduplicates(self):
        html = (FIXTURES / "portal_ennxo.html").read_text(encoding="utf-8")
        rows = parse_portal_html(html, "ennxo")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_platform"], "ennxo")
        self.assertEqual(rows[0]["url"], "https://ennxo.com/product/123456")
        self.assertEqual(rows[0]["price"], 1850000)

    def test_portal_parsers_keep_only_positive_priced_listing_rows(self):
        cases = (
            ("portal_propertyhub.html", "propertyhub", 18000),
            ("portal_livinginsider.html", "livinginsider", 25000),
            ("portal_zmyhome.html", "zmyhome", 9500),
        )
        for fixture, source, expected_price in cases:
            with self.subTest(source=source):
                html = (FIXTURES / fixture).read_text(encoding="utf-8")
                rows = parse_portal_html(html, source)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["price"], expected_price)
                self.assertEqual(rows[0]["source_channel"], "listing")
                self.assertEqual(rows[0]["type"], "condo_rent_thailand")
                self.assertEqual(rows[0]["contact_source_url"], rows[0]["url"])

    def test_rental_parser_chooses_rent_price_when_card_has_sale_price(self):
        html = (FIXTURES / "portal_livinginsider.html").read_text(encoding="utf-8")
        rows = parse_portal_html(html, "livinginsider")

        self.assertEqual(rows[0]["price"], 25000)

    def test_portal_snapshot_is_supply_only_and_uses_contract_fields(self):
        html = (FIXTURES / "portal_propertyhub.html").read_text(encoding="utf-8")
        rows = parse_portal_html(html, "propertyhub")
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = PortalPropertyScraper(
                source="propertyhub",
                output_dir=temp_dir,
                output_stem="propertyhub_snapshot",
            )
            output = Path(temp_dir) / "propertyhub_snapshot.csv"
            from property.portal_scrapers import _write_snapshot

            _write_snapshot(rows, Path(temp_dir), scraper.output_stem)
            with output.open(newline="", encoding="utf-8") as handle:
                saved = list(csv.DictReader(handle))

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["source_channel"], "listing")
        self.assertNotIn("demand_status", saved[0])
        self.assertEqual(set(PORTAL_FIELDNAMES), set(saved[0]))


if __name__ == "__main__":
    unittest.main()