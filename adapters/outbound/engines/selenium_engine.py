"""
Selenium engine — for complex interactions, legacy sites, CAPTCHA-heavy pages.
Use when: need login flows, complex click chains, or sites that block Playwright.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)


class SeleniumScraper(BaseScraper):
    """Scraper using Selenium for full browser automation."""

    def __init__(self, name: str, headless: bool = True, **kwargs):
        super().__init__(name, **kwargs)
        self.headless = headless
        self.driver = None

    async def _start_browser(self):
        """Launch Selenium browser."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.timeout)
        logger.info(f"[{self.name}] Selenium browser started")

    async def _stop_browser(self):
        if self.driver:
            self.driver.quit()
            logger.info(f"[{self.name}] Selenium browser stopped")

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Navigate to URL and return page source."""
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        for attempt in range(self.max_retries):
            try:
                self.driver.get(url)
                await asyncio.sleep(2)  # wait for JS
                content = self.driver.page_source
                self._set_cache(url, content)
                self.stats["misses"] += 1
                return content
            except Exception as e:
                logger.error(f"[ERROR] {url}: {e} (attempt {attempt+1})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        return None

    def find_elements(self, by: str, value: str):
        """Find elements on page."""
        from selenium.webdriver.common.by import By
        return self.driver.find_elements(By.__dict__.get(by.upper(), by), value)

    def click(self, by: str, value: str):
        """Click an element."""
        elements = self.find_elements(by, value)
        if elements:
            elements[0].click()

    def type_text(self, by: str, value: str, text: str):
        """Type text into an input field."""
        elements = self.find_elements(by, value)
        if elements:
            elements[0].clear()
            elements[0].send_keys(text)

    def scroll_to_bottom(self):
        """Scroll to bottom of page."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            import time; time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    async def run(self):
        raise NotImplementedError("Subclasses must implement run()")
