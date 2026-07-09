#!/usr/bin/env python3
"""
Scrape Dev.to articles via public API (free, no auth).
Tracks trending and recent articles for developer intelligence.

Outputs:
    - book-scraping/data/exported/devto_articles.csv (latest articles)
    - book-scraping/data/exported/devto_history.csv (appended daily)

Usage:
    python3 scripts/scrape_devto.py
    python3 scripts/scrape_devto.py --tags python,typescript,ai
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip install httpx")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[4]  # solo-empire/
OUTPUT_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data" / "exported"

DEVTO_API = "https://dev.to/api"

DEFAULT_TAGS = ["python", "typescript", "javascript", "react", "nextjs", "ai", "webdev", "programming"]


def fetch_articles_by_tag(tag: str, per_page: int = 20) -> list:
    """Fetch articles for a specific tag."""
    url = f"{DEVTO_API}/articles"
    params = {"tag": tag, "per_page": per_page, "page": 1}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Warning: Dev.to tag='{tag}' failed: {e}")
        return []


def fetch_trending(per_page: int = 30) -> list:
    """Fetch trending articles (no tag filter)."""
    url = f"{DEVTO_API}/articles"
    params = {"per_page": per_page, "top": 7}  # top 7 days trending
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Warning: Trending fetch failed: {e}")
        return []


def fetch_articles_by_user(username: str, per_page: int = 10) -> list:
    """Fetch articles from a specific user."""
    url = f"{DEVTO_API}/articles"
    params = {"username": username, "per_page": per_page}
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Warning: User '{username}' failed: {e}")
        return []


def normalize_article(article: dict, source_type: str = "tag") -> dict:
    """Normalize article to consistent format."""
    return {
        "id": article.get("id"),
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "description": article.get("description", "")[:200],
        "author": article.get("user", {}).get("username", ""),
        "tags": ",".join(article.get("tag_list", [])[:5]),
        "reactions": article.get("positive_reactions_count", 0),
        "comments": article.get("comments_count", 0),
        "published_at": article.get("published_at", ""),
        "source_type": source_type,
    }


def save_articles(articles: list, output_dir: Path):
    """Save articles to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "devto_articles.csv"
    fieldnames = ["id", "title", "url", "description", "author", "tags", "reactions", "comments", "published_at", "source_type"]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"  Saved {len(articles)} articles to {filepath}")


def append_history(articles: list, output_dir: Path):
    """Append to history CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "devto_history.csv"
    fieldnames = ["id", "title", "url", "description", "author", "tags", "reactions", "comments", "published_at", "source_type", "scraped_at"]
    now = datetime.now().isoformat()

    file_exists = filepath.exists()
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for a in articles:
            row = {**a, "scraped_at": now}
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Scrape Dev.to articles")
    parser.add_argument("--tags", default=",".join(DEFAULT_TAGS), help="Comma-separated tags")
    parser.add_argument("--per-page", type=int, default=20, help="Articles per tag (default: 20)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    tags = [t.strip() for t in args.tags.split(",")]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Dev.to Scraper")
    print(f"  Tags: {tags}")

    all_articles = []
    seen_ids = set()

    # Fetch trending
    print("  Fetching trending...")
    trending = fetch_trending(30)
    for a in trending:
        aid = a.get("id")
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            all_articles.append(normalize_article(a, "trending"))
    print(f"  Got {len(trending)} trending articles")

    # Fetch by tag
    for tag in tags:
        articles = fetch_articles_by_tag(tag, args.per_page)
        new_count = 0
        for a in articles:
            aid = a.get("id")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                all_articles.append(normalize_article(a, f"tag:{tag}"))
                new_count += 1
        print(f"  Tag '{tag}': {len(articles)} fetched, {new_count} new")

    save_articles(all_articles, output_dir)
    append_history(all_articles, output_dir)
    print(f"  Total unique articles: {len(all_articles)}")
    print("  Done.")


class DevToScraper:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, tags=None, per_page=20, **kwargs):
        self.tags = tags or DEFAULT_TAGS
        self.per_page = per_page

    async def run(self, **kwargs):
        print(f"[DevToScraper] Fetching articles for tags: {self.tags}")
        all_articles = []
        seen_ids = set()

        trending = fetch_trending(30)
        for a in trending:
            aid = a.get("id")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                all_articles.append(normalize_article(a, "trending"))

        for tag in self.tags:
            articles = fetch_articles_by_tag(tag, self.per_page)
            for a in articles:
                aid = a.get("id")
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    all_articles.append(normalize_article(a, f"tag:{tag}"))

        save_articles(all_articles, OUTPUT_DIR)
        append_history(all_articles, OUTPUT_DIR)
        print(f"  Total: {len(all_articles)} articles")
        return [{"source": "devto", "count": len(all_articles)}]


if __name__ == "__main__":
    main()
