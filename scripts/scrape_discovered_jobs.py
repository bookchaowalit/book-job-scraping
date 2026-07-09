#!/usr/bin/env python3
"""
Scrape discovered job URLs to extract company name and job title.

Reads apply_tracker.csv entries with status='discovered', fetches each URL,
extracts company + title from HTML meta tags / page content, and updates
the tracker with the extracted data.

Usage:
    python3 scripts/scrape_discovered_jobs.py                  # Process all
    python3 scripts/scrape_discovered_jobs.py --limit 20       # First 20
    python3 scripts/scrape_discovered_jobs.py --dry-run        # Don't save
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip3 install --user httpx")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# ── Extraction patterns per job board ─────────────────────────────────────────

def extract_from_remoteok(url: str, html: str) -> dict:
    """Extract from remoteok.com URLs."""
    # URL pattern: /remote-jobs/remote-data-scientist-producer
    path = urlparse(url).path.strip('/')
    slug = path.split('/')[-1] if path else ''
    title = slug.replace('-', ' ').replace('remote', '').strip().title() if slug else ''

    # Try og:title
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip()

    # Try to find company from og:description or page content
    company = ''
    og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_desc:
        desc = og_desc.group(1)
        # "Company is looking for a Title..." pattern
        m = re.search(r'^(\S+)\s+is\s+(?:looking|hiring|seeking)', desc)
        if m:
            company = m.group(1)
        else:
            # Try first word that looks like a company
            m = re.search(r'(?:at|by|from|@)\s+([A-Z][a-zA-Z0-9\s]+?)(?:\s+is|\s+is\s+looking|\s+has)', desc)
            if m:
                company = m.group(1).strip()

    # Try JSON-LD
    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_greenhouse(url: str, html: str) -> dict:
    """Extract from greenhouse.io job boards."""
    # URL: job-boards.greenhouse.io/{company}/jobs/{id}
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    company = parts[0] if parts else ''
    company = company.replace('-', ' ').title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip()
    else:
        t = re.search(r'<title>([^<]+)', html, re.I)
        if t:
            title = t.group(1).strip()
            # Remove " - Company" suffix
            title = re.sub(r'\s*[-–|]\s*\S+$', '', title)

    return {'title': title, 'company': company}


def extract_from_lever(url: str, html: str) -> dict:
    """Extract from lever.co job pages."""
    # URL: jobs.lever.co/{company}/{id}
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    company = parts[0] if len(parts) > 0 else ''
    company = company.replace('-', ' ').title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip()

    return {'title': title, 'company': company}


def extract_from_ashby(url: str, html: str) -> dict:
    """Extract from ashbyhq.com job pages."""
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    company = parts[0] if parts else ''
    company = company.replace('-', ' ').title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip()

    return {'title': title, 'company': company}


def extract_from_smartrecruiters(url: str, html: str) -> dict:
    """Extract from smartrecruiters.com."""
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    company = parts[0] if parts else ''
    company = company.replace('-', ' ').title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip()

    return {'title': title, 'company': company}


def extract_from_himalayas(url: str, html: str) -> dict:
    """Extract from himalayas.app."""
    title = ''
    company = ''

    og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_title:
        raw = og_title.group(1).strip()
        # "Company is hiring a Title | Himalayas"
        m = re.match(r'^(.+?)\s+is\s+hiring\s+(.+?)(?:\s*[|–-])?', raw)
        if m:
            company = m.group(1).strip()
            title = m.group(2).strip()
        else:
            title = raw.split('|')[0].strip()

    # Try JSON-LD
    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_arc(url: str, html: str) -> dict:
    """Extract from arc.dev."""
    title = ''
    company = ''

    og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_title:
        title = og_title.group(1).strip().split('|')[0].strip()

    og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_desc:
        desc = og_desc.group(1)
        m = re.search(r'(?:at|by|from)\s+([A-Z][A-Za-z0-9\s]+?)(?:\s*[•|–-]|\s+is)', desc)
        if m:
            company = m.group(1).strip()

    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_themuse(url: str, html: str) -> dict:
    """Extract from themuse.com."""
    title = ''
    company = ''

    og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_title:
        raw = og_title.group(1).strip()
        # "Company: Title" or "Company is hiring a Title"
        m = re.match(r'^(.+?):\s*(.+)', raw)
        if m:
            company = m.group(1).strip()
            title = m.group(2).strip()
        else:
            title = raw.split('|')[0].strip()

    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_remotive(url: str, html: str) -> dict:
    """Extract from remotive.com."""
    title = ''
    company = ''

    og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og_title:
        title = og_title.group(1).strip().split('|')[0].strip()

    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_landing(url: str, html: str) -> dict:
    """Extract from landing.jobs."""
    # URL: landing.jobs/at/{company}/{slug}
    path = urlparse(url).path.strip('/')
    parts = path.split('/')
    company = ''
    if len(parts) >= 2 and parts[0] == 'at':
        company = parts[1].replace('-', ' ').title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip().split('|')[0].strip()

    return {'title': title, 'company': company}


def extract_from_jobicy(url: str, html: str) -> dict:
    """Extract from jobicy.com."""
    title = ''
    company = ''

    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        raw = og.group(1).strip()
        # "Remote Title @ Company"
        m = re.match(r'(.+?)\s*@\s*(.+)', raw)
        if m:
            title = m.group(1).strip()
            company = m.group(2).strip()
        else:
            title = raw.split('|')[0].strip()

    if not company:
        ld = re.search(r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)
        if ld:
            company = ld.group(1)

    return {'title': title, 'company': company}


def extract_from_direct(url: str, html: str) -> dict:
    """Extract from direct company URLs (e.g. stripe.com, airbnb.com)."""
    domain = urlparse(url).hostname or ''
    company = domain.replace('www.', '').split('.')[0].title()

    title = ''
    og = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html, re.I)
    if og:
        title = og.group(1).strip().split('|')[0].strip()
    if not title:
        t = re.search(r'<title>([^<]+)', html)
        if t:
            title = t.group(1).strip().split('|')[0].strip()

    return {'title': title, 'company': company}


# ── Router ────────────────────────────────────────────────────────────────────

EXTRACTORS = {
    'remoteok.com': extract_from_remoteok,
    'remoteok.io': extract_from_remoteok,
    'greenhouse.io': extract_from_greenhouse,
    'jobs.lever.co': extract_from_lever,
    'lever.co': extract_from_lever,
    'ashbyhq.com': extract_from_ashby,
    'smartrecruiters.com': extract_from_smartrecruiters,
    'himalayas.app': extract_from_himalayas,
    'arc.dev': extract_from_arc,
    'themuse.com': extract_from_themuse,
    'remotive.com': extract_from_remotive,
    'landing.jobs': extract_from_landing,
    'jobicy.com': extract_from_jobicy,
}


def extract_job_info(url: str, html: str) -> dict:
    """Route to the right extractor based on URL domain."""
    host = (urlparse(url).hostname or '').lower().replace('www.', '')

    for pattern, extractor in EXTRACTORS.items():
        if pattern in host:
            return extractor(url, html)

    # Direct company URL
    return extract_from_direct(url, html)


def clean_title(title: str) -> str:
    """Clean up extracted title."""
    if not title:
        return ''
    # Remove trailing site names
    title = re.sub(r'\s*[\|–-]\s*(Himalayas|Arc\.dev|Lever|Greenhouse|The Muse|RemoteOK|Remotive).*$', '', title, flags=re.I)
    # Remove "Remote" prefix/suffix
    title = re.sub(r'^Remote\s+', '', title, flags=re.I)
    title = re.sub(r'\s+Remote$', '', title, flags=re.I)
    return title.strip()


def clean_company(company: str) -> str:
    """Clean up extracted company name."""
    if not company:
        return ''
    # Remove common suffixes
    company = re.sub(r'\s*(Inc|LLC|Ltd|Corp|Co)\.?\s*$', '', company, flags=re.I)
    return company.strip()


# ── URL slug extraction (no HTTP needed) ──────────────────────────────────────

def extract_from_url_slug(url: str) -> dict:
    """Extract company+title purely from URL structure (no HTTP)."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().replace('www.', '')
    path = parsed.path.strip('/')
    parts = path.split('/')

    # arc.dev/remote-jobs/{slug}
    if 'arc.dev' in host:
        slug = parts[-1] if parts else ''
        # Pattern: {company}-{title} or just {title}
        title = slug.replace('-', ' ').title()
        title = re.sub(r'^Remote\s+', '', title, flags=re.I)
        return {'title': title, 'company': '', 'source': 'url_slug'}

    # greenhouse.io/{company}/jobs/{id}
    if 'greenhouse.io' in host:
        company = parts[0].replace('-', ' ').title() if parts else ''
        return {'title': '', 'company': company, 'source': 'url_slug'}

    # lever.co/{company}/{id}
    if 'lever.co' in host:
        company = parts[0].replace('-', ' ').title() if len(parts) > 0 else ''
        return {'title': '', 'company': company, 'source': 'url_slug'}

    # ashbyhq.com/{company}/{id}
    if 'ashbyhq.com' in host:
        company = parts[0].replace('-', ' ').title() if parts else ''
        return {'title': '', 'company': company, 'source': 'url_slug'}

    # smartrecruiters.com/{company}/{id}
    if 'smartrecruiters.com' in host:
        company = parts[0].replace('-', ' ').title() if parts else ''
        return {'title': '', 'company': company, 'source': 'url_slug'}

    # landing.jobs/at/{company}/{slug}
    if 'landing.jobs' in host and len(parts) >= 2 and parts[0] == 'at':
        company = parts[1].replace('-', ' ').title()
        return {'title': '', 'company': company, 'source': 'url_slug'}

    # themuse.com/jobs/listings/{id}#{slug}
    if 'themuse.com' in host:
        frag = parsed.fragment
        if frag:
            slug_parts = frag.split('-')
            # Usually: {company}-{role}
            if len(slug_parts) > 1:
                company = slug_parts[0].title()
                title = ' '.join(slug_parts[1:]).title()
                return {'title': title, 'company': company, 'source': 'url_slug'}

    # remoteok.com/remote-jobs/{slug}
    if 'remoteok.com' in host or 'remoteok.io' in host:
        slug = parts[-1] if parts else ''
        # Pattern: remote-{title}-{at|@}-{company} or remote-{title}
        title = slug.replace('-', ' ').title()
        title = re.sub(r'^Remote\s+', '', title, flags=re.I)
        return {'title': title, 'company': '', 'source': 'url_slug'}

    # himalayas.app/jobs/{slug}
    if 'himalayas.app' in host:
        slug = parts[-1] if parts else ''
        title = slug.replace('-', ' ').title()
        return {'title': title, 'company': '', 'source': 'url_slug'}

    # remotive.com/remote-jobs/{slug}
    if 'remotive.com' in host:
        slug = parts[-1] if parts else ''
        title = slug.replace('-', ' ').title()
        return {'title': title, 'company': '', 'source': 'url_slug'}

    # jobicy.com
    if 'jobicy.com' in host:
        slug = parts[-1] if parts else ''
        title = slug.replace('-', ' ').title()
        return {'title': title, 'company': '', 'source': 'url_slug'}

    # Direct company URL
    domain = host.replace('www.', '')
    company = domain.split('.')[0].title()
    return {'title': '', 'company': company, 'source': 'url_slug'}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape discovered job URLs for company+title")
    parser.add_argument("--limit", type=int, default=0, help="Max URLs to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't save results")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests")
    parser.add_argument("--scrape", action="store_true", help="Also scrape HTML (slower)")
    args = parser.parse_args()

    # Load tracker
    if not TRACKER_FILE.exists():
        print(f"ERROR: {TRACKER_FILE} not found")
        sys.exit(1)

    rows = []
    with open(TRACKER_FILE) as f:
        rows = list(csv.DictReader(f))

    discovered = [r for r in rows if r.get('status') == 'discovered']
    print(f"Total discovered: {len(discovered)}")

    # ── Step 1: Build URL → {company, title} index from existing CSVs ──
    url_index = {}
    for fname in ['matched_jobs.csv', 'job_postings.csv']:
        fpath = DATA_DIR / fname
        if fpath.exists():
            with open(fpath) as f:
                for row in csv.DictReader(f):
                    url = row.get('url', '').strip()
                    company = row.get('company', '').strip()
                    title = row.get('title', '').strip()
                    if url and (company or title):
                        url_index[url] = {'company': company, 'title': title}

    print(f"Loaded {len(url_index)} URL→company mappings from existing CSVs")

    # ── Step 2: Fill from existing data (no HTTP) ──
    filled_from_data = 0
    filled_from_slug = 0
    needs_scrape = []

    for row in discovered:
        url = row.get('url', '').strip()
        if not url:
            continue
        # Already has data?
        if row.get('company', '').strip() and row.get('title', '').strip():
            continue

        # Try existing data
        if url in url_index:
            info = url_index[url]
            row['company'] = info.get('company', row.get('company', ''))
            row['title'] = info.get('title', row.get('title', ''))
            filled_from_data += 1
            continue

        # Try URL slug extraction
        slug_info = extract_from_url_slug(url)
        company = clean_company(slug_info.get('company', ''))
        title = clean_title(slug_info.get('title', ''))

        if company and title:
            row['company'] = company
            row['title'] = title
            filled_from_slug += 1
        elif company or title:
            row['company'] = company
            row['title'] = title
            filled_from_slug += 1
        else:
            needs_scrape.append(row)

    print(f"\nFilled from existing data: {filled_from_data}")
    print(f"Filled from URL slug:      {filled_from_slug}")
    print(f"Needs HTTP scrape:         {len(needs_scrape)}")

    # ── Step 3: HTTP scrape remaining (optional) ──
    scraped = 0
    failed = 0
    if args.scrape and needs_scrape:
        if args.limit > 0:
            needs_scrape = needs_scrape[:args.limit]

        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            for i, row in enumerate(needs_scrape, 1):
                url = row.get('url', '').strip()
                try:
                    resp = client.get(url)
                    if resp.status_code >= 400:
                        print(f"[{i}/{len(needs_scrape)}] ✗ HTTP {resp.status_code}: {url[:60]}")
                        failed += 1
                        time.sleep(args.delay)
                        continue

                    info = extract_job_info(url, resp.text)
                    title = clean_title(info.get('title', ''))
                    company = clean_company(info.get('company', ''))

                    if title or company:
                        row['title'] = title
                        row['company'] = company
                        scraped += 1
                        print(f"[{i}/{len(needs_scrape)}] ✓ {company or '?':25s} | {title or '?'}")
                    else:
                        failed += 1
                        print(f"[{i}/{len(needs_scrape)}] ✗ No data: {url[:60]}")

                except Exception as e:
                    failed += 1
                    print(f"[{i}/{len(needs_scrape)}] ✗ Error: {e}")

                time.sleep(args.delay)

    # ── Save ──
    total_filled = filled_from_data + filled_from_slug + scraped
    if not args.dry_run and total_filled > 0:
        fieldnames = list(rows[0].keys()) if rows else []
        with open(TRACKER_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nSaved to {TRACKER_FILE}")

    # ── Summary ──
    still_empty = sum(1 for r in discovered if not r.get('company','').strip() and not r.get('title','').strip())
    print(f"\n═══ Summary ═══")
    print(f"  Filled from CSV data:  {filled_from_data}")
    print(f"  Filled from URL slug:  {filled_from_slug}")
    print(f"  Filled from scraping:  {scraped}")
    print(f"  Failed:                {failed}")
    print(f"  Still empty:           {still_empty}")
    print(f"  Total filled:          {total_filled}")


if __name__ == "__main__":
    main()
