"""
httpx + BeautifulSoup engine — for static HTML pages.
Fastest engine. Use when content is in the HTML source (no JS rendering needed).
"""

import asyncio
import logging
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class HttpxBS4Scraper(BaseScraper):
    """Scraper using httpx for HTTP + BeautifulSoup for HTML parsing."""

    def __init__(self, name: str, **kwargs):
        super().__init__(name, **kwargs)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch URL with httpx, return HTML string."""
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=True
                ) as client:
                    response = await client.get(url, headers=self.headers)
                    response.raise_for_status()
                    content = response.text
                    self._set_cache(url, content)
                    self.stats["misses"] += 1
                    logger.info(f"[OK] {url}")
                    return content
            except httpx.HTTPStatusError as e:
                logger.warning(f"[HTTP {e.response.status_code}] {url} (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"[ERROR] {url}: {e} (attempt {attempt+1})")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        logger.error(f"[FAILED] {url} after {self.max_retries} attempts")
        return None

    def parse(self, html: str) -> BeautifulSoup:
        """Parse HTML string into BeautifulSoup object."""
        return BeautifulSoup(html, "html.parser")

    async def fetch_and_parse(self, url: str) -> Optional[BeautifulSoup]:
        """Convenience: fetch + parse in one call."""
        html = await self.fetch(url)
        if html:
            return self.parse(html)
        return None

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
