#!/usr/bin/env python3
"""
Scrape remote job postings from multiple boards (WeWorkRemotely, RemoteOK, etc.).
Detects new high-paying dev jobs and matches against your skills.

Outputs:
    - domains/product/engineering/book-dev/book-scraping/data/job_postings.csv (latest snapshot)
    - domains/product/engineering/book-dev/book-scraping/data/job_postings_history.csv (appended)
    - Console alerts for new high-paying jobs

Usage:
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_job_postings.py
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_job_postings.py --boards weworkremotely,remoteok
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_job_postings.py --keywords "python,react,next.js"
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_job_postings.py --min-salary 50000
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

import re

ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"

# Free scraper headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

DEFAULT_KEYWORDS = ["python", "react", "next.js", "node.js", "full-stack", "typescript", "AI", "API",
                    "โปรแกรมเมอร์", "นักพัฒนา", "developer", "software engineer", "remote"]
THAI_KEYWORDS = ["โปรแกรมเมอร์", "นักพัฒนา", "เว็บ", "ระบบ", "ไอที", "ซอฟต์แวร์", "developer", "fullstack"]
DEFAULT_MIN_SALARY = 0  # Show all by default


def _extract_company_from_url(url: str, source: str) -> str:
    """Fallback: extract company name from job board URL slugs.

    Each source has its own URL pattern. Returns '' if no match.
    """
    import re as _re
    try:
        path = url.lower()
        if 'dice.com' in path:
            # Dice URLs don't contain company — return empty
            return ''
        if 'landing.jobs' in path:
            # landing.jobs/at/{company-slug}/{job-slug}
            m = _re.search(r'landing\.jobs/at/([^/]+)/', path)
            if m:
                return m.group(1).replace('-', ' ').title()
        if 'weworkremotely.com' in path:
            # weworkremotely.com/remote-jobs/{company-slug}-{job-title}
            m = _re.search(r'remote-jobs/(.+)', path)
            if m:
                slug = m.group(1)
                job_keywords = {'senior', 'junior', 'mid', 'lead', 'staff', 'principal',
                                'full', 'front', 'back', 'backend', 'frontend',
                                'devops', 'data', 'ai', 'ml',
                                'software', 'web', 'mobile', 'ios', 'android', 'cloud',
                                'platform', 'site', 'qa', 'test', 'product', 'design',
                                'ux', 'ui', 'content', 'technical', 'sre', 'security',
                                'python', 'react', 'node', 'java', 'ruby', 'go', 'rust',
                                'dev', 'developer', 'engineer', 'manager', 'director',
                                'role', 'position', 'jobs'}
                words = slug.split('-')
                company_words = []
                for w in words:
                    if w in job_keywords:
                        break
                    company_words.append(w)
                if company_words:
                    return ' '.join(company_words).title()
        if 'arc.dev' in path:
            # arc.dev/remote-jobs/{company-slug}-{job-title}
            # Company is usually the first 1-3 words of the slug
            m = _re.search(r'remote-jobs/(.+)', path)
            if m:
                slug = m.group(1)
                # Known patterns: company name followed by job title keywords
                job_keywords = {'senior', 'junior', 'mid', 'lead', 'staff', 'principal',
                                'full', 'front', 'back', 'backend', 'frontend',
                                'devops', 'data', 'ai', 'ml',
                                'software', 'web', 'mobile', 'ios', 'android', 'cloud',
                                'platform', 'site', 'qa', 'test', 'product', 'design',
                                'ux', 'ui', 'content', 'technical', 'sre', 'security',
                                'role', 'position', 'jobs'}
                words = slug.split('-')
                company_words = []
                for w in words:
                    if w in job_keywords:
                        break
                    company_words.append(w)
                if company_words:
                    return ' '.join(company_words).title()
        return ''
    except Exception:
        return ''


# Remote job board RSS/API endpoints (free, no auth)
JOB_SOURCES = {
    "weworkremotely": {
        "name": "WeWorkRemotely",
        "url": "https://weworkremotely.com/remote-jobs/search?term={keyword}",
        "type": "free_scrape",
    },
    "remoteok": {
        "name": "RemoteOK",
        "url": "https://remoteok.com/remote-{keyword}-jobs",
        "type": "free_scrape",
    },
    "remotive": {
        "name": "Remotive",
        "url": "https://remotive.com/api/remote-jobs?search={keyword}&limit=20",
        "type": "httpx_json",
    },
}


def free_scrape_url(url: str) -> str:
    """Scrape a URL using free httpx + BeautifulSoup. Returns text content."""
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
            {'class_': re.compile(r'job[_-]?content', re.I)},
            {'class_': re.compile(r'description', re.I)},
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

        # Strategy 5: Job links
        job_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if text and 5 < len(text) < 150:
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
        print(f"    Scrape failed: {e}")
        return ""


def html_to_markdown(url: str) -> str:
    """Fetch URL and convert HTML to markdown-like text (free Firecrawl replacement).
    Preserves [title](url) links and **bold** text for regex parsing."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Remove script/style/nav/footer
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()

        # Convert headings
        for level in range(1, 7):
            for h in soup.find_all(f'h{level}'):
                h.string = f"\n{'#' * level} {h.get_text(strip=True)}\n"

        # Convert bold
        for tag in soup.find_all(['b', 'strong']):
            text = tag.get_text(strip=True)
            if text:
                tag.string = f"**{text}**"

        # Convert links
        for a in soup.find_all('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if text and href and not href.startswith('#'):
                if href and not href.startswith('http'):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)
                a.string = f"[{text}]({href})"

        # Convert images to alt text
        for img in soup.find_all('img'):
            alt = img.get('alt', '')
            if alt:
                img.replace_with(f"![{alt}]")

        # Find main content
        main = soup.find('main') or soup.find('article') or soup.find(id=re.compile(r'content|main', re.I))
        if main:
            text = main.get_text(separator='\n', strip=True)
        else:
            body = soup.find('body')
            text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
    except Exception as e:
        print(f"    html_to_markdown failed for {url}: {e}")
        return ""


def fetch_remotive(keyword: str, limit: int = 50) -> list:
    """Fetch jobs from Remotive API (free, no auth)."""
    url = f"https://remotive.com/api/remote-jobs?search={keyword}&limit={limit}"
    try:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for j in data.get("jobs", []):
            jobs.append({
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location", "Remote"),
                "salary": j.get("salary", "") or "",
                "url": j.get("url", ""),
                "source": "Remotive",
                "keyword": keyword,
                "posted": j.get("publication_date", "")[:10] if j.get("publication_date") else "",
                "tags": ",".join(j.get("tags", [])),
            })
        return jobs
    except Exception as e:
        print(f"  Warning: Remotive fetch failed for '{keyword}': {e}")
        return []


def fetch_weworkremotely(keyword: str) -> list:
    """Fetch jobs from WeWorkRemotely via direct httpx."""
    url = f"https://weworkremotely.com/remote-jobs/search?term={keyword}"
    try:
        md = html_to_markdown(url)
        return parse_weworkremotely(md, keyword)
    except Exception as e:
        print(f"  Warning: WWR scrape failed for '{keyword}': {e}")
        return []


def parse_weworkremotely(markdown: str, keyword: str) -> list:
    """Parse WWR markdown into job listings."""
    import re
    jobs = []
    # WWR lists jobs as links with company names
    lines = markdown.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for job title links: [Title](url) or ### [Title](url)
        match = re.match(r'(?:###\s*)?\[([^\]]+)\]\((https://weworkremotely\.com/remote-jobs/[^\)]+)\)', line)
        if match:
            raw_title = match.group(1)
            url = match.group(2)
            # Clean title: remove trailing junk like '18dBoosted', '10dBoosted listing'
            title = re.sub(r'\d+d(?:Boosted\s*(?:listing)?)?\s*$', '', raw_title).strip()
            # Extract company from URL slug as primary source
            company = _extract_company_from_url(url, 'WeWorkRemotely')
            # Fallback: next line may have company info
            if not company and i + 1 < len(lines):
                company_line = lines[i + 1].strip()
                if company_line and not company_line.startswith('['):
                    company = company_line.split('·')[0].strip() if '·' in company_line else company_line
            # Fallback: company may be inline after title (e.g. 'Title5dCompanyName')
            if not company:
                inline_match = re.search(r'[a-z](\d+d)([A-Z][a-z]+)', raw_title)
                if inline_match:
                    company = inline_match.group(2)
            jobs.append({
                "title": title,
                "company": company,
                "location": "Remote",
                "salary": "",
                "url": url,
                "source": "WeWorkRemotely",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
        i += 1
    return jobs


def fetch_remoteok(keyword: str) -> list:
    """Fetch jobs from RemoteOK public API (free, no auth)."""
    return fetch_remoteok_api(keyword)


def fetch_remoteok_api(keyword: str) -> list:
    """Fetch jobs from RemoteOK public API (free, no auth)."""
    url = f"https://remoteok.com/api?tag={keyword}&limit=50"
    try:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        data = resp.json()
        jobs_raw = [j for j in data if isinstance(j, dict) and "position" in j]
        jobs = []
        for j in jobs_raw:
            salary_parts = []
            if j.get("salary_min"):
                salary_parts.append(f"${int(j['salary_min'])//1000}k")
            if j.get("salary_max"):
                salary_parts.append(f"${int(j['salary_max'])//1000}k")
            salary = " - ".join(salary_parts) if salary_parts else ""
            jobs.append({
                "title": j.get("position", ""),
                "company": j.get("company", ""),
                "location": j.get("location", "Remote") or "Remote",
                "salary": salary,
                "url": j.get("url", "") or j.get("apply", ""),
                "source": "RemoteOK",
                "keyword": keyword,
                "posted": j.get("date", "")[:10] if j.get("date") else "",
                "tags": ",".join(j.get("tags", [])),
            })
        return jobs
    except Exception as e:
        print(f"  Warning: RemoteOK API failed for '{keyword}': {e}")
        return []


def parse_remoteok(markdown: str, keyword: str) -> list:
    """Parse RemoteOK markdown into job listings."""
    import re
    jobs = []
    lines = markdown.split("\n")
    for line in lines:
        line = line.strip()
        match = re.match(r'\[([^\]]+)\]\((https://remoteok\.com/[^\)]+)\)', line)
        if match:
            title = match.group(1)
            url = match.group(2)
            if "/remote-" in url and "-job" in url:
                jobs.append({
                    "title": title,
                    "company": "",
                    "location": "Remote",
                    "salary": "",
                    "url": url,
                    "source": "RemoteOK",
                    "keyword": keyword,
                    "posted": "",
                    "tags": keyword,
                })
    return jobs


def fetch_himalayas(keyword: str, pages: int = 3) -> list:
    """Fetch jobs from Himalayas.app API (free, no auth, 88k+ jobs)."""
    jobs = []
    for page in range(pages):
        url = f"https://himalayas.app/jobs/api?offset={page * 20}&limit=20&search={keyword}"
        try:
            resp = httpx.get(url, timeout=30, headers={"User-Agent": "SoloEmpire/1.0"})
            resp.raise_for_status()
            data = resp.json()
            job_list = data.get("jobs", [])
            if not job_list:
                break
            for j in job_list:
                salary_parts = []
                if j.get("minSalary"):
                    salary_parts.append(f"${int(j['minSalary'])//1000}k")
                if j.get("maxSalary"):
                    salary_parts.append(f"${int(j['maxSalary'])//1000}k")
                salary = " - ".join(salary_parts) if salary_parts else ""
                jobs.append({
                    "title": j.get("title", ""),
                    "company": j.get("companyName", ""),
                    "location": ", ".join(j.get("locationRestrictions", [])) or "Remote",
                    "salary": salary,
                    "url": j.get("applicationLink", ""),
                    "source": "Himalayas",
                    "keyword": keyword,
                    "posted": datetime.fromtimestamp(j["pubDate"]).strftime("%Y-%m-%d") if j.get("pubDate") else "",
                    "tags": ",".join(j.get("categories", [])[:5]),
                })
        except Exception as e:
            print(f"  Warning: Himalayas fetch failed for '{keyword}' page {page}: {e}")
            break
    return jobs


# ── Jobicy (free API, no auth) ─────────────────────────────────────────────
def fetch_jobicy(keyword: str) -> list:
    """Fetch jobs from Jobicy.com API (free, no auth, remote-focused)."""
    jobs = []
    try:
        url = f"https://jobicy.com/api/v2/remote-jobs?tag={keyword}"
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return jobs
        for j in data.get("jobs", []):
            jobs.append({
                "title": j.get("jobTitle", ""),
                "company": j.get("companyName", ""),
                "location": j.get("jobGeo", "Remote"),
                "salary": "",
                "url": j.get("url", ""),
                "source": "Jobicy",
                "keyword": keyword,
                "posted": j.get("pubDate", "")[:10] if j.get("pubDate") else "",
                "tags": ",".join(j.get("jobIndustry", [])[:3]),
            })
    except Exception as e:
        print(f"  Warning: Jobicy fetch failed for '{keyword}': {e}")
    return jobs


# ── Landing.jobs (free API, no auth, 45+ jobs per query) ───────────────────
def fetch_landing_jobs(keyword: str) -> list:
    """Fetch jobs from Landing.jobs API (free, no auth, remote-focused)."""
    jobs = []
    try:
        url = f"https://landing.jobs/api/v1/jobs?keyword={keyword}&remote=true"
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        data = resp.json()
        for j in data:
            # Extract salary from perks if available
            perks = j.get("perks", "")
            salary = ""
            import re
            salary_match = re.search(r'\$[\d,]+', perks)
            if salary_match:
                salary = salary_match.group(0)
            
            # Company extraction with multiple fallbacks
            company = ""
            # 1. API field as dict
            if isinstance(j.get("company"), dict):
                company = j["company"].get("name", "")
            # 2. API field as string
            if not company and isinstance(j.get("company"), str):
                company = j["company"]
            # 3. company_name field
            if not company:
                company = j.get("company_name", "")
            # 4. URL slug: landing.jobs/at/{company-slug}/{job-slug}
            if not company:
                company = _extract_company_from_url(j.get("url", ""), "Landing.jobs")
            
            jobs.append({
                "title": j.get("title", ""),
                "company": company,
                "location": "Remote" if j.get("remote") else j.get("location", ""),
                "salary": salary,
                "url": j.get("url", ""),
                "source": "Landing.jobs",
                "keyword": keyword,
                "posted": j.get("published_at", "")[:10] if j.get("published_at") else "",
                "tags": ",".join(j.get("tags", [])[:5]) if isinstance(j.get("tags"), list) else j.get("tags", ""),
            })
    except Exception as e:
        print(f"  Warning: Landing.jobs fetch failed for '{keyword}': {e}")
    return jobs


# ── Indeed (via free scraper) ─────────────────────────────────────────────────────
def fetch_indeed(keyword: str) -> list:
    """Fetch jobs from Indeed.com via free scraper."""
    jobs = []
    try:
        search_url = f"https://www.indeed.com/jobs?q={keyword}+remote&l=Remote&fromage=7"
        md = free_scrape_url(search_url)
        if not md:
            return jobs
        # Parse job cards: ### [Title](url)
        pattern = r'### \[([^\]]+)\]\(([^)]+)\)'
        matches = re.findall(pattern, md)
        for title, url in matches:
            if "indeed.com" in url or "indeed-click" in url:
                jobs.append({
                    "title": title,
                    "company": "",
                    "location": "Remote",
                    "salary": "",
                    "url": url,
                    "source": "Indeed",
                    "keyword": keyword,
                    "posted": "",
                    "tags": keyword,
                })
    except Exception as e:
        print(f"  Warning: Indeed fetch failed for '{keyword}': {e}")
    return jobs


# ── Seek AU/NZ (via free scraper) ─────────────────────────────────────────────────
def fetch_seek(keyword: str, country: str = "au") -> list:
    """Fetch jobs from Seek.com.au or Seek.co.nz via free scraper."""
    jobs = []
    try:
        domain = "au" if country == "au" else "nz"
        if country == "nz":
            search_url = f"https://www.seek.co.nz/jobs?keywords={keyword}+remote"
        else:
            search_url = f"https://www.seek.com.{domain}/jobs?keywords={keyword}+remote"
        md = free_scrape_url(search_url)
        if not md:
            return jobs
        # Parse job cards: ### [Title](au.seek.com/job/ID)
        title_pattern = r'### \[([^\]]+)\]\((https://[^)]*seek\.com[^)]*/job/[^)]+)\)'
        title_matches = re.findall(title_pattern, md)
        for title, url in title_matches:
            company = ""
            company_pattern = rf'at\[([^\]]+)\]\([^)]+\)'
            company_match = re.search(company_pattern, md[md.find(url):md.find(url)+500])
            if company_match:
                company = company_match.group(1)
            salary = ""
            salary_pattern = r'\$[\d,]+\s*[–-]\s*\$[\d,]+[^\n]*'
            salary_match = re.search(salary_pattern, md[md.find(url):md.find(url)+1000])
            if salary_match:
                salary = salary_match.group(0).strip()
            location = "Remote"
            if country == "au":
                location_pattern = r'\[([^\]]+\s+(?:VIC|NSW|QLD|WA|SA|TAS|ACT|NT))\]\([^)]*in-[^)]+\)'
            else:
                location_pattern = r'\[([^\]]+\s+(?:Auckland|Wellington|Canterbury|Otago|Waikato|Bay of Plenty|Manawatu|Hawke|Taranaki|Northland|Southland|Marlborough|Nelson|Tasman|West Coast))\]\([^)]*in-[^)]+\)'
            location_match = re.search(location_pattern, md[md.find(url):md.find(url)+500])
            if location_match:
                location = location_match.group(1)
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "salary": salary,
                "url": url,
                "source": f"Seek.{domain.upper()}",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
    except Exception as e:
        print(f"  Warning: Seek {country.upper()} fetch failed for '{keyword}': {e}")
    return jobs


# ── JobThai (direct HTML parsing, Thai job market) ────────────────────────────────
def fetch_jobthai(keyword: str) -> list:
    """Fetch jobs from JobThai.com by parsing raw HTML (Thai job market)."""
    jobs = []
    try:
        search_url = f"https://www.jobthai.com/jobs?keyword={keyword}"
        resp = httpx.get(search_url, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Find all job links: <a href="/th/company/job/ID">
        seen_ids = set()
        for a in soup.find_all('a', href=re.compile(r'/th/company/job/\d+')):
            href = a['href']
            job_id_match = re.search(r'/th/company/job/(\d+)', href)
            if not job_id_match:
                continue
            job_id = job_id_match.group(1)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            # Parse pipe-separated text: Title|Company(dup)|Company(dup)|Location|Salary|Date
            parts = [p.strip() for p in a.get_text('|', strip=True).split('|') if p.strip()]
            title = parts[0] if len(parts) > 0 else ''
            # Company is parts[1] and parts[2] (duplicated), take parts[1]
            company = parts[1] if len(parts) > 1 else ''
            location = parts[3] if len(parts) > 3 else 'Thailand'
            salary = parts[4] if len(parts) > 4 else ''
            posted = parts[5] if len(parts) > 5 else ''
            if title:
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "url": f"https://www.jobthai.com/th/company/job/{job_id}",
                    "source": "JobThai",
                    "keyword": keyword,
                    "posted": posted,
                    "tags": keyword,
                })
    except Exception as e:
        print(f"  Warning: JobThai fetch failed for '{keyword}': {e}")
    return jobs


# ── JobsDB Thailand (direct HTML parsing) ─────────────────────────────────────────
def fetch_jobsdb_th(keyword: str) -> list:
    """Fetch jobs from JobsDB Thailand by parsing raw HTML with data-automation attributes."""
    jobs = []
    try:
        search_url = f"https://th.jobsdb.com/jobs?keywords={keyword}"
        resp = httpx.get(search_url, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Each job is in an <article> with data-automation attributes
        for article in soup.find_all('article'):
            # Extract title
            title_el = article.find(attrs={'data-automation': 'jobTitle'})
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            # Extract job URL
            link_el = article.find('a', href=re.compile(r'/job/'))
            if not link_el:
                continue
            href = link_el['href']
            url = f"https://th.jobsdb.com{href}" if href.startswith('/') else href
            # Extract company
            company_el = article.find(attrs={'data-automation': 'jobCompany'})
            company = company_el.get_text(strip=True) if company_el else ''
            # Extract location
            location_el = article.find(attrs={'data-automation': 'jobLocation'})
            location = location_el.get_text(strip=True) if location_el else 'Thailand'
            # Extract salary
            salary_el = article.find(attrs={'data-automation': 'jobSalary'})
            salary = salary_el.get_text(strip=True) if salary_el else ''
            # Extract posted date
            date_el = article.find(attrs={'data-automation': 'jobListingDate'})
            posted = date_el.get_text(strip=True) if date_el else ''
            if title:
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "url": url,
                    "source": "JobsDB-TH",
                    "keyword": keyword,
                    "posted": posted,
                    "tags": keyword,
                })
    except Exception as e:
        print(f"  Warning: JobsDB TH fetch failed for '{keyword}': {e}")
    return jobs


# ── JobBKK (free scraper, Thai job market) ────────────────────────────────────
def fetch_jobbkk(keyword: str) -> list:
    """Fetch jobs from JobBKK.com via free html_to_markdown (Thai job market)."""
    jobs = []
    try:
        search_url = f"https://jobbkk.com/jobs/lists/1/{keyword}.html?keyword_type=1"
        md = html_to_markdown(search_url)
        if not md:
            return jobs
        # Parse job cards: [Title](jobbkk.com/jobs/detail/CATEGORY/ID)
        title_pattern = r'\[([^\]]+)\]\((https://jobbkk\.com/jobs/detail[^)]+)\)'
        title_matches = re.findall(title_pattern, md)
        for title, url in title_matches:
            # Find company: [Company](jobbkk.com/company/...)
            company = ""
            pos = md.find(url)
            if pos != -1:
                company_pattern = r'\[([^\]]+)\]\(https://jobbkk\.com/company/[^)]+\)'
                company_match = re.search(company_pattern, md[pos:pos+800])
                if company_match:
                    company = company_match.group(1)
            # Find salary
            salary = ""
            if pos != -1:
                salary_pattern = r'([\d,]+)-([\d,]+)\s*บาท'
                salary_match = re.search(salary_pattern, md[pos:pos+800])
                if salary_match:
                    salary = f'{salary_match.group(1)}-{salary_match.group(2)} บาท'
            # Find location
            location = "Thailand"
            if pos != -1:
                location_pattern = r'\[([^\]]+(?:กรุงเทพมหานคร|กรุงเทพ|เขต)[^\]]*)\]'
                location_match = re.search(location_pattern, md[pos:pos+800])
                if location_match:
                    location = location_match.group(1)
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "salary": salary,
                "url": url,
                "source": "JobBKK",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
    except Exception as e:
        print(f"  Warning: JobBKK fetch failed for '{keyword}': {e}")
    return jobs


def fetch_hn_who_is_hiring(keyword: str) -> list:
    """Fetch jobs from Hacker News 'Who is hiring' monthly threads via Algolia API."""
    jobs = []
    try:
        # Find the latest 'Who is hiring' thread
        resp = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": "Who is hiring", "tags": "story", "hitsPerPage": 1},
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return jobs
        thread_id = hits[0]["objectID"]

        # Search comments in that thread for the keyword
        resp2 = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": f"remote {keyword}",
                "tags": f"comment,story_{thread_id}",
                "hitsPerPage": 30,
            },
            timeout=15,
        )
        resp2.raise_for_status()
        comments = resp2.json().get("hits", [])

        for c in comments:
            text = c.get("comment_text", "")
            # Extract company from first line (format: "Company | Location | ...")
            first_line = text.split("<p>")[0].split("|")[0].strip()
            # Clean HTML tags
            import re
            first_line = re.sub(r'<[^>]+>', '', first_line).strip()
            if not first_line or len(first_line) < 3:
                continue

            # Extract URL from the comment
            url_match = re.search(r'href="([^"]+)"', text)
            job_url = url_match.group(1).replace("&#x2F;", "/").replace("&amp;", "&") if url_match else ""

            # Extract location from pipe-separated format
            parts = [p.strip() for p in re.sub(r'<[^>]+>', '', text.split("<p>")[0]).split("|")]
            location = parts[1] if len(parts) > 1 else "Remote"

            jobs.append({
                "title": first_line[:100],
                "company": first_line.split("|")[0].strip() if "|" in first_line else first_line[:50],
                "location": location,
                "salary": "",
                "url": job_url,
                "source": "HN_WhoIsHiring",
                "keyword": keyword,
                "posted": c.get("created_at", "")[:10] if c.get("created_at") else "",
                "tags": f"hn,hiring,{keyword}",
            })
    except Exception as e:
        print(f"  Warning: HN Who is hiring failed for '{keyword}': {e}")
    return jobs


# ── Upwork (free scraper, freelance marketplace) ─────────────────────────────
def fetch_upwork(keyword: str) -> list:
    """Upwork blocks scraping (403). Returns empty."""
    return []


# ── Fastwork (Thai freelance platform, free scraper) ─────────────────────────
def fetch_fastwork(keyword: str) -> list:
    """Fetch freelance gigs from Fastwork.co (Thai freelance marketplace) via free scraper."""
    jobs = []
    try:
        search_url = f"https://fastwork.co/search?q={keyword}&type=job"
        md = html_to_markdown(search_url)
        if not md:
            return jobs
        # Split markdown by Fastwork user URLs to isolate each gig card
        url_pattern = r'(https://fastwork\.co/user/[a-z0-9_]+/[a-z0-9-]+\?[^")\s]+)'
        segments = re.split(url_pattern, md)
        seen_urls = set()
        for i in range(1, len(segments), 2):  # URLs are at odd indices
            url = segments[i]
            clean_url = url.split("?")[0]
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)
            # Look at text BEFORE the URL for the bold title AND price
            before = segments[i - 1] if i > 0 else ""
            # Find the LAST bold text before the URL (that's the gig title)
            bold_matches = re.findall(r'\*\*([^\\*\n]{15,150})\*\*', before)
            title = bold_matches[-1].strip() if bold_matches else ""
            if not title or len(title) < 10:
                continue
            # Look for price in the BEFORE text (เริ่มต้น฿X,XXX format)
            price = ""
            price_match = re.search(r'฿([\d,]+)', before[-500:])
            if price_match:
                price = f"฿{price_match.group(1)}"
            jobs.append({
                "title": title[:100],
                "company": "Fastwork Client",
                "location": "Thailand/Remote",
                "salary": price,
                "url": clean_url,
                "source": "Fastwork",
                "keyword": keyword,
                "posted": "",
                "tags": f"freelance,fastwork,thai,{keyword}",
            })
    except Exception as e:
        print(f"  Warning: Fastwork fetch failed for '{keyword}': {e}")
    return jobs


# ── Fiverr (free scraper, freelance marketplace) ─────────────────────────────
def fetch_fiverr(keyword: str) -> list:
    """Fiverr blocks scraping (403). Returns empty."""
    return []


# ── Toptal (via Google site: search, high-end freelance) ──────────────────────
def _firecrawl_search(query: str, limit: int = 20) -> list:
    """Fallback search via Firecrawl API when Google fails."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        return []
    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": limit},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  Firecrawl fallback returned {resp.status_code}")
            return []
        data = resp.json()
        results = []
        for item in data.get("data", []):
            title = item.get("title", "") or item.get("metadata", {}).get("title", "")
            url = item.get("url", "") or item.get("metadata", {}).get("sourceURL", "")
            desc = item.get("description", "") or item.get("markdown", "")[:200]
            if title and url:
                results.append({"title": title[:200], "url": url, "description": desc})
            if len(results) >= limit:
                break
        if results:
            print(f"  Firecrawl fallback: {len(results)} results for '{query[:50]}'")
        return results
    except Exception as e:
        print(f"  Firecrawl fallback failed: {e}")
        return []


def fetch_toptal(keyword: str) -> list:
    """Fetch freelance jobs from Toptal via Google site: search (no public job board).
    Falls back to Firecrawl API if Google fails."""
    jobs = []
    search_query = f"site:toptal.com {keyword} freelance remote job"
    try:
        google_url = f"https://www.google.com/search?q={search_query}&num=20"
        resp = httpx.get(google_url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            # Fall back to Firecrawl
            fc_results = _firecrawl_search(search_query, limit=20)
            for r in fc_results:
                if "toptal.com" in r.get("url", ""):
                    jobs.append({
                        "title": r.get("title", f"Toptal {keyword} role")[:100],
                        "company": "Toptal",
                        "location": "Remote",
                        "salary": "",
                        "url": r["url"],
                        "source": "Toptal",
                        "keyword": keyword,
                        "posted": "",
                        "tags": f"freelance,toptal,premium,{keyword}",
                    })
            return jobs
        soup = BeautifulSoup(resp.text, 'html.parser')
        seen_urls = set()
        for a_tag in soup.find_all('a', href=True):
            url = a_tag['href']
            # Google wraps links in /url?q=...
            m = re.search(r'/url\?q=(https?://[^&]+)', url)
            if m:
                url = m.group(1)
            if "toptal.com" not in url:
                continue
            if any(skip in url for skip in ["/hire/", "/talent/apply", "/blog", "/faq", "/contact"]):
                continue
            # Individual jobs have a numeric ID in the last URL segment
            parts = url.rstrip("/").split("/")
            last_segment = parts[-1] if parts else ""
            if not any(c.isdigit() for c in last_segment):
                continue
            clean_url = url.split("?")[0]
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)
            title = a_tag.get_text(strip=True) or keyword
            if len(title) < 5:
                title = f"Toptal {keyword} role"
            jobs.append({
                "title": title.strip()[:100],
                "company": "Toptal",
                "location": "Remote",
                "salary": "",
                "url": clean_url,
                "source": "Toptal",
                "keyword": keyword,
                "posted": "",
                "tags": f"freelance,toptal,premium,{keyword}",
            })
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ['name resolution', 'dns', 'network is unreachable', 'no route']):
            fc_results = _firecrawl_search(search_query, limit=20)
            for r in fc_results:
                if "toptal.com" in r.get("url", ""):
                    jobs.append({
                        "title": r.get("title", f"Toptal {keyword} role")[:100],
                        "company": "Toptal",
                        "location": "Remote",
                        "salary": "",
                        "url": r["url"],
                        "source": "Toptal",
                        "keyword": keyword,
                        "posted": "",
                        "tags": f"freelance,toptal,premium,{keyword}",
                    })
        else:
            print(f"  Warning: Toptal fetch failed for '{keyword}': {e}")
    return jobs


# ── Arc.dev (high-paying remote, via __NEXT_DATA__ HTML parsing) ─────────────
def fetch_arc(keyword: str) -> list:
    """Fetch jobs from Arc.dev by parsing embedded __NEXT_DATA__ JSON."""
    jobs = []
    try:
        import re
        import json as _json
        url = "https://arc.dev/remote-jobs"
        resp = httpx.get(url, follow_redirects=True, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
        # Extract __NEXT_DATA__ JSON
        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if not match:
            print("  Warning: Arc.dev __NEXT_DATA__ not found")
            return jobs
        data = _json.loads(match.group(1))
        props = data.get("props", {}).get("pageProps", {})
        all_jobs = props.get("arcJobs", []) + props.get("externalJobs", [])
        kw_lower = keyword.lower()
        for j in all_jobs:
            title = j.get("title", "")
            cats = [c.get("name", "") for c in j.get("categories", [])]
            tags_list = j.get("tags", []) if isinstance(j.get("tags"), list) else []
            # Keyword filter: match title, categories, or tags
            searchable = (title + " " + " ".join(cats) + " " + " ".join(tags_list)).lower()
            if kw_lower not in searchable:
                continue
            company_data = j.get("company", {})
            company = ""
            if isinstance(company_data, dict):
                company = company_data.get("name", "") or company_data.get("displayName", "")
            elif isinstance(company_data, str):
                company = company_data
            # Fallback: check other possible fields
            if not company:
                company = j.get("companyName", "") or j.get("employer", {}).get("name", "") if isinstance(j.get("employer"), dict) else j.get("companyName", "")
            # Fallback: extract from URL slug
            if not company:
                company = _extract_company_from_url(j.get("urlString", "") or j.get("url", ""), "Arc.dev")
            url_string = j.get("urlString", "")
            job_url = f"https://arc.dev/remote-jobs/{url_string}" if url_string else ""
            min_sal = j.get("minAnnualSalary") or 0
            max_sal = j.get("maxAnnualSalary") or 0
            salary = f"${min_sal:,} - ${max_sal:,}" if min_sal and max_sal else ""
            countries = j.get("requiredCountries", [])
            location = ", ".join(countries) if countries else "Remote"
            jobs.append({
                "title": title.strip(),
                "company": company,
                "location": location,
                "salary": salary,
                "url": job_url,
                "source": "Arc.dev",
                "keyword": keyword,
                "posted": "",
                "tags": ", ".join(cats),
            })
        print(f"  Parsed {len(all_jobs)} Arc.dev jobs, {len(jobs)} match '{keyword}'")
    except Exception as e:
        print(f"  Warning: Arc.dev fetch failed for '{keyword}': {e}")
    return jobs


# ── WorkingNomads (via Elasticsearch API) ─────────────────────────────────────
def fetch_workingnomads(keyword: str) -> list:
    """Fetch jobs from WorkingNomads via their Elasticsearch API."""
    jobs = []
    try:
        es_url = "https://www.workingnomads.com/jobsapi/_search"
        body = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title": {"query": keyword, "boost": 3}}},
                        {"match": {"tags": keyword}},
                        {"match": {"category_name": keyword}},
                    ]
                }
            },
            "size": 50,
            "sort": [{"pub_date": "desc"}],
        }
        resp = httpx.post(es_url, json=body, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits:
            src = hit.get("_source", {})
            title = src.get("title", "")
            company = src.get("company", "")
            slug = src.get("slug", "")
            job_url = f"https://www.workingnomads.com/job/{slug}" if slug else ""
            apply_url = src.get("apply_url", "")
            locations = src.get("locations", [])
            location = ", ".join(locations) if locations else "Remote"
            salary = src.get("salary_range_short", "")
            if not salary:
                annual = src.get("annual_salary_usd")
                if annual:
                    salary = f"${annual:,}"
            tags = src.get("tags", [])
            pub_date = src.get("pub_date", "")[:10]
            jobs.append({
                "title": title.strip(),
                "company": company,
                "location": location,
                "salary": salary,
                "url": apply_url or job_url,
                "source": "WorkingNomads",
                "keyword": keyword,
                "posted": pub_date,
                "tags": ", ".join(tags) if tags else keyword,
            })
        print(f"  WorkingNomads ES: {len(hits)} hits for '{keyword}'")
    except Exception as e:
        print(f"  Warning: WorkingNomads fetch failed for '{keyword}': {e}")
    return jobs


# ── Turing (high-paying remote, via free scraper) ─────────────────────────────
def fetch_turing(keyword: str) -> list:
    """Turing.com changed URL structure - returns empty."""
    return []


# ── TheMuse ────────────────────────────────────────────────────────────────────
def fetch_themuse(keyword: str) -> list:
    """Fetch jobs from TheMuse public API."""
    jobs = []
    try:
        import json as _json
        url = f"https://www.themuse.com/api/public/jobs?keyword={keyword}&remote=true&page=1"
        resp = httpx.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        kw_lower = keyword.lower()
        for j in results:
            title = j.get("name", "")
            company_data = j.get("company", {})
            if isinstance(company_data, str):
                try:
                    company_data = _json.loads(company_data.replace("'", '"'))
                except Exception:
                    company_data = {}
            company = company_data.get("name", "") if isinstance(company_data, dict) else ""
            # Parse locations
            loc_data = j.get("locations", "[]")
            if isinstance(loc_data, str):
                try:
                    loc_data = _json.loads(loc_data.replace("'", '"'))
                except Exception:
                    loc_data = []
            location = ", ".join(l.get("name", "") for l in loc_data if isinstance(l, dict)) or "Remote"
            # Parse refs for URL
            refs_data = j.get("refs", {})
            if isinstance(refs_data, str):
                try:
                    refs_data = _json.loads(refs_data.replace("'", '"'))
                except Exception:
                    refs_data = {}
            job_url = refs_data.get("landing_page", "") if isinstance(refs_data, dict) else ""
            pub_date = j.get("publication_date", "")[:10]
            jobs.append({
                "title": title.strip(),
                "company": company,
                "location": location,
                "salary": "",
                "url": job_url,
                "source": "TheMuse",
                "keyword": keyword,
                "posted": pub_date,
                "tags": keyword,
            })
        print(f"  TheMuse: {len(results)} results, {len(jobs)} match '{keyword}'")
    except Exception as e:
        print(f"  Warning: TheMuse fetch failed for '{keyword}': {e}")
    return jobs


# ── LinkedIn (blocked - 403) ─────────────────────────────────────────────────
def fetch_linkedin(keyword: str) -> list:
    """LinkedIn blocks scraping - returns empty."""
    print("  Note: LinkedIn blocks automated access (403), skipping")
    return []


# ── Glassdoor (blocked - anti-bot) ────────────────────────────────────────────
def fetch_glassdoor(keyword: str) -> list:
    """Glassdoor blocks scraping - returns empty."""
    print("  Note: Glassdoor blocks automated access, skipping")
    return []


# ── Wellfound / AngelList (free API) ──────────────────────────────────────────
def fetch_wellfound(keyword: str) -> list:
    """Wellfound API no longer available (404). Returns empty."""
    return []


# ── Otta (via free scraper) ───────────────────────────────────────────────────
def fetch_otta(keyword: str) -> list:
    """Otta.com acquired by Welcome to the Jungle - no longer scrapable. Returns empty."""
    return []


# ── Dice (tech jobs, via free scraper) ────────────────────────────────────────
def fetch_dice(keyword: str) -> list:
    """Fetch jobs from Dice.com via free httpx+BS4 scraper."""
    jobs = []
    try:
        import re
        search_url = f"https://www.dice.com/jobs?q={keyword}&remoteOnly=true&postedDate=7"
        md = html_to_markdown(search_url)
        if not md:
            return jobs
        # Parse job cards: [Title](dice.com/job/ID)
        pattern = r'\[([^\]]{10,100})\]\((https://www\.dice\.com/job-detail/[^\)]+)\)'
        matches = re.findall(pattern, md)
        seen = set()
        for title, url in matches:
            if url in seen:
                continue
            seen.add(url)
            pos = md.find(url)
            company = ""
            salary = ""
            if pos >= 0:
                ctx = md[max(0, pos-200):pos+800]
                # Strategy 1: **bold** company name
                comp_match = re.search(r'\*\*([^\*]{3,40})\*\*', ctx)
                if comp_match:
                    company = comp_match.group(1)
                # Strategy 2: 'Company' label followed by value
                if not company:
                    comp_match2 = re.search(r'[Cc]ompany\s*[:\-|]\s*([^\n]{3,40})', ctx)
                    if comp_match2:
                        company = comp_match2.group(1).strip()
                # Strategy 3: line before title link (common pattern in Dice)
                if not company:
                    before_url = md[max(0, pos-200):pos].strip()
                    lines_before = [l.strip() for l in before_url.split('\n') if l.strip()]
                    if lines_before:
                        candidate = lines_before[-1]
                        # Skip if it looks like a heading, salary, or another link
                        if not candidate.startswith('#') and not candidate.startswith('$') and not candidate.startswith('['):
                            company = candidate[:40]
                # Strategy 4: text between title and location/salary
                if not company:
                    after_ctx = md[pos:pos+600]
                    loc_match = re.search(r'(?:Remote|United States|\w+, \w+)\s*\n', after_ctx)
                    if loc_match:
                        between = after_ctx[:loc_match.start()].strip()
                        # Company is usually the first non-empty line after URL
                        for line in between.split('\n'):
                            line = line.strip()
                            if line and len(line) > 2 and not line.startswith('http'):
                                company = line[:40]
                                break
                sal_match = re.search(r'\$[\d,]+\s*[-–]\s*\$[\d,]+', ctx)
                if sal_match:
                    salary = sal_match.group(0)
            jobs.append({
                "title": title.strip(),
                "company": company,
                "location": "Remote",
                "salary": salary,
                "url": url.split("?")[0],
                "source": "Dice",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
    except Exception as e:
        print(f"  Warning: Dice fetch failed for '{keyword}': {e}")
    return jobs


# ── BuiltIn (tech hubs, via free scraper) ─────────────────────────────────────
def fetch_builtin(keyword: str) -> list:
    """BuiltIn.com blocks scraping. Returns empty."""
    return []


# ── Remote.co (RSS feed, no auth) ────────────────────────────────────────────
def fetch_remoteco(keyword: str) -> list:
    """Fetch jobs from Remote.co RSS feed (no auth required)."""
    jobs = []
    try:
        import re
        url = f"https://remote.co/remote-jobs/search/?search_keywords={keyword}"
        resp = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        # Parse job links from HTML
        pattern = r'href="(https://remote\.co/remote-job/[^"]+)"[^>]*>([^<]+)<'
        matches = re.findall(pattern, resp.text)
        seen = set()
        for job_url, title in matches:
            if job_url in seen:
                continue
            seen.add(job_url)
            if title.strip() and len(title.strip()) > 5:
                jobs.append({
                    "title": title.strip()[:100],
                    "company": "",
                    "location": "Remote",
                    "salary": "",
                    "url": job_url,
                    "source": "Remote.co",
                    "keyword": keyword,
                    "posted": "",
                    "tags": keyword,
                })
        # Fallback: try html_to_markdown if no jobs found
        if not jobs:
            md = html_to_markdown(url)
            if md:
                pattern2 = r'\[([^\]]{10,100})\]\((https://remote\.co/remote-job/[^\)]+)\)'
                for title, jurl in re.findall(pattern2, md):
                    if jurl not in seen:
                        seen.add(jurl)
                        jobs.append({
                            "title": title.strip()[:100],
                            "company": "",
                            "location": "Remote",
                            "salary": "",
                            "url": jurl,
                            "source": "Remote.co",
                            "keyword": keyword,
                            "posted": "",
                            "tags": keyword,
                        })
    except Exception as e:
        print(f"  Warning: Remote.co fetch failed for '{keyword}': {e}")
    return jobs


# ── Jobspresso (public JSON API) ──────────────────────────────────────────────
def fetch_jobspresso(keyword: str) -> list:
    """Fetch jobs from Jobspresso public API."""
    jobs = []
    try:
        url = f"https://public.jobspresso.co/api/jobs?search={keyword}&limit=50"
        resp = httpx.get(url, timeout=15, headers={"User-Agent": "SoloEmpire/1.0"})
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
        for j in items:
            title = j.get("title", j.get("position", ""))
            company = j.get("company", j.get("company_name", ""))
            job_url = j.get("url", j.get("job_url", ""))
            location = j.get("location", "Remote")
            if not job_url:
                continue
            jobs.append({
                "title": title.strip()[:100],
                "company": company,
                "location": location or "Remote",
                "salary": "",
                "url": job_url,
                "source": "Jobspresso",
                "keyword": keyword,
                "posted": j.get("date", j.get("created_at", ""))[:10],
                "tags": keyword,
            })
        print(f"  Jobspresso: {len(jobs)} jobs for '{keyword}'")
    except Exception as e:
        print(f"  Warning: Jobspresso fetch failed for '{keyword}': {e}")
    return jobs


# ── Work at a Startup (Y Combinator) ─────────────────────────────────────────
def fetch_workatastartup(keyword: str) -> list:
    """Fetch jobs from Work at a Startup (Y Combinator job board)."""
    jobs = []
    try:
        url = f"https://www.workatastartup.com/jobs?search={keyword}"
        md = html_to_markdown(url)
        if not md:
            return jobs
        import re
        # Parse job cards: [Title](/job/ID) with company info
        pattern = r'\[([^\]]{10,100})\]\((/job/[^\)]+)\)'
        matches = re.findall(pattern, md)
        seen = set()
        for title, path in matches:
            job_url = f"https://www.workatastartup.com{path}"
            if job_url in seen:
                continue
            seen.add(job_url)
            # Try to find company near the title
            pos = md.find(path)
            company = ""
            if pos > 0:
                ctx = md[max(0, pos-200):pos+300]
                comp_match = re.search(r'\*\*([^*]{3,40})\*\*', ctx)
                if comp_match:
                    company = comp_match.group(1)
            jobs.append({
                "title": title.strip()[:100],
                "company": company,
                "location": "Remote / SF",
                "salary": "",
                "url": job_url,
                "source": "WorkAtStartup",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
        print(f"  WorkAtStartup: {len(jobs)} jobs for '{keyword}'")
    except Exception as e:
        print(f"  Warning: WorkAtStartup fetch failed for '{keyword}': {e}")
    return jobs


# ── DevJobStore (developer-focused) ──────────────────────────────────────────
def fetch_devjobstore(keyword: str) -> list:
    """Fetch jobs from DevJobStore.com via scraper."""
    jobs = []
    try:
        url = f"https://devjobstore.com/search?q={keyword}&remote=true"
        md = html_to_markdown(url)
        if not md:
            return jobs
        import re
        pattern = r'\[([^\]]{10,100})\]\((https://devjobstore\.com/job/[^\)]+)\)'
        matches = re.findall(pattern, md)
        seen = set()
        for title, job_url in matches:
            if job_url in seen:
                continue
            seen.add(job_url)
            pos = md.find(job_url)
            company = ""
            salary = ""
            if pos > 0:
                ctx = md[max(0, pos-200):pos+400]
                comp_match = re.search(r'\*\*([^*]{3,40})\*\*', ctx)
                if comp_match:
                    company = comp_match.group(1)
                sal_match = re.search(r'\$[\d,]+\s*[-–]\s*\$[\d,]+', ctx)
                if sal_match:
                    salary = sal_match.group(0)
            jobs.append({
                "title": title.strip()[:100],
                "company": company,
                "location": "Remote",
                "salary": salary,
                "url": job_url,
                "source": "DevJobStore",
                "keyword": keyword,
                "posted": "",
                "tags": keyword,
            })
        print(f"  DevJobStore: {len(jobs)} jobs for '{keyword}'")
    except Exception as e:
        print(f"  Warning: DevJobStore fetch failed for '{keyword}': {e}")
    return jobs


def parse_salary(salary_str: str) -> int:
    """Extract numeric salary from string."""
    import re
    if not salary_str:
        return 0
    nums = re.findall(r'[\d,]+', salary_str.replace(",", ""))
    if nums:
        try:
            return max(int(n) for n in nums if int(n) > 1000)
        except ValueError:
            return 0
    return 0


def load_previous_urls() -> set:
    """Load previously seen job URLs from history."""
    history_file = OUTPUT_DIR / "job_postings_history.csv"
    urls = set()
    if history_file.exists():
        with open(history_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url"):
                    urls.add(row["url"])
    return urls


def save_jobs(jobs: list):
    """Save latest job snapshot."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / "job_postings.csv"
    fieldnames = ["title", "company", "location", "salary", "url", "source", "keyword", "posted", "tags", "scraped_at"]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            row = {**job, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            writer.writerow(row)
    print(f"  Saved {len(jobs)} jobs to {filepath}")


def append_history(jobs: list):
    """Append to history CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / "job_postings_history.csv"
    fieldnames = ["title", "company", "location", "salary", "url", "source", "keyword", "posted", "tags", "scraped_at"]
    file_exists = filepath.exists()
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for job in jobs:
            row = {**job, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            writer.writerow(row)
    print(f"  Appended {len(jobs)} rows to {filepath}")


class JobPostingScraper:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, boards=None, keywords=None, min_salary=DEFAULT_MIN_SALARY, **kwargs):
        self.boards = boards or ["remotive", "weworkremotely"]
        self.keywords = keywords or ["python", "react", "next.js", "typescript"]
        self.min_salary = min_salary

    async def run(self, **kwargs):
        main(boards=self.boards, keywords=self.keywords, min_salary=self.min_salary)
        return [{"source": "jobs", "count": 0}]


def archive_old_jobs(max_age_days: int = 30):
    """Move jobs older than max_age_days from job_postings.csv to archive file."""
    filepath = OUTPUT_DIR / "job_postings.csv"
    archive_path = OUTPUT_DIR / "job_postings_archive.csv"
    if not filepath.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=max_age_days)
    fieldnames = ["title", "company", "location", "salary", "url", "source", "keyword", "posted", "tags", "scraped_at"]

    keep = []
    archive = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scraped = row.get("scraped_at", "")
            try:
                dt = datetime.strptime(scraped, "%Y-%m-%d %H:%M:%S") if scraped else datetime.now()
            except ValueError:
                dt = datetime.now()
            if dt < cutoff:
                archive.append(row)
            else:
                keep.append(row)

    if not archive:
        return 0

    # Write kept jobs back to main file
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in keep:
            writer.writerow(row)

    # Append archived jobs to archive file
    file_exists = archive_path.exists()
    with open(archive_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in archive:
            writer.writerow(row)

    print(f"  Archived {len(archive)} old jobs (>{max_age_days} days) to {archive_path.name}")
    print(f"  Kept {len(keep)} recent jobs in {filepath.name}")
    return len(archive)


def main(boards=None, keywords=None, min_salary=DEFAULT_MIN_SALARY, output_dir=None):
    if boards is None:
        boards = ["remotive", "weworkremotely"]
    elif isinstance(boards, str):
        boards = [b.strip() for b in boards.split(",")]
    if keywords is None:
        keywords = ["python", "react", "next.js", "typescript"]
    elif isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",")]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Job Posting Scraper")
    print(f"  Boards: {boards} | Keywords: {keywords}")
    if min_salary:
        print(f"  Min salary: ${min_salary:,}/year")

    all_jobs = []
    seen_urls = set()

    for keyword in keywords:
        print(f"\n  Searching: {keyword}...")

        for board in boards:
            board = board.strip()
            if board == "remotive":
                jobs = fetch_remotive(keyword)
            elif board == "weworkremotely":
                jobs = fetch_weworkremotely(keyword)
            elif board == "remoteok":
                jobs = fetch_remoteok(keyword)
            elif board == "remoteok-api":
                jobs = fetch_remoteok_api(keyword)
            elif board == "himalayas":
                jobs = fetch_himalayas(keyword)
            elif board == "jobicy":
                jobs = fetch_jobicy(keyword)
            elif board == "landing-jobs":
                jobs = fetch_landing_jobs(keyword)
            elif board == "indeed":
                jobs = fetch_indeed(keyword)
            elif board == "seek-au":
                jobs = fetch_seek(keyword, country="au")
            elif board == "seek-nz":
                jobs = fetch_seek(keyword, country="nz")
            elif board == "jobthai":
                jobs = fetch_jobthai(keyword)
            elif board == "jobsdb-th":
                jobs = fetch_jobsdb_th(keyword)
            elif board == "jobbkk":
                jobs = fetch_jobbkk(keyword)
            elif board == "hn-hiring":
                jobs = fetch_hn_who_is_hiring(keyword)
            elif board == "upwork":
                jobs = fetch_upwork(keyword)
            elif board == "fastwork":
                jobs = fetch_fastwork(keyword)
            elif board == "fiverr":
                jobs = fetch_fiverr(keyword)
            elif board == "toptal":
                jobs = fetch_toptal(keyword)
            elif board == "linkedin":
                jobs = fetch_linkedin(keyword)
            elif board == "glassdoor":
                jobs = fetch_glassdoor(keyword)
            elif board == "arc":
                jobs = fetch_arc(keyword)
            elif board == "workingnomads":
                jobs = fetch_workingnomads(keyword)
            elif board == "turing":
                jobs = fetch_turing(keyword)
            elif board == "themuse":
                jobs = fetch_themuse(keyword)
            elif board == "wellfound":
                jobs = fetch_wellfound(keyword)
            elif board == "otta":
                jobs = fetch_otta(keyword)
            elif board == "dice":
                jobs = fetch_dice(keyword)
            elif board == "builtin":
                jobs = fetch_builtin(keyword)
            elif board == "remoteco":
                jobs = fetch_remoteco(keyword)
            elif board == "jobspresso":
                jobs = fetch_jobspresso(keyword)
            elif board == "workatastartup":
                jobs = fetch_workatastartup(keyword)
            elif board == "devjobstore":
                jobs = fetch_devjobstore(keyword)
            else:
                print(f"  Unknown board: {board}")
                continue

            print(f"    {board}: {len(jobs)} jobs")
            all_jobs.extend(jobs)

    # Deduplicate by URL
    unique_jobs = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            unique_jobs.append(job)
        elif not job["url"]:
            unique_jobs.append(job)

    # Filter by salary if set
    if min_salary > 0:
        unique_jobs = [j for j in unique_jobs if parse_salary(j.get("salary", "")) >= min_salary]
        print(f"\n  After salary filter: {len(unique_jobs)} jobs")

    # Detect new jobs
    previous_urls = load_previous_urls()
    new_jobs = [j for j in unique_jobs if j["url"] not in previous_urls]

    save_jobs(unique_jobs)
    append_history(unique_jobs)

    if new_jobs:
        print(f"\n  *** {len(new_jobs)} NEW JOBS detected ***")
        for job in new_jobs[:10]:
            salary = f" | {job['salary']}" if job.get("salary") else ""
            print(f"    {job['title'][:50]:50s} | {job['company'][:20]:20s}{salary}")
    else:
        print(f"\n  No new jobs (all {len(unique_jobs)} seen before)")

    print(f"\n  Total: {len(unique_jobs)} unique jobs from {len(boards)} boards")

    # Auto-archive old jobs
    archived = archive_old_jobs(max_age_days=30)
    if archived:
        print(f"  Auto-archived {archived} old jobs")

    print("  Done.")


if __name__ == "__main__":
    import argparse as _argparse
    _p = _argparse.ArgumentParser(description="Scrape remote job postings")
    _p.add_argument("--boards", default="remoteok-api,himalayas,landing-jobs,jobicy,indeed,seek-au,seek-nz,jobthai,jobsdb-th,jobbkk,hn-hiring,remotive,upwork,fastwork,fiverr,toptal,arc,workingnomads,turing,themuse,wellfound,otta,dice,builtin,remoteco,jobspresso,workatastartup,devjobstore")
    _p.add_argument("--keywords", default="python,react,next.js,typescript,full-stack,developer,AI engineer,backend,frontend,node.js,FastAPI,Django")
    _p.add_argument("--min-salary", type=int, default=0)
    _a = _p.parse_args()
    main(boards=_a.boards, keywords=_a.keywords, min_salary=_a.min_salary)
