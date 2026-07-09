#!/usr/bin/env python3
"""
Scrape visa sponsorship job postings from specialized boards.

Targets:
- Relocate.me (relocation + visa sponsorship)
- Jobgether (visa sponsorship filter)
- VanHack (tech jobs with visa sponsorship)

Outputs:
- Adds to apply_tracker.csv with 'visa_sponsorship' source tag
- Extracts company names for contact matching

Usage:
    python3 scripts/scrape_visa_sponsorship_jobs.py
    python3 scripts/scrape_visa_sponsorship_jobs.py --apply
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def load_tracker():
    """Load existing tracker to avoid duplicates."""
    if not TRACKER_FILE.exists():
        return []
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_tracker(rows):
    """Save tracker rows."""
    fieldnames = ["url", "title", "company", "status", "note", "updated_at",
                  "work_type", "visa_sponsor", "job_type", "experience_level", "country"]
    with open(TRACKER_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def scrape_relocate_me():
    """Scrape relocate.me for relocation + visa sponsorship jobs."""
    print("Scraping relocate.me...")
    jobs = []
    
    try:
        # relocate.me has a public API
        url = "https://relocate.me/api/job/search?keywords=software+engineer&page=1&sort=recent"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for job in data.get("data", [])[:30]:
                title = job.get("position", "")
                company = job.get("company", "")
                job_url = f"https://relocate.me/relocation-jobs/{job.get('id', '')}"
                
                jobs.append({
                    "url": job_url,
                    "title": f"{title} [visa sponsorship]",
                    "company": company,
                    "status": "discovered",
                    "note": f"Source: relocate.me | Relocation + visa sponsorship",
                    "updated_at": datetime.now().isoformat()[:19]
                })
        print(f"  Found {len(jobs)} jobs from relocate.me")
    except Exception as e:
        print(f"  Error scraping relocate.me: {e}")
    
    return jobs


def scrape_jobgether():
    """Scrape Jobgether for visa sponsorship jobs."""
    print("Scraping Jobgether...")
    jobs = []
    
    try:
        # Jobgether API endpoint
        url = "https://jobgether.com/api/jobs?search=visa+sponsorship&location=remote&page=1"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for job in data.get("jobs", [])[:30]:
                title = job.get("title", "")
                company = job.get("company", {}).get("name", "")
                job_url = f"https://jobgether.com/jobs/{job.get('id', '')}"
                
                jobs.append({
                    "url": job_url,
                    "title": f"{title} [visa sponsorship]",
                    "company": company,
                    "status": "discovered",
                    "note": f"Source: Jobgether | Visa sponsorship available",
                    "updated_at": datetime.now().isoformat()[:19]
                })
        print(f"  Found {len(jobs)} jobs from Jobgether")
    except Exception as e:
        print(f"  Error scraping Jobgether: {e}")
    
    return jobs


def scrape_vanhack():
    """Scrape VanHack for tech jobs with visa sponsorship."""
    print("Scraping VanHack...")
    jobs = []
    
    try:
        # VanHack public jobs page
        url = "https://www.vanhack.com/jobs"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look for job cards
            job_cards = soup.find_all("div", class_=re.compile(r"job-card|job-listing", re.I))
            for card in job_cards[:20]:
                title_elem = card.find(["h2", "h3", "a"], class_=re.compile(r"title|job-title", re.I))
                company_elem = card.find(["div", "span", "p"], class_=re.compile(r"company", re.I))
                link_elem = card.find("a", href=True)
                
                if title_elem and company_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True)
                    job_url = link_elem["href"]
                    if not job_url.startswith("http"):
                        job_url = f"https://www.vanhack.com{job_url}"
                    
                    jobs.append({
                        "url": job_url,
                        "title": f"{title} [visa sponsorship]",
                        "company": company,
                        "status": "discovered",
                        "note": f"Source: VanHack | Tech job with visa sponsorship",
                        "updated_at": datetime.now().isoformat()[:19]
                    })
        print(f"  Found {len(jobs)} jobs from VanHack")
    except Exception as e:
        print(f"  Error scraping VanHack: {e}")
    
    return jobs


def scrape_linkedin_visa():
    """Scrape LinkedIn for visa sponsorship jobs (limited without auth)."""
    print("Scraping LinkedIn (limited)...")
    jobs = []
    
    try:
        # LinkedIn public search (limited results without auth)
        url = "https://www.linkedin.com/jobs/search?keywords=visa%20sponsorship%20software%20engineer&location=Worldwide"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look for job cards in public view
            job_cards = soup.find_all("div", class_="base-card")
            for card in job_cards[:15]:
                title_elem = card.find("h3", class_="base-search-card__title")
                company_elem = card.find("h4", class_="base-search-card__subtitle")
                link_elem = card.find("a", class_="base-card__full-link", href=True)
                
                if title_elem and company_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True)
                    job_url = link_elem["href"].split("?")[0]
                    
                    jobs.append({
                        "url": job_url,
                        "title": f"{title} [visa sponsorship]",
                        "company": company,
                        "status": "discovered",
                        "note": f"Source: LinkedIn | Visa sponsorship keyword",
                        "updated_at": datetime.now().isoformat()[:19]
                    })
        print(f"  Found {len(jobs)} jobs from LinkedIn")
    except Exception as e:
        print(f"  Error scraping LinkedIn: {e}")
    
    return jobs


def main():
    parser = argparse.ArgumentParser(description="Scrape visa sponsorship jobs")
    parser.add_argument("--apply", action="store_true", help="Add jobs to tracker")
    args = parser.parse_args()
    
    print("=" * 70)
    print("  VISA SPONSORSHIP JOB SCRAPER")
    print("=" * 70)
    
    # Load existing tracker
    existing = load_tracker()
    existing_urls = {r.get("url") for r in existing}
    print(f"Existing tracker: {len(existing)} rows")
    
    # Scrape all sources
    all_jobs = []
    all_jobs.extend(scrape_relocate_me())
    all_jobs.extend(scrape_jobgether())
    all_jobs.extend(scrape_vanhack())
    all_jobs.extend(scrape_linkedin_visa())
    
    # Deduplicate
    new_jobs = []
    for job in all_jobs:
        if job["url"] not in existing_urls:
            new_jobs.append(job)
            existing_urls.add(job["url"])
    
    print(f"\nNew jobs found: {len(new_jobs)}")
    
    if args.apply and new_jobs:
        existing.extend(new_jobs)
        save_tracker(existing)
        print(f"✓ Added {len(new_jobs)} jobs to tracker")
        print(f"  Total tracker rows: {len(existing)}")
    else:
        print("\nDRY RUN - Use --apply to add jobs to tracker")
        if new_jobs:
            print("\nSample jobs:")
            for job in new_jobs[:5]:
                print(f"  {job['company']} | {job['title'][:50]}")
                print(f"    {job['url']}")


if __name__ == "__main__":
    main()
