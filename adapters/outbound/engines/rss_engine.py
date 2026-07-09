"""
RSS/Atom feed engine — for blogs, news, podcasts, structured feeds.
Easiest and most reliable. Use when the site has an RSS/Atom feed.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser

from .base import BaseScraper

logger = logging.getLogger(__name__)


class RSSScraper(BaseScraper):
    """Scraper for RSS and Atom feeds using feedparser."""

    def __init__(self, name: str, **kwargs):
        super().__init__(name, **kwargs)
        self.feeds: List[str] = []

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch and parse RSS/Atom feed."""
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.error(f"[FEED ERROR] {url}: {feed.bozo_exception}")
                self.stats["errors"] += 1
                return None

            # Store raw feed as cache
            raw = str(feed)
            self._set_cache(url, raw)
            self.stats["misses"] += 1
            return raw
        except Exception as e:
            logger.error(f"[FEED ERROR] {url}: {e}")
            self.stats["errors"] += 1
            return None

    def parse_feed(self, url: str) -> Dict[str, Any]:
        """Parse feed and return feedparser result."""
        return feedparser.parse(url)

    def extract_entries(self, feed_url: str) -> List[Dict[str, Any]]:
        """Extract entries from a feed URL."""
        feed = feedparser.parse(feed_url)
        entries = []
        for entry in feed.entries:
            data = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
                "author": entry.get("author", ""),
                "tags": [t.get("term", "") for t in entry.get("tags", [])],
                "feed_url": feed_url,
                "feed_title": feed.feed.get("title", ""),
            }
            entries.append(data)
        return entries

    async def run(self):
        """Scrape all configured feeds."""
        for feed_url in self.feeds:
            logger.info(f"Scraping feed: {feed_url}")
            entries = self.extract_entries(feed_url)
            for entry in entries:
                self.add_result(entry)
            logger.info(f"  Found {len(entries)} entries")
