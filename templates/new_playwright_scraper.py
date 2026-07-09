#!/usr/bin/env python3
"""
Template: New Playwright scraper.
Copy this file to categories/<category>/<site>_scraper.py and customize.

Use this when the site requires JavaScript to render content.

Steps:
1. Copy this file
2. Rename class
3. Set target URLs
4. Implement parse_page()
5. Implement run()
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.outbound.engines.playwright_engine import PlaywrightScraper

logger = logging.getLogger(__name__)


class MyPlaywrightScraper(PlaywrightScraper):
    """TODO: Describe what this scraper does."""

    def __init__(self):
        super().__init__(
            name="my_playwright_scraper",
            headless=True,
            rate_limit=4.0,
            timeout=60.0,
        )

    async def parse_page(self):
        """
        Parse current page using JS evaluation.
        
        TODO: Use self.page.evaluate() to extract data from the rendered page.
        """
        items = await self.page.evaluate("""
            () => {
                // TODO: Select elements from the page
                const cards = document.querySelectorAll('.item-card');
                return [...cards].map(card => ({
                    name: card.querySelector('.name')?.textContent?.trim() || '',
                    url: card.querySelector('a')?.href || '',
                    price: card.querySelector('.price')?.textContent?.trim() || '',
                })).filter(item => item.name);
            }
        """)
        return items

    async def run(self):
        """Run the scraper."""
        target_urls = [
            # TODO: Add URLs
            "https://example.com/search?q=test",
        ]

        await self._start_browser()
        try:
            for url in target_urls:
                logger.info(f"Scraping: {url}")
                await self.fetch(url)
                items = await self.parse_page()
                for item in items:
                    self.add_result({**item, "source": self.name})
                logger.info(f"  Found {len(items)} items")
        finally:
            await self._stop_browser()

        self.print_stats()
        self.export_csv("my_results.csv")
        self.export_json("my_results.json")
        return self.results


async def main():
    scraper = MyPlaywrightScraper()
    results = await scraper.run()
    print(f"\nTotal results: {len(results)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
