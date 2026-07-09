"""
Core domain models — pure Python, no external dependencies.
These represent the business entities of the scraping platform.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ScrapedItem:
    """Base model for any scraped data."""
    source: str = ""
    url: str = ""
    title: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    cleaned: bool = False
    duplicate: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScrapedItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class JobListing(ScrapedItem):
    """Job board listing."""
    company: str = ""
    location: str = ""
    salary: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    job_type: str = "full-time"  # full-time, part-time, contract, remote
    posted_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class BusinessListing(ScrapedItem):
    """Business directory listing (restaurants, shops, services)."""
    name: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    rating: Optional[float] = None
    reviews_count: int = 0
    price_range: str = ""
    opening_hours: str = ""
    area: str = ""


@dataclass
class ProductListing(ScrapedItem):
    """E-commerce product listing."""
    name: str = ""
    price: Optional[float] = None
    currency: str = "THB"
    original_price: Optional[float] = None
    discount_percent: Optional[int] = None
    image_url: str = ""
    seller: str = ""
    seller_rating: Optional[float] = None
    sold_count: int = 0
    category: str = ""
    in_stock: bool = True


@dataclass
class PropertyListing(ScrapedItem):
    """Real estate listing."""
    title: str = ""
    property_type: str = ""  # condo, house, land, commercial
    price: Optional[float] = None
    price_per_sqm: Optional[float] = None
    area_sqm: Optional[float] = None
    bedrooms: int = 0
    bathrooms: int = 0
    location: str = ""
    address: str = ""
    floor: Optional[int] = None
    furnished: bool = False


@dataclass
class NewsArticle(ScrapedItem):
    """News/blog article."""
    title: str = ""
    summary: str = ""
    content: str = ""
    author: str = ""
    published_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    language: str = "th"


@dataclass
class ScrapeJob:
    """Definition of a scheduled scraping job."""
    name: str
    category: str  # jobs, ecommerce, restaurants, directories, news, social, property
    engine: str  # httpx, playwright, selenium, scrapy, rss, firecrawl, jina
    url: str
    schedule: str  # cron expression: "0 */6 * * *" = every 6 hours
    enabled: bool = True
    rate_limit: float = 2.0
    max_pages: int = 10
    params: Dict[str, Any] = field(default_factory=dict)
    scraper_module: Optional[str] = None  # e.g. "jobs.jobsdb_scraper"
    scraper_class: Optional[str] = None   # e.g. "JobsdbScraper"
    last_run: Optional[str] = None
    run_count: int = 0
    error_count: int = 0

    def is_due(self) -> bool:
        """Check if job should run based on schedule."""
        if not self.enabled:
            return False
        if not self.last_run:
            return True
        # Parse cron to determine if due
        # Simplified: check if enough time has passed
        from datetime import timedelta
        intervals = {
            "hourly": timedelta(hours=1),
            "2h": timedelta(hours=2),
            "6h": timedelta(hours=6),
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
        }
        # Map common cron patterns to intervals
        cron_interval_map = {
            "0 * * * *": "hourly",
            "0 */2 * * *": "2h",
            "0 */6 * * *": "6h",
            "0 0 * * *": "daily",
            "0 8 * * *": "daily",
            "0 9 * * *": "daily",
            "0 0 * * 0": "weekly",
            "0 0 * * 1": "weekly",
        }
        interval_key = cron_interval_map.get(self.schedule, "daily")
        interval = intervals.get(interval_key, timedelta(days=1))
        last = datetime.fromisoformat(self.last_run)
        return datetime.now() - last >= interval


@dataclass
class MoneyOpportunity(ScrapedItem):
    """Money-making opportunity from trending markets."""
    category: str = ""  # tcg, digital-products, ai-content, print-on-demand, courses, freelance-services, trending-products
    price: str = ""
    trend_score: int = 0  # 0-100
    competition_level: str = ""  # low, medium, high, varies
    notes: str = ""


@dataclass
class ScrapeResult:
    """Result of a scrape operation."""
    job_name: str
    success: bool
    items_scraped: int = 0
    items_new: int = 0  # after dedup
    items_cleaned: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    exported_to: List[str] = field(default_factory=list)  # file paths
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
