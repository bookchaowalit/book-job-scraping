#!/usr/bin/env python3
"""
Job Description Deep-Scraper - Fetches full job descriptions for top matched jobs.
Stores descriptions for AI resume tailoring and detailed analysis.

Usage:
    python3 scrape_job_descriptions.py
    python3 scrape_job_descriptions.py --top 10
    python3 scrape_job_descriptions.py --url "https://example.com/job/123"
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
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

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
DESCRIPTIONS_DIR = DATA_DIR / "job_descriptions"
DESCRIPTIONS_CSV = DATA_DIR / "job_descriptions.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def extract_from_json_ld(soup: BeautifulSoup) -> str:
    """Extract job description from JSON-LD structured data."""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            # Handle single object or list
            items = data if isinstance(data, list) else [data]
            for item in items:
                desc = item.get('description', '')
                if desc and len(desc) > 100:
                    # Clean HTML tags from JSON-LD description
                    clean = re.sub(r'<[^>]+>', '\n', desc)
                    clean = re.sub(r'\n{2,}', '\n', clean).strip()
                    if len(clean) > 100:
                        return clean
        except (json.JSONDecodeError, TypeError):
            continue
    return ""


def extract_from_next_data(soup: BeautifulSoup) -> str:
    """Extract job description from Next.js __NEXT_DATA__."""
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return ""
    try:
        data = json.loads(next_data.string)
        props = data.get('props', {}).get('pageProps', {})
        # Try various key names
        for key in ['job', 'position', 'posting', 'jobPosting']:
            job = props.get(key, {})
            if job and isinstance(job, dict):
                desc = job.get('description', '')
                if desc:
                    clean = re.sub(r'<[^>]+>', '\n', desc)
                    clean = re.sub(r'\n{2,}', '\n', clean).strip()
                    if len(clean) > 100:
                        return clean
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def get_top_jobs(top_n: int = 10) -> list:
    """Get top N jobs from matched_jobs.csv."""
    if not MATCHED_CSV.exists():
        print(f"ERROR: {MATCHED_CSV} not found")
        return []
    
    jobs = []
    with open(MATCHED_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    
    # Sort by score (descending)
    jobs.sort(key=lambda x: float(x.get("_score", 0)), reverse=True)
    return jobs[:top_n]


def scrape_job_description(url: str) -> dict:
    """Scrape full job description from URL using BeautifulSoup."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title
        page_title = ""
        title_tag = soup.find('title')
        if title_tag:
            page_title = title_tag.get_text(strip=True)
        
        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': re.compile(r'description', re.I)})
        if meta_tag:
            meta_desc = meta_tag.get('content', '').strip()
        
        # Extract main content using multiple strategies (best first)
        description = ""
        
        # Strategy 1: JSON-LD structured data (most reliable)
        description = extract_from_json_ld(soup)
        
        # Strategy 2: Next.js __NEXT_DATA__
        if not description:
            description = extract_from_next_data(soup)
        
        # Strategy 3: Look for job description containers by class/id
        if not description:
            content_selectors = [
                {'class_': re.compile(r'job[_-]?description', re.I)},
                {'class_': re.compile(r'job[_-]?detail', re.I)},
                {'class_': re.compile(r'job[_-]?content', re.I)},
                {'class_': re.compile(r'job[_-]?posting', re.I)},
                {'class_': re.compile(r'description', re.I)},
                {'class_': re.compile(r'content[_-]?body', re.I)},
                {'id': re.compile(r'job[_-]?description', re.I)},
                {'id': re.compile(r'job[_-]?detail', re.I)},
            ]
            
            for selector in content_selectors:
                el = soup.find(**selector)
                if el:
                    text = el.get_text(separator='\n', strip=True)
                    if len(text) > 100:
                        description = text
                        break
        
        # Strategy 4: Try semantic HTML tags
        if not description:
            for tag_name in ['article', 'main']:
                tag = soup.find(tag_name)
                if tag:
                    text = tag.get_text(separator='\n', strip=True)
                    if len(text) > 100:
                        description = text
                        break
        
        # Strategy 5: Find the largest text block on the page
        if not description:
            all_divs = soup.find_all('div')
            best_text = ""
            for div in all_divs:
                text = div.get_text(separator='\n', strip=True)
                if len(text) > len(best_text) and len(text) > 200:
                    child_tags = div.find_all(['nav', 'header', 'footer', 'aside'])
                    nav_text_len = sum(len(ct.get_text()) for ct in child_tags)
                    if nav_text_len < len(text) * 0.3:
                        best_text = text
            if best_text:
                description = best_text
        
        # Fallback to meta description
        if not description and meta_desc:
            description = meta_desc
        
        # Clean up - limit whitespace
        if description:
            description = re.sub(r'\n{3,}', '\n\n', description)
            description = description[:5000]
        
        # Extract skills/keywords from description
        skills = extract_skills(description)
        
        return {
            "url": url,
            "page_title": page_title,
            "description": description,
            "skills": skills,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "success",
        }
    except Exception as e:
        return {
            "url": url,
            "description": "",
            "skills": [],
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": f"error: {str(e)[:100]}",
        }


def extract_skills(text: str) -> list:
    """Extract skills from job description text."""
    text_lower = text.lower()
    skills = set()
    
    skill_patterns = [
        r'\b(python|javascript|typescript|java|golang|rust|ruby|php|c\+\+|c#)\b',
        r'\b(react|vue|angular|svelte|next\.?js|nuxt)\b',
        r'\b(node\.?js|express|nestjs|django|flask|fastapi|spring|rails|laravel)\b',
        r'\b(postgresql|mysql|mongodb|redis|elasticsearch|dynamodb)\b',
        r'\b(aws|gcp|azure|docker|kubernetes|terraform)\b',
        r'\b(ai|machine learning|deep learning|tensorflow|pytorch|openai|llm|nlp)\b',
        r'\b(rest|graphql|api|microservices)\b',
        r'\b(git|agile|scrum|ci/cd|devops)\b',
        r'\b(tailwind|css|html|webpack|vite)\b',
        r'\b(jest|pytest|mocha|cypress|selenium|testing)\b',
        r'\b(rabbitmq|kafka|celery|redis)\b',
        r'\b(linux|unix|bash|shell)\b',
    ]
    
    for pattern in skill_patterns:
        matches = re.findall(pattern, text_lower)
        skills.update(matches)
    
    return list(skills)


def save_description(desc_data: dict):
    """Save description to CSV."""
    DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    fieldnames = ["url", "page_title", "description", "skills", "scraped_at", "status"]
    
    # Check if URL already exists
    existing = False
    if DESCRIPTIONS_CSV.exists():
        with open(DESCRIPTIONS_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == desc_data["url"]:
                    existing = True
                    break
    
    if existing:
        # Update existing entry
        entries = []
        with open(DESCRIPTIONS_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == desc_data["url"]:
                    entries.append(desc_data)
                else:
                    entries.append(row)
        
        with open(DESCRIPTIONS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(entry)
    else:
        # Append new entry
        file_exists = DESCRIPTIONS_CSV.exists()
        with open(DESCRIPTIONS_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(desc_data)
    
    # Also save full description as text file
    url_hash = hashlib.md5(desc_data["url"].encode()).hexdigest()[:12]
    desc_file = DESCRIPTIONS_DIR / f"{url_hash}.txt"
    with open(desc_file, "w") as f:
        f.write(f"URL: {desc_data['url']}\n")
        f.write(f"Title: {desc_data['page_title']}\n")
        f.write(f"Scraped: {desc_data['scraped_at']}\n")
        f.write(f"Skills: {', '.join(desc_data['skills'])}\n")
        f.write(f"\n{'='*80}\n\n")
        f.write(desc_data['description'])
    
    return desc_file


def main():
    parser = argparse.ArgumentParser(description="Job Description Deep-Scraper")
    parser.add_argument("--top", type=int, default=10, help="Scrape top N jobs")
    parser.add_argument("--url", default="", help="Scrape specific URL only")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"  JOB DESCRIPTION DEEP-SCRAPER")
    print(f"{'='*80}\n")
    
    DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.url:
        # Scrape single URL
        print(f"Scraping: {args.url}")
        desc_data = scrape_job_description(args.url)
        if desc_data["status"] == "success":
            desc_file = save_description(desc_data)
            print(f"  ✓ Saved to {desc_file.name}")
            print(f"  ✓ Description: {len(desc_data['description'])} chars")
            print(f"  ✓ Skills found: {', '.join(desc_data['skills'][:10])}")
        else:
            print(f"  ✗ Error: {desc_data['status']}")
        return
    
    # Get top jobs
    print(f"Getting top {args.top} matched jobs...")
    top_jobs = get_top_jobs(args.top)
    
    if not top_jobs:
        print("ERROR: No matched jobs found")
        return
    
    print(f"Found {len(top_jobs)} jobs to scrape\n")
    
    # Scrape each job
    success_count = 0
    for i, job in enumerate(top_jobs, 1):
        url = job.get("url", "")
        title = job.get("title", "")[:50]
        try:
            score = int(job.get("_score", 0))
        except (ValueError, TypeError):
            score = 0
        
        print(f"{i:2d}. [{score}] {title}")
        print(f"    {url}")
        
        desc_data = scrape_job_description(url)
        
        if desc_data["status"] == "success":
            desc_file = save_description(desc_data)
            print(f"    ✓ Saved ({len(desc_data['description'])} chars, {len(desc_data['skills'])} skills)")
            success_count += 1
        else:
            print(f"    ✗ {desc_data['status']}")
        
        # Delay between requests
        if i < len(top_jobs):
            time.sleep(args.delay)
    
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}\n")
    print(f"  Scraped: {success_count}/{len(top_jobs)} jobs")
    print(f"  Saved to: {DESCRIPTIONS_CSV}")
    print(f"  Full descriptions: {DESCRIPTIONS_DIR}/\n")


if __name__ == "__main__":
    main()
