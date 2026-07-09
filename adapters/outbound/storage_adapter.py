"""
Storage adapter — implements StoragePort.
File-based storage with JSON files organized by category.
"""
import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from core.models import ScrapedItem, JobListing, BusinessListing, ProductListing, NewsArticle
from core.ports import StoragePort


class StorageAdapter:
    """
    File-based storage adapter.
    Stores data as JSON files organized by category.
    Future: can be replaced with database adapter.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[ScrapedItem]] = {}

    def save(self, items: List[ScrapedItem], collection: str) -> int:
        """Save items to collection (category folder)."""
        collection_dir = self.data_dir / collection
        collection_dir.mkdir(parents=True, exist_ok=True)

        # Load existing items
        existing = self.load(collection)

        # Add new items (avoid duplicates by URL)
        existing_urls = {item.url for item in existing if item.url}
        new_count = 0
        for item in items:
            if not item.url or item.url not in existing_urls:
                existing.append(item)
                if item.url:
                    existing_urls.add(item.url)
                new_count += 1

        # Save all items
        filepath = collection_dir / "items.json"
        data = [item.to_dict() for item in existing]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        # Update cache
        self._cache[collection] = existing

        return new_count

    # Map collection names to exported filenames
    EXPORTED_FILE_MAP = {
        "jobs": ["jobsdb_jobs.json", "jobsdb_remote.json"],
        "ecommerce": ["shopee_products.json", "lazada_products.json"],
        "restaurants": ["wongnai_restaurants.json"],
        "news": ["thai_news.json"],
        "property": ["ddproperty_listings.json"],
        "directories": ["yellow_pages.json"],
    }

    def load(self, collection: str, filters: Optional[Dict] = None) -> List[ScrapedItem]:
        """Load items from collection (category folder or exported files)."""
        # Check cache first
        if collection in self._cache and not filters:
            return self._cache[collection]

        # Try primary path: data/{collection}/items.json
        filepath = self.data_dir / collection / "items.json"
        data = None
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

        # Fallback: load from data/exported/ files
        if data is None:
            exported_dir = self.data_dir / "exported"
            if exported_dir.exists():
                exported_files = self.EXPORTED_FILE_MAP.get(collection, [])
                all_data = []
                for filename in exported_files:
                    fp = exported_dir / filename
                    if fp.exists():
                        try:
                            with open(fp, "r", encoding="utf-8") as f:
                                file_data = json.load(f)
                                if isinstance(file_data, list):
                                    all_data.extend(file_data)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                if all_data:
                    data = all_data

        if data is None:
            return []

        items = [self._dict_to_item(d) for d in data]

        # Apply filters
        if filters:
            items = self._apply_filters(items, filters)

        return items

    def exists(self, url: str) -> bool:
        """Check if URL exists in any collection."""
        for collection_dir in self.data_dir.iterdir():
            if collection_dir.is_dir():
                filepath = collection_dir / "items.json"
                if filepath.exists():
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if any(item.get("url") == url for item in data):
                            return True
        return False

    def _dict_to_item(self, data: dict) -> ScrapedItem:
        """Convert dict back to appropriate ScrapedItem subclass."""
        # Determine type from raw_data or source
        source = data.get("source", "")
        if "job" in source or "salary" in data:
            return JobListing(**{k: v for k, v in data.items() if k in JobListing.__dataclass_fields__})
        elif "business" in source or "rating" in data:
            return BusinessListing(**{k: v for k, v in data.items() if k in BusinessListing.__dataclass_fields__})
        elif "product" in source or "price" in data:
            return ProductListing(**{k: v for k, v in data.items() if k in ProductListing.__dataclass_fields__})
        else:
            return ScrapedItem(**{k: v for k, v in data.items() if k in ScrapedItem.__dataclass_fields__})

    def _apply_filters(self, items: List[ScrapedItem], filters: Dict) -> List[ScrapedItem]:
        """Apply filters to items."""
        filtered = items
        for key, value in filters.items():
            if key.endswith("_contains"):
                field = key.replace("_contains", "")
                filtered = [i for i in filtered if value.lower() in str(getattr(i, field, "")).lower()]
            elif key.endswith("_lte"):
                field = key.replace("_lte", "")
                filtered = [i for i in filtered if getattr(i, field, 0) is not None and getattr(i, field, 0) <= value]
            elif key.endswith("_gte"):
                field = key.replace("_gte", "")
                filtered = [i for i in filtered if getattr(i, field, 0) is not None and getattr(i, field, 0) >= value]
            else:
                filtered = [i for i in filtered if getattr(i, key, None) == value]
        return filtered

    def get_collections(self) -> List[str]:
        """Get list of available collections."""
        return [d.name for d in self.data_dir.iterdir() if d.is_dir()]

    def get_stats(self) -> Dict:
        """Get storage statistics."""
        stats = {}
        for collection in self.get_collections():
            items = self.load(collection)
            stats[collection] = {
                "count": len(items),
                "last_updated": max((i.scraped_at for i in items), default=None),
            }
        return stats
