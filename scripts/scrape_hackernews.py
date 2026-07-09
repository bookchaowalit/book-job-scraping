#!/usr/bin/env python3
"""
Scrape Hacker News via public Firebase API (free, no auth).
Tracks top stories, new stories, and "Who is hiring?" threads.

Outputs:
    - book-scraping/data/exported/hackernews_top.csv (latest top stories)
    - book-scraping/data/exported/hackernews_history.csv (appended daily)

Usage:
    python3 scripts/scrape_hackernews.py
    python3 scripts/scrape_hackernews.py --limit 50
"""

import argparse
import csv
import json
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

HN_API = "https://hacker-news.firebaseio.com/v0"
HN_SEARCH = "https://hn.algolia.com/api/v1"


def fetch_top_stories(limit: int = 30) -> list:
    """Fetch top story IDs then get details."""
    url = f"{HN_API}/topstories.json"
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    ids = resp.json()[:limit]

    stories = []
    for sid in ids:
        try:
            detail = httpx.get(f"{HN_API}/item/{sid}.json", timeout=10)
            detail.raise_for_status()
            item = detail.json()
            if item and item.get("title"):
                stories.append({
                    "id": sid,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                    "by": item.get("by", ""),
                    "time": datetime.fromtimestamp(item.get("time", 0)).isoformat(),
                    "descendants": item.get("descendants", 0),
                    "type": "top",
                })
        except Exception:
            continue
    return stories


def fetch_new_stories(limit: int = 20) -> list:
    """Fetch newest stories."""
    url = f"{HN_API}/newstories.json"
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    ids = resp.json()[:limit]

    stories = []
    for sid in ids:
        try:
            detail = httpx.get(f"{HN_API}/item/{sid}.json", timeout=10)
            detail.raise_for_status()
            item = detail.json()
            if item and item.get("title") and item.get("score", 0) >= 5:
                stories.append({
                    "id": sid,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                    "by": item.get("by", ""),
                    "time": datetime.fromtimestamp(item.get("time", 0)).isoformat(),
                    "descendants": item.get("descendants", 0),
                    "type": "new",
                })
        except Exception:
            continue
    return stories


def fetch_hiring_threads(limit: int = 5) -> list:
    """Search for 'Who is hiring?' threads via Algolia HN search."""
    url = f"{HN_SEARCH}/search"
    params = {
        "query": "Who is hiring?",
        "tags": "story",
        "hitsPerPage": limit,
        "numericFilters": "created_at_i>0",
    }
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "id": hit["objectID"],
                "title": hit.get("title", ""),
                "url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "score": hit.get("points", 0),
                "by": hit.get("author", ""),
                "time": hit.get("created_at", ""),
                "descendants": hit.get("num_comments", 0),
                "type": "hiring",
            }
            for hit in data.get("hits", [])
        ]
    except Exception as e:
        print(f"  Warning: Hiring search failed: {e}")
        return []


def save_stories(stories: list, output_dir: Path):
    """Save stories to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "hackernews_top.csv"
    fieldnames = ["id", "title", "url", "score", "by", "time", "descendants", "type"]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stories)
    print(f"  Saved {len(stories)} stories to {filepath}")


def append_history(stories: list, output_dir: Path):
    """Append to history CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "hackernews_history.csv"
    fieldnames = ["id", "title", "url", "score", "by", "time", "descendants", "type", "scraped_at"]
    now = datetime.now().isoformat()

    file_exists = filepath.exists()
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for s in stories:
            row = {**s, "scraped_at": now}
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Scrape Hacker News stories")
    parser.add_argument("--limit", type=int, default=30, help="Max top stories (default: 30)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HackerNews Scraper")

    print("  Fetching top stories...")
    top = fetch_top_stories(args.limit)
    print(f"  Got {len(top)} top stories")

    print("  Fetching new stories...")
    new = fetch_new_stories(20)
    print(f"  Got {len(new)} new stories (score >= 5)")

    print("  Fetching hiring threads...")
    hiring = fetch_hiring_threads()
    print(f"  Got {len(hiring)} hiring threads")

    all_stories = top + new + hiring
    save_stories(all_stories, output_dir)
    append_history(all_stories, output_dir)
    print("  Done.")


class HackerNewsScraper:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, limit=30, **kwargs):
        self.limit = limit

    async def run(self, **kwargs):
        print(f"[HackerNewsScraper] Fetching stories...")
        top = fetch_top_stories(self.limit)
        new = fetch_new_stories(20)
        hiring = fetch_hiring_threads()
        all_stories = top + new + hiring
        save_stories(all_stories, OUTPUT_DIR)
        append_history(all_stories, OUTPUT_DIR)
        print(f"  Total: {len(all_stories)} stories")
        return [{"source": "hackernews", "count": len(all_stories)}]


if __name__ == "__main__":
    main()
