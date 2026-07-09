"""
Firecrawl engine — AI-powered scraping via Firecrawl API.
Returns clean markdown/text from any URL. Handles JS rendering, anti-bot,
and structured extraction automatically.

Best for: sites with heavy anti-bot protection, JS-heavy SPAs, structured extraction.
Requires: FIRECRAWL_API_KEY env var (free tier: 500 pages/month).
Docs: https://docs.firecrawl.dev
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any

from .base import BaseScraper

logger = logging.getLogger(__name__)


class FirecrawlScraper(BaseScraper):
    """
    Scraper using Firecrawl API for AI-optimized web extraction.
    Returns clean markdown by default, supports structured extraction.
    """

    def __init__(self, name: str = "firecrawl", api_key: Optional[str] = None, **kwargs):
        super().__init__(name, **kwargs)
        self.api_key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
        self._client = None

    def _get_client(self):
        """Lazy-init Firecrawl client."""
        if self._client is None:
            try:
                from firecrawl import FirecrawlApp
                if not self.api_key:
                    raise ValueError(
                        "FIRECRAWL_API_KEY not set. "
                        "Get one at https://firecrawl.dev (free: 500 pages/mo)"
                    )
                self._client = FirecrawlApp(api_key=self.api_key)
            except ImportError:
                raise ImportError("firecrawl-py not installed. Run: pip install firecrawl-py")
        return self._client

    async def fetch(self, url: str, use_cache: bool = True, **kwargs) -> Optional[str]:
        """
        Scrape URL via Firecrawl API. Returns markdown content.
        
        Kwargs:
            formats: list of output formats (default: ["markdown"])
            only_main_content: bool (default: True)
            timeout: int in ms (default: 30000)
        """
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        formats = kwargs.get("formats", ["markdown"])
        only_main_content = kwargs.get("only_main_content", True)
        fc_timeout = kwargs.get("fc_timeout", 30000)

        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                # Firecrawl's scrape is sync — run in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: client.scrape_url(
                        url,
                        params={
                            "formats": formats,
                            "onlyMainContent": only_main_content,
                            "timeout": fc_timeout,
                        }
                    )
                )

                # Extract content based on requested formats
                content = ""
                if "markdown" in formats and result.get("markdown"):
                    content = result["markdown"]
                elif "html" in formats and result.get("html"):
                    content = result["html"]
                elif "rawHtml" in formats and result.get("rawHtml"):
                    content = result["rawHtml"]

                if content:
                    self._set_cache(url, content)
                    self.stats["misses"] += 1
                    logger.info(f"[FIRECRAWL OK] {url} ({len(content)} chars)")
                    return content
                else:
                    logger.warning(f"[FIRECRAWL EMPTY] {url}: {result.get('metadata', {})}")

            except Exception as e:
                logger.error(f"[FIRECRAWL ERROR] {url}: {e} (attempt {attempt+1})")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        logger.error(f"[FIRECRAWL FAILED] {url} after {self.max_retries} attempts")
        return None

    async def scrape_structured(self, url: str, schema: Dict) -> Optional[Dict]:
        """
        Extract structured data using Firecrawl's LLM extraction.
        
        Args:
            url: URL to scrape
            schema: JSON schema for extraction (e.g. {"type": "object", "properties": {...}})
        
        Returns:
            Extracted data dict matching schema, or None on failure.
        """
        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.scrape_url(
                    url,
                    params={
                        "formats": ["extract"],
                        "extract": {"schema": schema},
                    }
                )
            )
            extracted = result.get("extract", {})
            if extracted:
                logger.info(f"[FIRECRAWL EXTRACT] {url}: {list(extracted.keys())}")
                return extracted
        except Exception as e:
            logger.error(f"[FIRECRAWL EXTRACT ERROR] {url}: {e}")
            self.stats["errors"] += 1

        return None

    async def crawl_site(self, url: str, max_pages: int = 10, **kwargs) -> List[Dict]:
        """
        Crawl multiple pages from a starting URL.
        
        Args:
            url: Starting URL
            max_pages: Maximum pages to crawl
            include_paths: URL path patterns to include (e.g. ["/blog/*"])
            exclude_paths: URL path patterns to exclude
        
        Returns:
            List of page results with markdown content.
        """
        self.stats["requests"] += 1

        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()
            
            crawl_params = {
                "limit": max_pages,
                "scrapeOptions": {
                    "formats": kwargs.get("formats", ["markdown"]),
                    "onlyMainContent": kwargs.get("only_main_content", True),
                }
            }
            if "include_paths" in kwargs:
                crawl_params["includePaths"] = kwargs["include_paths"]
            if "exclude_paths" in kwargs:
                crawl_params["excludePaths"] = kwargs["exclude_paths"]

            result = await loop.run_in_executor(
                None,
                lambda: client.crawl_url(url, params=crawl_params)
            )

            pages = result.get("data", [])
            logger.info(f"[FIRECRAWL CRAWL] {url}: {len(pages)} pages")
            return pages

        except Exception as e:
            logger.error(f"[FIRECRAWL CRAWL ERROR] {url}: {e}")
            self.stats["errors"] += 1
            return []

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
