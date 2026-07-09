"""
Core ports — interfaces that adapters must implement.
This is the contract between core logic and external systems.
"""
from typing import Protocol, List, Dict, Any, Optional
from .models import ScrapedItem, ScrapeJob, ScrapeResult


class ScraperPort(Protocol):
    """Port for scraping engines (httpx, playwright, selenium, etc.)."""

    async def fetch(self, url: str, **kwargs) -> Optional[str]:
        """Fetch raw HTML/content from URL."""
        ...

    async def scrape(self, job: ScrapeJob) -> List[ScrapedItem]:
        """Scrape data according to job configuration."""
        ...

    def supports_engine(self, engine_name: str) -> bool:
        """Check if this adapter supports the given engine."""
        ...


class ExporterPort(Protocol):
    """Port for data export (CSV, JSON, SQLite, Parquet)."""

    def export(self, items: List[ScrapedItem], format: str, filename: str) -> str:
        """Export items to specified format. Returns file path."""
        ...

    def supported_formats(self) -> List[str]:
        """Return list of supported export formats."""
        ...


class StoragePort(Protocol):
    """Port for data persistence (cache, database)."""

    def save(self, items: List[ScrapedItem], collection: str) -> int:
        """Save items. Returns count saved."""
        ...

    def load(self, collection: str, filters: Optional[Dict] = None) -> List[ScrapedItem]:
        """Load items from storage."""
        ...

    def exists(self, url: str) -> bool:
        """Check if URL already scraped (for dedup)."""
        ...


class SchedulerPort(Protocol):
    """Port for job scheduling."""

    def schedule(self, job: ScrapeJob) -> str:
        """Schedule a job. Returns job ID."""
        ...

    def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled job."""
        ...

    def get_pending_jobs(self) -> List[ScrapeJob]:
        """Get jobs that are due to run."""
        ...

    def mark_completed(self, job_id: str, result: ScrapeResult):
        """Mark job as completed with result."""
        ...


class NotificationPort(Protocol):
    """Port for notifications (email, LINE, Slack)."""

    def send(self, message: str, level: str = "info") -> bool:
        """Send notification. Level: info, warning, error."""
        ...
