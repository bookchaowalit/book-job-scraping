"""
Base scraper engine — all engines inherit from this.
Provides: rate limiting, caching, retry, export, logging.
"""

import asyncio
import csv
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseScraper:
    """Base class for all web scrapers regardless of engine."""

    def __init__(
        self,
        name: str,
        rate_limit: float = 2.0,
        max_retries: int = 3,
        timeout: float = 30.0,
        cache_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None,
    ):
        self.name = name
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.timeout = timeout
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.cache_dir = cache_dir or project_root / "data" / "cache"
        self.data_dir = data_dir or project_root / "data"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.last_request_time = 0.0
        self.results: List[Dict[str, Any]] = []
        self.stats = {"requests": 0, "hits": 0, "misses": 0, "errors": 0}

    async def _wait_for_rate_limit(self):
        """Ensure minimum time between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            await asyncio.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _get_cache_key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _get_cached(self, url: str, max_age: int = 86400) -> Optional[str]:
        """Get cached response if fresh (< max_age seconds)."""
        cache_key = self._get_cache_key(url)
        cache_file = self.cache_dir / f"{cache_key}.html"
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < max_age:
                self.stats["hits"] += 1
                logger.debug(f"[CACHE] {url}")
                return cache_file.read_text(encoding="utf-8")
        return None

    def _set_cache(self, url: str, content: str):
        cache_key = self._get_cache_key(url)
        cache_file = self.cache_dir / f"{cache_key}.html"
        cache_file.write_text(content, encoding="utf-8")

    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """Fetch URL — override in subclass with engine-specific logic."""
        raise NotImplementedError

    def add_result(self, data: Dict[str, Any]):
        """Add a scraped result with metadata."""
        data.setdefault("scraped_at", datetime.now().isoformat())
        data.setdefault("source", self.name)
        self.results.append(data)

    def export_csv(self, filename: str, fieldnames: Optional[List[str]] = None) -> Path:
        if not self.results:
            logger.warning(f"No results to export for {self.name}")
            return Path()
        output_dir = self.data_dir / "exported"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        if not fieldnames:
            fieldnames = list(self.results[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)
        logger.info(f"Exported {len(self.results)} results → {filepath}")
        return filepath

    def export_json(self, filename: str) -> Path:
        if not self.results:
            return Path()
        output_dir = self.data_dir / "exported"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported {len(self.results)} results → {filepath}")
        return filepath

    def print_stats(self):
        print(f"\n[{self.name}] Stats:")
        print(f"  Requests: {self.stats['requests']}")
        print(f"  Cache hits: {self.stats['hits']}")
        print(f"  Cache misses: {self.stats['misses']}")
        print(f"  Errors: {self.stats['errors']}")
        print(f"  Results: {len(self.results)}")

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
