"""
Deduplicator — remove duplicate records across scraper runs
Uses content hashing to detect duplicates
"""
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
HASH_DB_FILE = DATA_DIR / "hash_db.json"


class Deduplicator:
    """
    Detect and remove duplicate records using content hashing.
    
    Usage:
        dedup = Deduplicator()
        unique_items = dedup.deduplicate(items, key_fields=["title", "url"])
        dedup.save()  # persist hash DB
    """

    def __init__(self, hash_db: Path = HASH_DB_FILE):
        self.hash_db_file = hash_db
        self.seen_hashes: Dict[str, dict] = {}
        self._load_db()

    def _load_db(self):
        """Load hash database from disk."""
        if self.hash_db_file.exists():
            with open(self.hash_db_file) as f:
                self.seen_hashes = json.load(f)
        else:
            self.seen_hashes = {}

    def save(self):
        """Persist hash database to disk."""
        self.hash_db_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.hash_db_file, "w") as f:
            json.dump(self.seen_hashes, f, indent=2)

    def _make_hash(self, item: dict, key_fields: List[str]) -> str:
        """
        Generate a content hash from specified fields.
        
        Args:
            item: The record dict
            key_fields: Fields to include in hash (e.g. ["title", "url"])
        
        Returns:
            MD5 hash string
        """
        # Normalize: lowercase, strip whitespace, concat key fields
        parts = []
        for field in key_fields:
            val = str(item.get(field, "")).strip().lower()
            parts.append(val)
        
        content = "|".join(parts)
        return hashlib.md5(content.encode()).hexdigest()

    def is_duplicate(self, item: dict, key_fields: List[str]) -> bool:
        """Check if an item is a known duplicate."""
        h = self._make_hash(item, key_fields)
        return h in self.seen_hashes

    def deduplicate(
        self,
        items: List[dict],
        key_fields: Optional[List[str]] = None,
        keep: str = "first",
    ) -> List[dict]:
        """
        Remove duplicates from a list of items.
        
        Args:
            items: List of record dicts
            key_fields: Fields to hash for dedup. If None, uses all fields.
            keep: "first" or "last" — which duplicate to keep
        
        Returns:
            Deduplicated list
        """
        if not items:
            return []

        # Auto-detect key fields if not provided
        if key_fields is None:
            key_fields = self._auto_key_fields(items[0])

        seen: Set[str] = set()
        unique = []
        dup_count = 0

        if keep == "first":
            for item in items:
                h = self._make_hash(item, key_fields)
                if h not in seen and h not in self.seen_hashes:
                    seen.add(h)
                    self.seen_hashes[h] = {
                        "first_seen": datetime.now().isoformat(),
                        "key": {f: item.get(f) for f in key_fields},
                        "count": 1,
                    }
                    unique.append(item)
                else:
                    dup_count += 1
                    if h in self.seen_hashes:
                        self.seen_hashes[h]["count"] += 1
        else:  # keep == "last"
            # Reverse, keep first occurrence, then reverse back
            reversed_items = list(reversed(items))
            for item in reversed_items:
                h = self._make_hash(item, key_fields)
                if h not in seen and h not in self.seen_hashes:
                    seen.add(h)
                    self.seen_hashes[h] = {
                        "first_seen": datetime.now().isoformat(),
                        "key": {f: item.get(f) for f in key_fields},
                        "count": 1,
                    }
                    unique.append(item)
                else:
                    dup_count += 1
            unique.reverse()

        print(f"[Dedup] {len(items)} items → {len(unique)} unique ({dup_count} duplicates removed)")
        return unique

    def _auto_key_fields(self, item: dict) -> List[str]:
        """Auto-detect best key fields for deduplication."""
        # Priority: url > link > title > name > id
        candidates = ["url", "link", "title", "name", "id"]
        found = [f for f in candidates if f in item]
        
        if not found:
            # Fallback: use first 3 string fields
            found = [k for k, v in item.items() if isinstance(v, str)][:3]
        
        return found if found else list(item.keys())[:2]

    def merge_files(self, file_paths: List[Path], output: Path, key_fields: List[str]):
        """
        Merge multiple JSON files, deduplicating across all of them.
        
        Args:
            file_paths: List of JSON file paths to merge
            output: Output file path for merged result
            key_fields: Fields to use for dedup
        """
        all_items = []
        for fp in file_paths:
            if fp.exists():
                with open(fp) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_items.extend(data)
                    else:
                        all_items.append(data)
                print(f"[Dedup] Loaded {len(data) if isinstance(data, list) else 1} items from {fp.name}")

        unique = self.deduplicate(all_items, key_fields)

        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(unique, f, indent=2, ensure_ascii=False)

        print(f"[Dedup] Merged {len(all_items)} → {len(unique)} items → {output}")
        return unique

    def stats(self) -> dict:
        """Get dedup database stats."""
        return {
            "total_hashes": len(self.seen_hashes),
            "db_size_kb": len(json.dumps(self.seen_hashes)) // 1024,
        }

    def clear(self):
        """Clear the hash database."""
        self.seen_hashes = {}
        self.save()
        print("[Dedup] Hash database cleared")

    def __repr__(self):
        return f"Deduplicator(hashes={len(self.seen_hashes)})"
