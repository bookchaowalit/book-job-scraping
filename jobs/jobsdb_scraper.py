#!/usr/bin/env python3
"""
Jobsdb Thailand scraper — uses httpx+BS4 engine.
Scrapes public job listings from th.jobsdb.com.

MCP Tool: search_jobs
Data: job title, company, location, salary, URL, description snippet
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.outbound.engines.httpx_bs4 import HttpxBS4Scraper
from core.models import JobListing

logger = logging.getLogger(__name__)

# Default search queries for AI/tech jobs in Thailand
DEFAULT_SEARCH_QUERIES = [
    "AI developer",
    "chatbot developer",
    "Python developer",
    "Full stack developer",
    "Data scientist",
    "Machine learning",
    "Software engineer",
    "Backend developer",
    "Frontend developer",
    "DevOps engineer",
]

BASE_URL = "https://th.jobsdb.com/th/jobs"


class JobsdbScraper(HttpxBS4Scraper):
    """Scrape job listings from Jobsdb Thailand."""

    def __init__(self, keywords: List[str] = None, extra_url_params: dict = None):
        super().__init__(
            name="jobsdb_thailand",
            rate_limit=3.0,  # be gentle
            max_retries=3,
            timeout=30.0,
        )
        self.keywords = keywords or DEFAULT_SEARCH_QUERIES
        self.extra_url_params = extra_url_params or {}

    def build_search_url(self, query: str, page: int = 1) -> str:
        """Build Jobsdb search URL."""
        url = f"{BASE_URL}?keywords={query.replace(' ', '%20')}&page={page}"
        for k, v in self.extra_url_params.items():
            url += f"&{k}={v}"
        return url

    def parse_job_card(self, card) -> Optional[JobListing]:
        """Parse a single job card element."""
        try:
            title_el = card.select_one("a[data-automation='jobTitle']") or card.select_one("h1 a")
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.select_one("a[data-automation='jobCompany']") or card.select_one("span[data-automation='jobCompany']")
            company = company_el.get_text(strip=True) if company_el else ""

            location_el = card.select_one("span[data-automation='jobLocation']")
            location = location_el.get_text(strip=True) if location_el else ""

            salary_el = card.select_one("span[data-automation='jobSalary']")
            salary = salary_el.get_text(strip=True) if salary_el else None

            link = ""
            if title_el and title_el.get("href"):
                href = title_el["href"]
                link = f"https://th.jobsdb.com{href}" if href.startswith("/") else href

            desc_el = card.select_one("span[data-automation='jobSnippet']")
            description = desc_el.get_text(strip=True) if desc_el else None

            if not title:
                return None

            return JobListing(
                title=title,
                company=company,
                location=location,
                salary=salary,
                url=link,
                description=description,
                source="jobsdb",
            )
        except Exception as e:
            logger.error(f"Error parsing job card: {e}")
            return None

    async def scrape_query(self, query: str, max_pages: int = 3):
        """Scrape jobs for a single search query."""
        logger.info(f"Scraping Jobsdb: '{query}' (max {max_pages} pages)")

        for page in range(1, max_pages + 1):
            url = self.build_search_url(query, page)
            soup = await self.fetch_and_parse(url)

            if not soup:
                break

            # Find job cards
            cards = soup.select("article") or soup.select("div[data-automation='jobCard']")
            if not cards:
                logger.info(f"  No more results on page {page}")
                break

            for card in cards:
                job = self.parse_job_card(card)
                if job:
                    self.add_result(job.__dict__)

            logger.info(f"  Page {page}: {len(cards)} jobs found")

    async def run(self, queries: List[str] = None, max_pages: int = 3):
        """Run scraper for all search queries."""
        queries = queries or self.keywords
        for query in queries:
            await self.scrape_query(query, max_pages)

        self.print_stats()
        self.export_csv("jobsdb_jobs.csv")
        self.export_json("jobsdb_jobs.json")
        return self.results


async def main():
    scraper = JobsdbScraper()
    results = await scraper.run()
    print(f"\nTotal jobs scraped: {len(results)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
