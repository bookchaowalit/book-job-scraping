#!/usr/bin/env python3
"""
Scrape ProductHunt top products via Atom feed (free, no auth).
Tracks daily top products for developer intelligence and opportunity detection.

Outputs:
    - book-scraping/data/exported/producthunt_top.csv (latest top products)
    - book-scraping/data/exported/producthunt_history.csv (appended daily)

Usage:
    python3 scripts/scrape_producthunt.py
    python3 scripts/scrape_producthunt.py --limit 20
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
    from bs4 import XMLParsedAsHTMLWarning
    import warnings
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    print("ERROR: beautifulsoup4 required. Install: pip install beautifulsoup4")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[4]  # solo-empire/
OUTPUT_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data" / "exported"

PH_FEED = "https://www.producthunt.com/feed"


def fetch_feed_products(limit: int = 20) -> list:
    """Fetch products from ProductHunt Atom feed."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/atom+xml,application/xml,text/xml",
    }

    try:
        resp = httpx.get(PH_FEED, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Warning: ProductHunt feed fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    entries = soup.find_all("entry")

    products = []
    for entry in entries[:limit]:
        title = entry.find("title")
        link = entry.find("link")
        summary = entry.find("summary") or entry.find("content")
        published = entry.find("published") or entry.find("updated")

        title_text = title.get_text(strip=True) if title else ""
        href = link.get("href", "") if link else ""

        # Clean description from HTML
        desc = ""
        if summary:
            desc_text = summary.get_text(strip=True)
            desc = re.sub(r"<[^>]+>", "", desc_text)[:200]

        if title_text:
            products.append({
                "title": title_text,
                "url": href,
                "description": desc,
                "published_at": published.get_text(strip=True) if published else "",
            })

    return products


def save_products(products: list, output_dir: Path):
    """Save products to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "producthunt_top.csv"
    fieldnames = ["title", "url", "description", "published_at"]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)
    print(f"  Saved {len(products)} products to {filepath}")


def append_history(products: list, output_dir: Path):
    """Append to history CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "producthunt_history.csv"
    fieldnames = ["title", "url", "description", "published_at", "scraped_at"]
    now = datetime.now().isoformat()

    file_exists = filepath.exists()
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for p in products:
            row = {**p, "scraped_at": now}
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Scrape ProductHunt products via Atom feed")
    parser.add_argument("--limit", type=int, default=20, help="Max products (default: 20)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ProductHunt Scraper")

    print("  Fetching feed...")
    products = fetch_feed_products(args.limit)
    print(f"  Got {len(products)} products")

    save_products(products, output_dir)
    append_history(products, output_dir)
    print("  Done.")


class ProductHuntScraper:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, limit=20, **kwargs):
        self.limit = limit

    async def run(self, **kwargs):
        print(f"[ProductHuntScraper] Fetching products from feed...")
        products = fetch_feed_products(self.limit)
        save_products(products, OUTPUT_DIR)
        append_history(products, OUTPUT_DIR)
        print(f"  Total: {len(products)} products")
        return [{"source": "producthunt", "count": len(products)}]


if __name__ == "__main__":
    main()
