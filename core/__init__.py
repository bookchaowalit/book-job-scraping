"""
Core domain layer — pure business logic, zero external dependencies.
Models, ports (interfaces), use cases, and pipeline operations.
"""
from .models import (
    ScrapedItem,
    JobListing,
    BusinessListing,
    ProductListing,
    PropertyListing,
    NewsArticle,
    ScrapeJob,
    ScrapeResult,
)
from .ports import (
    ScraperPort,
    ExporterPort,
    StoragePort,
    SchedulerPort,
    NotificationPort,
)
from .use_cases import ScrapeUseCase, SearchUseCase
from .pipeline import DataCleaner, Deduplicator

__all__ = [
    # Models
    "ScrapedItem",
    "JobListing",
    "BusinessListing",
    "ProductListing",
    "PropertyListing",
    "NewsArticle",
    "ScrapeJob",
    "ScrapeResult",
    # Ports
    "ScraperPort",
    "ExporterPort",
    "StoragePort",
    "SchedulerPort",
    "NotificationPort",
    # Use Cases
    "ScrapeUseCase",
    "SearchUseCase",
    # Pipeline
    "DataCleaner",
    "Deduplicator",
]
