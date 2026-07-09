"""
Data validators using Pydantic schemas.
Ensures scraped data is clean and consistent before export/MCP.
"""

from typing import Optional, List
from datetime import datetime

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback if pydantic not installed
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Field(default=None, **kwargs):
        return default


class JobListing(BaseModel):
    """Schema for job board scrapers."""
    title: str = ""
    company: str = ""
    location: str = ""
    salary: Optional[str] = None
    url: str = ""
    description: Optional[str] = None
    source: str = ""
    posted_date: Optional[str] = None
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = []


class BusinessListing(BaseModel):
    """Schema for business directory scrapers."""
    name: str = ""
    category: str = ""
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    source: str = ""
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProductListing(BaseModel):
    """Schema for e-commerce scrapers."""
    name: str = ""
    price: Optional[float] = None
    currency: str = "THB"
    url: str = ""
    image_url: Optional[str] = None
    seller: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    category: Optional[str] = None
    source: str = ""
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PropertyListing(BaseModel):
    """Schema for real estate scrapers."""
    title: str = ""
    property_type: str = ""  # condo, house, land, commercial
    price: Optional[float] = None
    price_per_sqm: Optional[float] = None
    area_sqm: Optional[float] = None
    location: str = ""
    url: str = ""
    source: str = ""
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class NewsArticle(BaseModel):
    """Schema for news/blog scrapers."""
    title: str = ""
    url: str = ""
    summary: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[str] = None
    source: str = ""
    tags: List[str] = []
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())
