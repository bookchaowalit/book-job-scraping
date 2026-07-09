#!/usr/bin/env python3
"""
RSS Feed Aggregator — Scrape 50+ tech company career pages via RSS/Atom feeds.
Converts feed items to pipeline-compatible job format.

Usage:
    python rss_aggregator.py --fetch
    python rss_aggregator.py --fetch --company google
    python rss_aggregator.py --list-feeds
    python rss_aggregator.py --add-feed --name "Company" --url "https://..."
    python rss_aggregator.py --stats
"""

import argparse
import csv
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
RSS_DIR = DATA_DIR / "rss_feeds"
FEEDS_CONFIG = DATA_DIR / "rss_feeds_config.json"

# 50+ Tech Company Career Page RSS Feeds
DEFAULT_FEEDS = [
    # Big Tech
    {"name": "Google", "url": "https://careers.google.com/api/v3/search/jobs/?format=json", "category": "big_tech"},
    {"name": "Meta", "url": "https://www.metacareers.com/jobs/feed", "category": "big_tech"},
    {"name": "Amazon", "url": "https://www.amazon.jobs/en/search.rss", "category": "big_tech"},
    {"name": "Microsoft", "url": "https://careers.microsoft.com/us/en/api/feed", "category": "big_tech"},
    {"name": "Apple", "url": "https://jobs.apple.com/en-us/feed", "category": "big_tech"},

    # Cloud/SaaS
    {"name": "Salesforce", "url": "https://careers.salesforce.com/en/jobs/feed/", "category": "saas"},
    {"name": "Oracle", "url": "https://oracle.taleo.net/careersection/rest/jobboard/searchrss", "category": "saas"},
    {"name": "SAP", "url": "https://www.sap.com/jobs/feed", "category": "saas"},
    {"name": "Adobe", "url": "https://adobe.wd5.myworkdayjobs.com/en_US/external/rss", "category": "saas"},
    {"name": "Atlassian", "url": "https://www.atlassian.com/company/careers/rss", "category": "saas"},
    {"name": "HubSpot", "url": "https://www.hubspot.com/careers/rss", "category": "saas"},
    {"name": "Slack", "url": "https://slack.com/intl/en-jp/careers/rss", "category": "saas"},

    # Fintech
    {"name": "Stripe", "url": "https://stripe.com/jobs/rss", "category": "fintech"},
    {"name": "Square", "url": "https://careers.squareup.com/us/en/rss", "category": "fintech"},
    {"name": "PayPal", "url": "https://paypal.eightfold.ai/api/feed", "category": "fintech"},
    {"name": "Coinbase", "url": "https://www.coinbase.com/careers/rss", "category": "fintech"},

    # Startups/Scaleups
    {"name": "Airbnb", "url": "https://careers.airbnb.com/jobs/feed/", "category": "startup"},
    {"name": "Spotify", "url": "https://www.spotifyjobs.com/en/feed/", "category": "startup"},
    {"name": "Netflix", "url": "https://jobs.netflix.com/rss", "category": "startup"},
    {"name": "Uber", "url": "https://www.uber.com/careers/rss", "category": "startup"},
    {"name": "Lyft", "url": "https://www.lyft.com/careers/rss", "category": "startup"},
    {"name": "DoorDash", "url": "https://careers.doordash.com/rss", "category": "startup"},
    {"name": "Shopify", "url": "https://www.shopify.com/careers/feed", "category": "startup"},

    # Developer Tools
    {"name": "GitHub", "url": "https://github.com/about/careers/rss", "category": "dev_tools"},
    {"name": "GitLab", "url": "https://about.gitlab.com/jobs/rss", "category": "dev_tools"},
    {"name": "HashiCorp", "url": "https://www.hashicorp.com/careers/rss", "category": "dev_tools"},
    {"name": "Datadog", "url": "https://www.datadoghq.com/careers/rss", "category": "dev_tools"},
    {"name": "MongoDB", "url": "https://www.mongodb.com/careers/rss", "category": "dev_tools"},
    {"name": "Elastic", "url": "https://www.elastic.co/about/careers/rss", "category": "dev_tools"},
    {"name": "Confluent", "url": "https://www.confluent.io/careers/rss", "category": "dev_tools"},

    # AI/ML
    {"name": "OpenAI", "url": "https://openai.com/careers/rss", "category": "ai_ml"},
    {"name": "Anthropic", "url": "https://www.anthropic.com/jobs/rss", "category": "ai_ml"},
    {"name": "DeepMind", "url": "https://deepmind.google/about/rss", "category": "ai_ml"},
    {"name": "Hugging Face", "url": "https://huggingface.co/careers/rss", "category": "ai_ml"},
    {"name": "Scale AI", "url": "https://scale.com/careers/rss", "category": "ai_ml"},

    # Remote-First
    {"name": "Automattic", "url": "https://automattic.com/work-with-us/feed/", "category": "remote"},
    {"name": "Zapier", "url": "https://zapier.com/jobs/rss", "category": "remote"},
    {"name": "Buffer", "url": "https://buffer.com/jobs/rss", "category": "remote"},
    {"name": "Basecamp", "url": "https://basecamp.com/careers/rss", "category": "remote"},
    {"name": "GitLab", "url": "https://about.gitlab.com/jobs/rss", "category": "remote"},

    # Enterprise
    {"name": "IBM", "url": "https://www.ibm.com/careers/rss", "category": "enterprise"},
    {"name": "Intel", "url": "https://jobs.intel.com/en/rss", "category": "enterprise"},
    {"name": "Cisco", "url": "https://www.cisco.com/c/en/us/about/careers/rss.html", "category": "enterprise"},
    {"name": "Dell", "url": "https://jobs.dell.com/en/rss", "category": "enterprise"},
    {"name": "HP", "url": "https://jobs.hp.com/en-us/rss", "category": "enterprise"},

    # Asia-Pacific
    {"name": "Grab", "url": "https://careers.grab.com/rss", "category": "apac"},
    {"name": "Sea Group", "url": "https://careers.seagroup.com/rss", "category": "apac"},
    {"name": "Tokopedia", "url": "https://www.tokopedia.com/careers/rss", "category": "apac"},
    {"name": "LINE", "url": "https://careers.line.com/rss", "category": "apac"},
    {"name": "Rakuten", "url": "https://global.rakuten.com/corp/careers/rss", "category": "apac"},
    {"name": "Agoda", "url": "https://careers.agoda.com/rss", "category": "apac"},

    # Consulting/Services
    {"name": "Accenture", "url": "https://www.accenture.com/us-en/careers/rss", "category": "consulting"},
    {"name": "McKinsey", "url": "https://www.mckinsey.com/careers/rss", "category": "consulting"},
]


def load_feeds_config():
    """Load feeds configuration."""
    if FEEDS_CONFIG.exists():
        return json.loads(FEEDS_CONFIG.read_text())
    return {"feeds": DEFAULT_FEEDS, "updated_at": None}


def save_feeds_config(config):
    """Save feeds configuration."""
    FEEDS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config["updated_at"] = datetime.now().isoformat()
    FEEDS_CONFIG.write_text(json.dumps(config, indent=2))


def fetch_feed(feed_info, max_items=20):
    """Fetch and parse a single RSS feed."""
    url = feed_info["url"]
    name = feed_info["name"]

    if not HAS_REQUESTS:
        return []

    try:
        headers = {"User-Agent": "SoloEmpire-RSS-Aggregator/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        if HAS_FEEDPARSER:
            parsed = feedparser.parse(resp.content)
            items = []
            for entry in parsed.entries[:max_items]:
                items.append({
                    "title": entry.get("title", ""),
                    "company": name,
                    "url": entry.get("link", entry.get("url", "")),
                    "description": (entry.get("summary", "") or entry.get("description", ""))[:500],
                    "location": entry.get("location", "Remote"),
                    "published": entry.get("published", ""),
                    "board": f"rss-{feed_info.get('category', 'unknown')}",
                    "source": "rss",
                })
            return items
        else:
            # Basic XML parsing fallback
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            items = []
            for item in root.iter("item") if "rss" in resp.text[:200].lower() else root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                link = item.findtext("link") or ""
                if not link:
                    link_el = item.find("{http://www.w3.org/2005/Atom}link")
                    link = link_el.get("href", "") if link_el is not None else ""
                desc = item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or ""
                if title:
                    items.append({
                        "title": title, "company": name, "url": link,
                        "description": desc[:500], "location": "Remote",
                        "board": f"rss-{feed_info.get('category', 'unknown')}", "source": "rss",
                    })
                if len(items) >= max_items:
                    break
            return items

    except Exception as e:
        print(f"  Error fetching {name}: {e}")
        return []


def fetch_all_feeds(company_filter=None, category_filter=None):
    """Fetch all configured RSS feeds."""
    config = load_feeds_config()
    feeds = config.get("feeds", DEFAULT_FEEDS)

    if company_filter:
        feeds = [f for f in feeds if company_filter.lower() in f["name"].lower()]
    if category_filter:
        feeds = [f for f in feeds if f.get("category", "") == category_filter]

    RSS_DIR.mkdir(parents=True, exist_ok=True)
    all_jobs = []
    results = {"fetched": 0, "success": 0, "failed": 0, "total_jobs": 0}

    print(f"Fetching {len(feeds)} RSS feeds...\n")

    for i, feed in enumerate(feeds):
        print(f"  [{i+1}/{len(feeds)}] {feed['name']}...", end=" ")
        results["fetched"] += 1

        items = fetch_feed(feed)
        if items:
            all_jobs.extend(items)
            results["success"] += 1
            results["total_jobs"] += len(items)
            print(f"{len(items)} jobs")
        else:
            results["failed"] += 1
            print("no results")

        # Rate limiting
        time.sleep(0.5)

    # Deduplicate
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            job["id"] = hashlib.md5(url.encode()).hexdigest()[:16]
            unique_jobs.append(job)

    # Save to CSV
    if unique_jobs:
        output_file = RSS_DIR / f"rss_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "company", "url", "description", "location", "board", "source", "published"])
            writer.writeheader()
            for job in unique_jobs:
                writer.writerow({k: job.get(k, "") for k in writer.fieldnames})
        print(f"\nSaved {len(unique_jobs)} jobs to {output_file}")

    # Save summary
    summary_file = RSS_DIR / "latest_summary.json"
    summary_file.write_text(json.dumps({
        **results, "unique_jobs": len(unique_jobs),
        "fetched_at": datetime.now().isoformat(),
    }, indent=2))

    print(f"\nResults: {results['success']} feeds OK, {results['failed']} failed, {len(unique_jobs)} unique jobs")
    return unique_jobs


def list_feeds():
    """List all configured feeds."""
    config = load_feeds_config()
    feeds = config.get("feeds", DEFAULT_FEEDS)

    categories = {}
    for feed in feeds:
        cat = feed.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(feed)

    print(f"\n{'='*60}")
    print(f"RSS FEED CONFIGURATION — {len(feeds)} feeds")
    print(f"{'='*60}")

    for cat, cat_feeds in sorted(categories.items()):
        print(f"\n📁 {cat.upper()} ({len(cat_feeds)} feeds)")
        for feed in cat_feeds:
            print(f"  • {feed['name']:<20} {feed['url'][:50]}")


def add_feed(name, url, category="other"):
    """Add a new feed."""
    config = load_feeds_config()
    feeds = config.get("feeds", DEFAULT_FEEDS)

    # Check for duplicates
    for f in feeds:
        if f["name"].lower() == name.lower():
            print(f"Feed '{name}' already exists.")
            return

    feeds.append({"name": name, "url": url, "category": category})
    config["feeds"] = feeds
    save_feeds_config(config)
    print(f"Added feed: {name} ({category})")


def show_stats():
    """Show RSS aggregation stats."""
    if not RSS_DIR.exists():
        print("No RSS data yet. Run --fetch first.")
        return

    summary_file = RSS_DIR / "latest_summary.json"
    if summary_file.exists():
        summary = json.loads(summary_file.read_text())
        print(f"\n📊 RSS AGGREGATION STATS")
        print(f"  Last fetch: {summary.get('fetched_at', 'N/A')[:19]}")
        print(f"  Feeds fetched: {summary.get('fetched', 0)}")
        print(f"  Successful: {summary.get('success', 0)}")
        print(f"  Failed: {summary.get('failed', 0)}")
        print(f"  Total jobs: {summary.get('total_jobs', 0)}")
        print(f"  Unique jobs: {summary.get('unique_jobs', 0)}")

    # Count CSV files
    csv_files = list(RSS_DIR.glob("rss_jobs_*.csv"))
    print(f"  Historical fetches: {len(csv_files)}")


def main():
    parser = argparse.ArgumentParser(description="RSS Feed Aggregator")
    parser.add_argument("--fetch", action="store_true", help="Fetch all feeds")
    parser.add_argument("--company", help="Filter by company name")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--list-feeds", action="store_true", help="List configured feeds")
    parser.add_argument("--add-feed", action="store_true", help="Add new feed")
    parser.add_argument("--name", help="Feed name")
    parser.add_argument("--url", help="Feed URL")
    parser.add_argument("--category-name", default="other", help="Feed category")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()

    if args.list_feeds:
        list_feeds()
    elif args.fetch:
        fetch_all_feeds(args.company, args.category)
    elif args.add_feed:
        if not args.name or not args.url:
            print("Error: --name and --url required")
            return
        add_feed(args.name, args.url, args.category_name)
    elif args.stats:
        show_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
