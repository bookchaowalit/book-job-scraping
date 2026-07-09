"""
Jina Reader engine — AI-optimized reading/scraping via Jina AI API.
Converts any URL to LLM-ready clean text/markdown.
Excellent for content extraction, summarization, and structured data.

Best for: article/content-heavy sites, AI data pipelines, research scraping.
Requires: JINA_API_KEY env var (free tier available).
Docs: https://jina.ai/reader/
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any

import httpx

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Jina Reader API endpoint
JINA_READER_URL = "https://r.jina.ai/"
JINA_SEARCH_URL = "https://s.jina.ai/"


class JinaReaderScraper(BaseScraper):
    """
    Scraper using Jina AI Reader API.
    Converts web pages to clean markdown/text optimized for LLMs.
    Also supports search via Jina's search endpoint.
    """

    def __init__(self, name: str = "jina", api_key: Optional[str] = None, **kwargs):
        super().__init__(name, **kwargs)
        self.api_key = api_key or os.environ.get("JINA_API_KEY", "")

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers for Jina API."""
        headers = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def fetch(self, url: str, use_cache: bool = True, **kwargs) -> Optional[str]:
        """
        Read URL via Jina Reader. Returns clean markdown.

        Kwargs:
            target_selector: CSS selector to target specific content
            search: if True, use Jina search instead of reader
            query: search query (when search=True)
        """
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return cached

        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        use_search = kwargs.get("search", False)
        query = kwargs.get("query", "")

        if use_search and query:
            return await self._search(query, **kwargs)

        # Build Jina Reader URL
        reader_url = f"{JINA_READER_URL}{url}"

        headers = self._get_headers()
        target_selector = kwargs.get("target_selector")
        if target_selector:
            headers["X-Target-Selector"] = target_selector

        # Wait for selector (for JS-rendered content)
        wait_selector = kwargs.get("wait_selector")
        if wait_selector:
            headers["X-Wait-For-Selector"] = wait_selector

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(reader_url, headers=headers)
                    resp.raise_for_status()

                data = resp.json()
                content = data.get("data", {})

                # Extract markdown content
                markdown = content.get("content", "")
                title = content.get("title", "")
                description = content.get("description", "")

                if markdown:
                    self._set_cache(url, markdown)
                    self.stats["misses"] += 1
                    logger.info(
                        f"[JINA OK] {url}: {title[:60]} ({len(markdown)} chars)"
                    )
                    return markdown
                else:
                    logger.warning(f"[JINA EMPTY] {url}: no content extracted")

            except httpx.HTTPStatusError as e:
                logger.error(f"[JINA HTTP] {url}: {e.response.status_code} (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"[JINA ERROR] {url}: {e} (attempt {attempt+1})")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        logger.error(f"[JINA FAILED] {url} after {self.max_retries} attempts")
        return None

    async def _search(self, query: str, **kwargs) -> Optional[str]:
        """
        Search the web via Jina Search API.
        Returns aggregated markdown from top results.
        """
        search_url = f"{JINA_SEARCH_URL}{query}"
        headers = self._get_headers()

        num_results = kwargs.get("num_results", 5)
        headers["X-Num-Results"] = str(num_results)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(search_url, headers=headers)
                resp.raise_for_status()

            data = resp.json()
            results = data.get("data", [])

            combined = []
            for item in results:
                title = item.get("title", "")
                url = item.get("url", "")
                content = item.get("content", "")
                combined.append(f"## {title}\n**Source:** {url}\n\n{content}\n")

            if combined:
                result_text = "\n---\n".join(combined)
                logger.info(f"[JINA SEARCH] '{query}': {len(results)} results")
                return result_text

        except Exception as e:
            logger.error(f"[JINA SEARCH ERROR] '{query}': {e}")
            self.stats["errors"] += 1

        return None

    async def read_multiple(self, urls: List[str]) -> List[Dict[str, str]]:
        """
        Read multiple URLs concurrently via Jina Reader.

        Returns:
            List of dicts with 'url', 'content', 'title' keys.
        """
        tasks = [self.fetch(url, use_cache=True) for url in urls]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for url, content in zip(urls, results_raw):
            if isinstance(content, Exception):
                results.append({"url": url, "content": "", "error": str(content)})
            elif content:
                results.append({"url": url, "content": content, "title": ""})
            else:
                results.append({"url": url, "content": "", "error": "empty"})

        return results

    async def run(self):
        """Override in subclass."""
        raise NotImplementedError("Subclasses must implement run()")
