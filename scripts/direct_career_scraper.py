#!/usr/bin/env python3
"""
Direct Company Career Page Scraper
Scrapes career pages directly using free httpx + BeautifulSoup.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_DIR = DATA_DIR / "direct_scrapes"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Free scraper headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Direct career page URLs
COMPANY_CAREER_PAGES = {
    # AI/ML companies
    "openai": {
        "url": "https://openai.com/careers/",
        "company": "OpenAI",
        "category": "ai_ml",
        "selector": "a[href*='/careers/']",
    },
    "anthropic": {
        "url": "https://www.anthropic.com/jobs",
        "company": "Anthropic",
        "category": "ai_ml",
        "selector": "a[href*='/jobs/']",
    },
    "huggingface": {
        "url": "https://huggingface.co/careers",
        "company": "Hugging Face",
        "category": "ai_ml",
        "selector": "a[href*='careers']",
    },
    "scale_ai": {
        "url": "https://scale.com/careers",
        "company": "Scale AI",
        "category": "ai_ml",
        "selector": "a[href*='careers']",
    },
    # Dev tools
    "vercel": {
        "url": "https://vercel.com/careers",
        "company": "Vercel",
        "category": "dev_tools",
        "selector": "a[href*='careers']",
    },
    "supabase": {
        "url": "https://supabase.com/careers",
        "company": "Supabase",
        "category": "dev_tools",
        "selector": "a[href*='careers']",
    },
    "planetscale": {
        "url": "https://planetscale.com/careers",
        "company": "PlanetScale",
        "category": "dev_tools",
        "selector": "a[href*='careers']",
    },
    "railway": {
        "url": "https://railway.app/careers",
        "company": "Railway",
        "category": "dev_tools",
        "selector": "a[href*='careers']",
    },
    # Fintech
    "stripe": {
        "url": "https://stripe.com/jobs",
        "company": "Stripe",
        "category": "fintech",
        "selector": "a[href*='/jobs/']",
    },
    "coinbase": {
        "url": "https://www.coinbase.com/careers",
        "company": "Coinbase",
        "category": "fintech",
        "selector": "a[href*='careers']",
    },
    # SaaS
    "linear": {
        "url": "https://linear.app/careers",
        "company": "Linear",
        "category": "saas",
        "selector": "a[href*='careers']",
    },
    "notion": {
        "url": "https://www.notion.so/careers",
        "company": "Notion",
        "category": "saas",
        "selector": "a[href*='careers']",
    },
    "figma": {
        "url": "https://www.figma.com/careers/",
        "company": "Figma",
        "category": "saas",
        "selector": "a[href*='careers']",
    },
    # Remote-first
    "gitlab": {
        "url": "https://about.gitlab.com/jobs/",
        "company": "GitLab",
        "category": "remote",
        "selector": "a[href*='jobs']",
    },
    "automattic": {
        "url": "https://automattic.com/work-with-us/",
        "company": "Automattic",
        "category": "remote",
        "selector": "a[href*='work-with-us']",
    },
    # APAC
    "grab": {
        "url": "https://grab.careers/",
        "company": "Grab",
        "category": "apac",
        "selector": "a[href*='careers']",
    },
    "agoda": {
        "url": "https://careers.agoda.com/",
        "company": "Agoda",
        "category": "apac",
        "selector": "a[href*='careers']",
    },
    "line_man": {
        "url": "https://linecorp.com/en/careers/",
        "company": "LINE",
        "category": "apac",
        "selector": "a[href*='careers']",
    },
    # Big tech
    "cloudflare": {
        "url": "https://www.cloudflare.com/careers/",
        "company": "Cloudflare",
        "category": "big_tech",
        "selector": "a[href*='careers']",
    },
    "datadog": {
        "url": "https://www.datadoghq.com/careers/",
        "company": "Datadog",
        "category": "big_tech",
        "selector": "a[href*='careers']",
    },
}


def scrape_career_page(url, company_name):
    """Scrape a career page using free httpx + BeautifulSoup."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy 1: JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    desc = item.get('description', '')
                    if desc and len(desc) > 100:
                        clean = re.sub(r'<[^>]+>', '\n', desc)
                        clean = re.sub(r'\n{2,}', '\n', clean).strip()
                        if len(clean) > 100:
                            return clean
            except (json.JSONDecodeError, TypeError):
                continue

        # Strategy 2: Next.js __NEXT_DATA__
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            try:
                data = json.loads(next_data.string)
                props = data.get('props', {}).get('pageProps', {})
                for key in ['job', 'position', 'posting', 'jobPosting', 'jobs']:
                    job = props.get(key, {})
                    if job:
                        if isinstance(job, list):
                            # Multiple jobs in array
                            titles = []
                            for j in job:
                                if isinstance(j, dict):
                                    t = j.get('title', '')
                                    if t:
                                        titles.append(t)
                            if titles:
                                return '\n'.join(f'- {t}' for t in titles)
                        elif isinstance(job, dict):
                            desc = job.get('description', '')
                            if desc:
                                clean = re.sub(r'<[^>]+>', '\n', desc)
                                clean = re.sub(r'\n{2,}', '\n', clean).strip()
                                if len(clean) > 100:
                                    return clean
            except (json.JSONDecodeError, TypeError):
                pass

        # Strategy 3: Job containers
        content_selectors = [
            {'class_': re.compile(r'job[_-]?list', re.I)},
            {'class_': re.compile(r'career[_-]?list', re.I)},
            {'class_': re.compile(r'job[_-]?posting', re.I)},
            {'class_': re.compile(r'open[_-]?position', re.I)},
            {'class_': re.compile(r'job[_-]?board', re.I)},
            {'class_': re.compile(r'job[_-]?content', re.I)},
            {'id': re.compile(r'job[_-]?list', re.I)},
            {'id': re.compile(r'career', re.I)},
        ]
        for selector in content_selectors:
            el = soup.find(**selector)
            if el:
                t = el.get_text(separator='\n', strip=True)
                if len(t) > 100:
                    return t

        # Strategy 4: Semantic HTML
        for tag_name in ['article', 'main']:
            tag = soup.find(tag_name)
            if tag:
                t = tag.get_text(separator='\n', strip=True)
                if len(t) > 100:
                    return t

        # Strategy 5: All links that look like job postings
        job_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if text and len(text) > 5 and len(text) < 150:
                if any(kw in href.lower() for kw in ['/job/', '/jobs/', '/position/', '/career/']):
                    job_links.append(f'- [{text}]({href})')
        if job_links:
            return '\n'.join(job_links[:50])

        # Fallback: largest text block
        all_divs = soup.find_all('div')
        best_text = ""
        for div in all_divs:
            t = div.get_text(separator='\n', strip=True)
            if len(t) > len(best_text) and len(t) > 200:
                child_tags = div.find_all(['nav', 'header', 'footer', 'aside'])
                nav_len = sum(len(ct.get_text()) for ct in child_tags)
                if nav_len < len(t) * 0.3:
                    best_text = t
        return best_text

    except Exception as e:
        print(f"  ⚠️  Scrape failed for {company_name}: {e}")
        return None


def parse_jobs_from_markdown(markdown, company_name):
    """Extract job listings from markdown content."""
    jobs = []
    if not markdown:
        return jobs

    lines = markdown.split("\n")
    current_title = None
    current_location = None
    current_url = None

    for line in lines:
        line = line.strip()

        # Look for job titles (common patterns)
        title_patterns = [
            r'^\[(.+?)\]\((https?://.+?/jobs/.+?)\)',  # [Title](url)
            r'^#{2,4}\s+(.+)',  # ## Title
            r'^\*\*(.+?)\*\*',  # **Title**
            r'^[-•]\s+(.+)',  # - Title
        ]

        for pattern in title_patterns:
            match = re.match(pattern, line)
            if match:
                title = match.group(1).strip()
                # Filter: must look like a job title
                if len(title) > 5 and len(title) < 150:
                    if any(kw in title.lower() for kw in [
                        "engineer", "developer", "designer", "manager",
                        "lead", "senior", "staff", "principal", "director",
                        "analyst", "architect", "devops", "frontend",
                        "backend", "full", "product", "data", "ml",
                        "ai", "platform", "infrastructure", "security",
                        "mobile", "ios", "android", "qa", "test",
                    ]):
                        current_title = title
                        if match.lastindex >= 2:
                            current_url = match.group(2)
                break

        # Look for location
        location_patterns = [
            r'(?:location|based in|remote|hybrid|onsite)[:\s]+(.+)',
            r'\b(remote|hybrid|onsite)\b',
            r'(?:bangkok|san francisco|new york|london|berlin|singapore|tokyo)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match and current_title:
                current_location = match.group(0) if match.lastindex else line.strip()
                break

        # If we have a title, save it
        if current_title:
            job = {
                "title": current_title,
                "company": company_name,
                "location": current_location or "Not specified",
                "url": current_url or "",
                "source": "direct_scrape",
                "scraped_at": datetime.now().isoformat(),
            }
            # Avoid duplicates
            if not any(j["title"] == job["title"] for j in jobs):
                jobs.append(job)
            current_title = None
            current_location = None
            current_url = None

    return jobs


def scrape_company(key, config):
    """Scrape a single company's career page."""
    company = config["company"]
    url = config["url"]
    print(f"  🔍 Scraping {company} ({url})...")

    markdown = scrape_career_page(url, company)
    if not markdown:
        return []

    jobs = parse_jobs_from_markdown(markdown, company)
    print(f"     Found {len(jobs)} positions")
    return jobs


def scrape_all(categories=None):
    """Scrape all configured career pages."""
    all_jobs = []
    companies = COMPANY_CAREER_PAGES

    if categories:
        companies = {k: v for k, v in companies.items() if v["category"] in categories}

    print(f"\n🔍 Scraping {len(companies)} company career pages...")
    print("=" * 60)

    for key, config in companies.items():
        jobs = scrape_company(key, config)
        for j in jobs:
            j["category"] = config["category"]
        all_jobs.extend(jobs)

    return all_jobs


def save_jobs(jobs):
    """Save scraped jobs to CSV."""
    if not jobs:
        print("\n⚠️  No jobs found to save.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = OUTPUT_DIR / f"direct_scrape_{timestamp}.csv"

    fieldnames = ["title", "company", "location", "url", "category", "source", "scraped_at"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    print(f"\n💾 Saved {len(jobs)} jobs to {filepath}")
    return filepath


def list_companies():
    """List all configured company career pages."""
    print(f"\n🏢 Configured Career Pages ({len(COMPANY_CAREER_PAGES)} companies)")
    print("=" * 60)

    categories = {}
    for key, config in COMPANY_CAREER_PAGES.items():
        cat = config["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((config["company"], config["url"]))

    for cat, companies in sorted(categories.items()):
        print(f"\n  📁 {cat.upper()} ({len(companies)})")
        for name, url in companies:
            print(f"     {name}: {url}")

    print(f"\n{'=' * 60}")
    print(f"  Total: {len(COMPANY_CAREER_PAGES)} companies")


def main():
    parser = argparse.ArgumentParser(description="Direct Company Career Page Scraper")
    parser.add_argument("--scrape", action="store_true", help="Scrape all career pages")
    parser.add_argument("--company", type=str, help="Scrape specific company")
    parser.add_argument("--category", type=str, help="Scrape by category")
    parser.add_argument("--list", action="store_true", help="List configured pages")
    parser.add_argument("--save", action="store_true", help="Save results to CSV")
    parser.add_argument("--stats", action="store_true", help="Show scrape stats")
    args = parser.parse_args()

    if args.list:
        list_companies()
        return

    if args.stats:
        files = list(OUTPUT_DIR.glob("*.csv"))
        total = 0
        print(f"\n📊 Direct Scrape Stats")
        print(f"{'=' * 50}")
        for f in sorted(files):
            with open(f) as fh:
                count = sum(1 for _ in fh) - 1
            total += count
            print(f"  {f.name}: {count} jobs")
        print(f"{'=' * 50}")
        print(f"  Total jobs found: {total}")
        print(f"  Files: {len(files)}")
        return

    if args.scrape or args.company or args.category:
        categories = None
        if args.category:
            categories = [args.category]

        if args.company:
            key = args.company.lower()
            if key in COMPANY_CAREER_PAGES:
                jobs = scrape_company(key, COMPANY_CAREER_PAGES[key])
            else:
                print(f"❌ Company '{args.company}' not found. Use --list to see options.")
                return
        else:
            jobs = scrape_all(categories)

        if jobs and args.save:
            save_jobs(jobs)
        elif jobs:
            print(f"\n📋 Found {len(jobs)} positions (use --save to export)")
            for j in jobs[:20]:
                print(f"  • {j['title']} @ {j['company']} ({j['location']})")
            if len(jobs) > 20:
                print(f"  ... and {len(jobs) - 20} more")
        else:
            print("\n⚠️  No positions found")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
