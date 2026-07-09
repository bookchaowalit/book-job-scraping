"""
Scraping engines — one per library type.
Import the engine you need for each scraping task.
"""

from .base import BaseScraper
from .httpx_bs4 import HttpxBS4Scraper
from .playwright_engine import PlaywrightScraper
from .rss_engine import RSSScraper

# Optional engines — install deps only when needed
try:
    from .selenium_engine import SeleniumScraper
except ImportError:
    SeleniumScraper = None  # pip install selenium

try:
    from .scrapy_engine import ScrapyScraper
except ImportError:
    ScrapyScraper = None  # pip install scrapy

__all__ = [
    "BaseScraper",
    "HttpxBS4Scraper",
    "PlaywrightScraper",
    "SeleniumScraper",
    "ScrapyScraper",
    "RSSScraper",
]
