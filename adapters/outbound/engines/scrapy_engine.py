"""
Scrapy engine — for large-scale crawls (10,000+ pages).
Use when: need to crawl entire sites, follow links, handle pagination at scale.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)


class ScrapyScraper(BaseScraper):
    """
    Wrapper around Scrapy spiders for large-scale crawling.
    For full Scrapy projects, create a separate spider file.
    This class provides a lightweight wrapper for simple crawl tasks.
    """

    def __init__(self, name: str, **kwargs):
        super().__init__(name, **kwargs)
        self.start_urls: List[str] = []
        self.allowed_domains: List[str] = []

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch single URL using Scrapy's async capabilities."""
        import scrapy
        from scrapy.crawler import CrawlerProcess
        from scrapy.http import Request

        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        # For single URL fetch, fall back to httpx
        import httpx
        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
                content = response.text
                self._set_cache(url, content)
                self.stats["misses"] += 1
                return content
        except Exception as e:
            logger.error(f"[ERROR] {url}: {e}")
            self.stats["errors"] += 1
            return None

    def run_spider(self, spider_cls):
        """
        Run a Scrapy spider class.
        
        Usage:
            class MySpider(scrapy.Spider):
                name = 'my_spider'
                start_urls = ['https://example.com']
                
                def parse(self, response):
                    yield {'title': response.css('h1::text').get()}
            
            scraper = ScrapyScraper('test')
            scraper.run_spider(MySpider)
        """
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings

        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/5.0 (compatible; BookScraper/1.0)',
            'LOG_LEVEL': 'INFO',
            'FEEDS': {
                f'data/exported/{self.name}.json': {'format': 'json'},
            },
        })
        process.crawl(spider_cls)
        process.start()

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
