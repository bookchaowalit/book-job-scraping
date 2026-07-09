#!/usr/bin/env python3
"""
Scrape GitHub trending repositories and detect tech opportunities.
Uses GitHub Search API to find fast-rising repos by stars.

Outputs:
    - book-scraping/data/exported/github_trending.csv (latest trending)
    - book-scraping/data/exported/github_trending_history.csv (appended daily)

Usage:
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_github_trending.py
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_github_trending.py --languages python,javascript,typescript
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_github_trending.py --since weekly
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_github_trending.py --min-stars 100
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip install httpx")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[4]  # solo-empire/
OUTPUT_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data" / "exported"

GITHUB_API = "https://api.github.com"

DEFAULT_LANGUAGES = ["python", "javascript", "typescript", "rust", "go"]
DEFAULT_MIN_STARS = 50


def get_github_token() -> str:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN", "")


def search_trending(language: str, since_days: int, min_stars: int, per_page: int = 30) -> list:
    """Search for repos created recently with high star count."""
    token = get_github_token()
    date_threshold = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")

    query = f"language:{language} created:>{date_threshold} stars:>={min_stars}"
    url = f"{GITHUB_API}/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    repos = []
    for item in data.get("items", []):
        repos.append({
            "name": item["full_name"],
            "url": item["html_url"],
            "description": (item.get("description") or "")[:200],
            "language": item.get("language", ""),
            "stars": item["stargazers_count"],
            "forks": item["forks_count"],
            "open_issues": item["open_issues_count"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "topics": ",".join(item.get("topics", [])),
            "owner": item["owner"]["login"],
            "license": (item.get("license") or {}).get("spdx_id", ""),
        })

    return repos


def detect_opportunities(repos: list, keywords: list) -> list:
    """Detect repos matching business opportunity keywords."""
    opportunities = []
    keyword_set = {k.lower() for k in keywords}

    for repo in repos:
        text = f"{repo['description']} {repo['topics']} {repo['name']}".lower()
        matched = [k for k in keyword_set if k in text]
        if matched:
            repo["matched_keywords"] = ",".join(matched)
            opportunities.append(repo)

    return opportunities


def save_trending(repos: list, output_dir: Path, language: str = ""):
    """Save trending repos to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trending_file = output_dir / "github_trending.csv"
    file_exists = trending_file.exists()

    fieldnames = [
        "scraped_at", "name", "owner", "url", "description", "language",
        "stars", "forks", "open_issues", "created_at", "updated_at",
        "topics", "license"
    ]

    rows = []
    for repo in repos:
        rows.append({
            "scraped_at": now,
            "name": repo["name"],
            "owner": repo["owner"],
            "url": repo["url"],
            "description": repo["description"],
            "language": repo["language"],
            "stars": repo["stars"],
            "forks": repo["forks"],
            "open_issues": repo["open_issues"],
            "created_at": repo["created_at"],
            "updated_at": repo["updated_at"],
            "topics": repo["topics"],
            "license": repo["license"],
        })

    with open(trending_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"  Appended {len(rows)} repos to {trending_file}")


def append_history(repos: list, output_dir: Path):
    """Append star count history for tracking growth."""
    history_file = output_dir / "github_trending_history.csv"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = history_file.exists()

    fieldnames = ["date", "name", "language", "stars", "forks"]
    rows = []
    for repo in repos:
        rows.append({
            "date": now,
            "name": repo["name"],
            "language": repo["language"],
            "stars": repo["stars"],
            "forks": repo["forks"],
        })

    with open(history_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"  Appended {len(rows)} rows to {history_file}")


def print_summary(repos: list, language: str, opportunities: list = None):
    """Print trending summary."""
    print(f"\n  Top trending ({language or 'all'}):")
    for repo in repos[:10]:
        print(f"    {repo['stars']:>5} stars | {repo['name']:<40} | {repo['description'][:50]}")

    if opportunities:
        print(f"\n  OPPORTUNITIES ({len(opportunities)}):")
        for opp in opportunities[:5]:
            print(f"    {opp['stars']:>5} stars | {opp['matched_keywords']:<20} | {opp['name']}")


def main():
    parser = argparse.ArgumentParser(description="Scrape GitHub trending repositories")
    parser.add_argument("--languages", default=",".join(DEFAULT_LANGUAGES),
                        help="Comma-separated languages to track")
    parser.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"],
                        help="Time window: daily (7d), weekly (30d), monthly (90d)")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS,
                        help=f"Minimum stars threshold (default: {DEFAULT_MIN_STARS})")
    parser.add_argument("--keywords", default="ai,agent,saas,api,tool,framework,library,scraper,bot",
                        help="Keywords for opportunity detection")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR),
                        help="Output directory")
    args = parser.parse_args()

    languages = [l.strip() for l in args.languages.split(",")]
    keywords = [k.strip() for k in args.keywords.split(",")]
    output_dir = Path(args.output_dir)

    since_map = {"daily": 7, "weekly": 30, "monthly": 90}
    since_days = since_map[args.since]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] GitHub Trending Scraper")
    print(f"  Languages: {languages} | Since: {args.since} ({since_days}d) | Min stars: {args.min_stars}")

    all_repos = []
    all_opportunities = []

    for lang in languages:
        print(f"\n  Fetching {lang}...")
        try:
            repos = search_trending(lang, since_days, args.min_stars)
            print(f"    Found {len(repos)} repos")
            all_repos.extend(repos)

            opps = detect_opportunities(repos, keywords)
            if opps:
                all_opportunities.extend(opps)
                print(f"    {len(opps)} opportunities detected")

        except Exception as e:
            print(f"    Error: {e}")

    if all_repos:
        # Sort by stars
        all_repos.sort(key=lambda x: x["stars"], reverse=True)

        save_trending(all_repos, output_dir)
        append_history(all_repos, output_dir)

        # Print top per language
        for lang in languages:
            lang_repos = [r for r in all_repos if r["language"].lower() == lang.lower()]
            if lang_repos:
                print_summary(lang_repos[:5], lang, [o for o in all_opportunities if o["language"].lower() == lang.lower()])

    print(f"\n  Total: {len(all_repos)} repos, {len(all_opportunities)} opportunities")
    print("  Done.")


class GitHubTrendingScraper:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, languages=None, since='daily', min_stars=None, keywords=None, **kwargs):
        self.languages = languages or DEFAULT_LANGUAGES
        self.min_stars = min_stars or DEFAULT_MIN_STARS
        self.keywords = keywords or ['ai', 'agent', 'saas', 'api', 'tool', 'framework', 'scraper', 'bot']
        since_map = {'daily': 7, 'weekly': 30, 'monthly': 90}
        self.since_days = since_map.get(since, 7)

    async def run(self, **kwargs):
        print(f"[GitHubTrendingScraper] Languages: {self.languages}")
        all_repos = []
        all_opportunities = []
        for lang in self.languages:
            try:
                repos = search_trending(lang, self.since_days, self.min_stars)
                all_repos.extend(repos)
                opps = detect_opportunities(repos, self.keywords)
                all_opportunities.extend(opps)
            except Exception as e:
                print(f"  Error fetching {lang}: {e}")
        if all_repos:
            all_repos.sort(key=lambda x: x['stars'], reverse=True)
            save_trending(all_repos, OUTPUT_DIR)
            append_history(all_repos, OUTPUT_DIR)
        return [{"source": "github_trending", "count": len(all_repos), "opportunities": len(all_opportunities)}]


if __name__ == "__main__":
    main()
