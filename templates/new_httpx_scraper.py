#!/usr/bin/env python3
"""
Template: New httpx+BS4 scraper.
Copy this file to categories/<category>/<site>_scraper.py and customize.

Steps:
1. Copy this file
2. Rename class
3. Set TARGET_URLS
4. Implement parse_page()
5. Implement run()
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.outbound.engines.httpx_bs4 import HttpxBS4Scraper

logger = logging.getLogger(__name__)


class MyNewScraper(HttpxBS4Scraper):
    """TODO: Describe what this scraper does."""

    def __init__(self):
        super().__init__(
            name="my_scraper",
            rate_limit=3.0,
            max_retries=3,
            timeout=30.0,
        )
        self.target_urls: List[str] = [
            # TODO: Add URLs to scrape
            "https://example.com/page1",
            "https://example.com/page2",
        ]

    def parse_page(self, soup, url: str):
        """
        Parse a single page.
        
        Args:
            soup: BeautifulSoup object
            url: The URL that was scraped
        
        TODO: Extract data from the page and call self.add_result()
        """
        # Example:
        # items = soup.select("div.item")
        # for item in items:
        #     self.add_result({
        #         "name": item.select_one("h2").get_text(strip=True),
        #         "url": item.select_one("a")["href"],
        #         "source": "example.com",
        #     })
        pass

    async def run(self):
        """Run the scraper for all target URLs."""
        for url in self.target_urls:
            logger.info(f"Scraping: {url}")
            soup = await self.fetch_and_parse(url)
            if soup:
                self.parse_page(soup, url)

        self.print_stats()
        self.export_csv("my_results.csv")
        self.export_json("my_results.json")
        return self.results


async def main():
    scraper = MyNewScraper()
    results = await scraper.run()
    print(f"\nTotal results: {len(results)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
