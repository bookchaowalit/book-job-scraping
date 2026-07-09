"""
Playwright engine — for JS-rendered pages, SPAs, and pages needing interaction.
Use when: content loads via JavaScript, need screenshots, need to click/scroll/type.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)


class PlaywrightScraper(BaseScraper):
    """Scraper using Playwright for browser automation."""

    def __init__(
        self,
        name: str,
        headless: bool = True,
        browser_type: str = "chromium",  # chromium, firefox, webkit
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self.headless = headless
        self.browser_type = browser_type
        self.browser = None
        self.context = None
        self.page = None

    async def _start_browser(self):
        """Launch browser instance."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        launcher = getattr(self._playwright, self.browser_type)
        self.browser = await launcher.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        self.page = await self.context.new_page()
        logger.info(f"[{self.name}] Browser started ({self.browser_type})")

    async def _stop_browser(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"[{self.name}] Browser stopped")

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Navigate to URL and return rendered HTML."""
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        for attempt in range(self.max_retries):
            try:
                response = await self.page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
                if response and response.status >= 400:
                    logger.warning(f"[HTTP {response.status}] {url}")
                    continue
                content = await self.page.content()
                self._set_cache(url, content)
                self.stats["misses"] += 1
                return content
            except Exception as e:
                logger.error(f"[ERROR] {url}: {e} (attempt {attempt+1})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        return None

    async def screenshot(self, url: str, path: str) -> bool:
        """Take screenshot of a page."""
        try:
            await self.page.goto(url, wait_until="networkidle")
            await self.page.screenshot(path=path, full_page=True)
            logger.info(f"[SCREENSHOT] {url} → {path}")
            return True
        except Exception as e:
            logger.error(f"[SCREENSHOT FAILED] {url}: {e}")
            return False

    async def click(self, selector: str):
        """Click an element."""
        await self.page.click(selector)
        await self.page.wait_for_load_state("networkidle")

    async def scroll_to_bottom(self, pause: float = 1.0):
        """Scroll to bottom of page (for infinite scroll)."""
        prev_height = 0
        while True:
            curr_height = await self.page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                break
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(pause)
            prev_height = curr_height

    async def extract_table(self, selector: str) -> List[Dict[str, str]]:
        """Extract HTML table as list of dicts."""
        return await self.page.evaluate(f"""
            () => {{
                const table = document.querySelector('{selector}');
                if (!table) return [];
                const headers = [...table.querySelectorAll('th')].map(h => h.textContent.trim());
                return [...table.querySelectorAll('tr')].map(row => {{
                    const cells = [...row.querySelectorAll('td')].map(c => c.textContent.trim());
                    if (!cells.length) return null;
                    return headers.reduce((obj, h, i) => {{ obj[h] = cells[i] || ''; return obj; }}, {{}});
                }}).filter(Boolean);
            }}
        """)

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
