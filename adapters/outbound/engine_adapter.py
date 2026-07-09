"""
Engine adapter — implements ScraperPort for all scraping engines.
Routes to the correct engine based on job.engine type.
"""
import asyncio
from typing import List, Optional, Dict
from pathlib import Path

from core.models import ScrapedItem, ScrapeJob
from core.ports import ScraperPort


class EngineAdapter:
    """
    Adapter that routes to the correct scraping engine.
    Supports: httpx, playwright, selenium, scrapy, rss, firecrawl, jina
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._engines = {}
        self._init_engines()

    def _init_engines(self):
        """Initialize available engines (lazy import)."""
        # httpx - always available
        try:
            from adapters.outbound.engines.httpx_bs4 import HttpxBS4Scraper
            self._engines["httpx"] = HttpxBS4Scraper(name="httpx")
        except ImportError:
            pass

        # playwright
        try:
            from adapters.outbound.engines.playwright_engine import PlaywrightScraper
            self._engines["playwright"] = PlaywrightScraper(name="playwright")
        except ImportError:
            pass

        # selenium
        try:
            from adapters.outbound.engines.selenium_engine import SeleniumScraper
            self._engines["selenium"] = SeleniumScraper(name="selenium")
        except ImportError:
            pass

        # rss
        try:
            from adapters.outbound.engines.rss_engine import RSSScraper
            self._engines["rss"] = RSSScraper(name="rss")
        except ImportError:
            pass

        # firecrawl (AI-powered, requires FIRECRAWL_API_KEY)
        try:
            from adapters.outbound.engines.firecrawl_engine import FirecrawlScraper
            self._engines["firecrawl"] = FirecrawlScraper(name="firecrawl")
        except (ImportError, ValueError):
            pass

        # jina reader (AI-optimized reading, requires JINA_API_KEY)
        try:
            from adapters.outbound.engines.jina_reader_engine import JinaReaderScraper
            self._engines["jina"] = JinaReaderScraper(name="jina")
        except ImportError:
            pass

    def supports_engine(self, engine_name: str) -> bool:
        """Check if engine is available."""
        return engine_name in self._engines

    async def fetch(self, url: str, engine: str = "httpx", **kwargs) -> Optional[str]:
        """Fetch raw HTML from URL using specified engine."""
        if engine not in self._engines:
            raise ValueError(f"Engine not available: {engine}")
        return await self._engines[engine].fetch(url, **kwargs)

    async def scrape(self, job: ScrapeJob) -> List[ScrapedItem]:
        """Scrape data using the job's configured engine."""
        engine_name = job.engine
        if engine_name not in self._engines:
            raise ValueError(f"Engine not available: {engine_name}")

        engine = self._engines[engine_name]
        return await engine.scrape(job)

    def get_available_engines(self) -> List[str]:
        """Return list of available engine names."""
        return list(self._engines.keys())
