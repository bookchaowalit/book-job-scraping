#!/usr/bin/env python3
"""
Find contact emails for companies from job posting URLs.

Strategy:
1. Extract company domain from job URLs (direct, ATS, or job board)
2. Check /careers, /contact, /about pages for email addresses
3. Score emails by relevance (careers@, hr@, jobs@ get higher scores)
4. Save results to contact_emails.json

Usage:
    python3 scripts/find_contact_emails.py                    # Find all
    python3 scripts/find_contact_emails.py --company "phData" # Single company
    python3 scripts/find_contact_emails.py --limit 20         # First 20
    python3 scripts/find_contact_emails.py --from-followups   # Only companies with followup emails
"""

import csv
import json
import os
import re
import socket
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
OUTPUT_FILE = DATA_DIR / "contact_emails.json"

# ── Config ────────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')

# Noise domains to ignore (not real contact emails)
NOISE_DOMAINS = {
    'example.com', 'sentry.io', 'webpack.js.org', 'schema.org', 'w3.org',
    'googleapis.com', 'cloudflare.com', 'wix.com', 'email.com', 'github.com',
    'twitter.com', 'facebook.com', 'linkedin.com', 'youtube.com',
    'gravatar.com', 'wordpress.org', 'wordpress.com', 'gstatic.com',
    'google.com', 'google-analytics.com', 'googletagmanager.com',
    'jsdelivr.net', 'unpkg.com', 'cdnjs.com', 'npmjs.com',
}

# Noise domain patterns
NOISE_DOMAIN_PATTERNS = ['sentry', 'webpack', 'wixpress', 'new-sentry', 'track', 'analytics']

# TLDs that are never real email domains
NOISE_TLDS = {'.webp', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.mp', '.mp4', '.mov', '.avi', '.pdf'}

# Known platform emails (not the company's own contact)
PLATFORM_EMAILS = {
    'support@bamboohr.com',  # BambooHR platform
    'noreply@bamboohr.com',
}

# High-value email prefixes (more likely to be real contact)
HIGH_VALUE_PREFIXES = {'careers', 'hr', 'jobs', 'recruiting', 'talent', 'people', 'hiring', 'apply'}
MEDIUM_VALUE_PREFIXES = {'contact', 'info', 'hello', 'hi', 'team', 'office', 'support'}

# ATS platforms → how to extract company slug
ATS_PATTERNS = {
    'greenhouse.io': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'eu.greenhouse.io': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'applytojob.com': lambda host: host.split('.')[0],
    'smartrecruiters.com': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'eightfold.ai': lambda path: None,  # Hard to extract
    'ashbyhq.com': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'lever.co': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'myworkdayjobs.com': lambda path: None,
    'breezy.hr': lambda path: path.strip('/').split('/')[0] if path.strip('/') else None,
    'workable.com': lambda path: None,
}

# Job boards that don't have company domains
JOB_BOARDS = {
    'jobicy.com', 'remoteok.com', 'remotive.com', 'himalayas.app',
    'arc.dev', 'landing.jobs', 'themuse.com', 'dice.com',
    'workingnomads.com', 'remote.working',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

CHECK_PATHS = ['/careers', '/contact', '/about', '/company', '/about-us', '/']


# ── Domain extraction ─────────────────────────────────────────────────────────

def clean_company_name(name: str) -> str:
    """Clean company name for domain guessing."""
    import html
    # Decode HTML entities first
    name = html.unescape(name)
    # Remove special chars, trademarks
    name = name.replace('&', '').replace('®', '').replace('™', '')
    name = name.replace('.', '').replace(',', '').replace("'", '').replace('"', '')
    name = name.replace('(', '').replace(')', '').replace('-', '')
    name = name.strip()
    return name


def guess_domains(company: str) -> list[str]:
    """Guess possible company domains from name."""
    cleaned = clean_company_name(company)
    if not cleaned:
        return []

    # If company name already looks like a domain (e.g. "Lenskart.com")
    if '.' in company and ' ' not in company:
        return [company.lower()]

    # Generate slug
    slug = re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()
    if not slug:
        return []

    # Try common TLDs
    candidates = []
    for tld in ['.com', '.io', '.co', '.ai', '.tech']:
        candidates.append(slug + tld)

    return candidates


def verify_domain(domain: str) -> bool:
    """Check if a domain resolves (has DNS + responds to HTTPS)."""
    try:
        # Quick DNS check
        socket.getaddrinfo(domain, 443, socket.AF_INET)
        # Try HTTPS
        resp = httpx.head(
            f"https://{domain}/",
            follow_redirects=True,
            timeout=8,
            headers=HEADERS,
        )
        return resp.status_code < 500
    except Exception:
        return False


def extract_domain_from_url(url: str) -> str | None:
    """Extract the most likely company domain from a job URL."""
    if not url:
        return None

    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    path = parsed.path.strip('/')

    if not host:
        return None

    # Check if it's an ATS URL → extract company slug
    for ats_host, extractor in ATS_PATTERNS.items():
        if ats_host in host:
            slug = extractor(path) if 'path' in extractor.__code__.co_varnames else extractor(host)
            if slug:
                for tld in ['.com', '.io', '.co', '.ai']:
                    domain = slug.lower() + tld
                    return domain
            return None

    # Check if it's a job board → can't extract company domain
    for jb in JOB_BOARDS:
        if jb in host:
            return None

    # Direct company URL
    domain = host.replace('www.', '')
    return domain


def is_valid_email(email: str) -> bool:
    """Check if an email looks like a real contact email."""
    # Skip known platform emails
    if email.lower() in PLATFORM_EMAILS:
        return False

    local, domain = email.rsplit('@', 1)
    domain_lower = domain.lower()

    # Skip noise domains
    if domain_lower in NOISE_DOMAINS:
        return False

    # Skip noise domain patterns
    if any(p in domain_lower for p in NOISE_DOMAIN_PATTERNS):
        return False

    # Skip image/file extensions
    for tld in NOISE_TLDS:
        if domain_lower.endswith(tld):
            return False

    # Skip if local part is too long (likely hash/tracking)
    if len(local) > 30:
        return False

    # Skip if local part is all hex (likely tracking ID)
    if re.match(r'^[a-f0-9]{16,}$', local):
        return False

    # Skip if local part contains numbers with dashes (likely filename like "720p-nov2025")
    if re.search(r'\d+[a-z]*-', local, re.I):
        return False

    # Skip if domain has no dot (invalid)
    if '.' not in domain:
        return False

    # Skip if TLD is too long or short
    tld = domain.rsplit('.', 1)[-1]
    if len(tld) < 2 or len(tld) > 6:
        return False

    return True


def score_email(email: str) -> int:
    """Score an email by how likely it is a useful contact."""
    local = email.split('@')[0].lower()
    domain = email.split('@')[1].lower()

    # Skip noise
    if domain in NOISE_DOMAINS:
        return -1

    # High value: careers@, hr@, jobs@, etc.
    if local in HIGH_VALUE_PREFIXES:
        return 10
    # Medium value: contact@, info@, hello@
    if local in MEDIUM_VALUE_PREFIXES:
        return 5
    # Personal-looking: first.last@, first@
    if '.' in local or len(local) < 10:
        return 3
    # Generic/unknown
    return 1


# ── Email finding ─────────────────────────────────────────────────────────────

def find_emails_on_page(client: httpx.Client, url: str) -> set[str]:
    """Fetch a page and extract email addresses."""
    try:
        resp = client.get(url, follow_redirects=True, timeout=12)
        if resp.status_code >= 400:
            return set()
        emails = set(EMAIL_RE.findall(resp.text))
        # Filter using validation
        return {e for e in emails if is_valid_email(e)}
    except Exception:
        return set()


def find_contact_email(client: httpx.Client, domain: str) -> dict:
    """Check common pages on a domain for contact emails."""
    all_emails = {}  # email → score

    for path in CHECK_PATHS:
        url = f"https://{domain}{path}"
        emails = find_emails_on_page(client, url)
        for email in emails:
            s = score_email(email)
            if s > 0 and email not in all_emails:
                all_emails[email] = s

    if not all_emails:
        return {"domain": domain, "emails": [], "best": None}

    # Sort by score
    sorted_emails = sorted(all_emails.items(), key=lambda x: -x[1])
    return {
        "domain": domain,
        "emails": [e for e, _ in sorted_emails[:5]],
        "best": sorted_emails[0][0] if sorted_emails else None,
        "best_score": sorted_emails[0][1] if sorted_emails else 0,
    }


# ── Company → URL mapping ─────────────────────────────────────────────────────

def build_company_urls() -> dict[str, list[str]]:
    """Build mapping of company → URLs from all data sources."""
    companies = {}

    # apply_tracker.csv
    tracker_file = DATA_DIR / "apply_tracker.csv"
    if tracker_file.exists():
        with open(tracker_file) as f:
            for row in csv.DictReader(f):
                c = row.get('company', '').strip()
                url = row.get('url', '').strip()
                if c and url:
                    companies.setdefault(c, set()).add(url)

    # job_postings.csv
    postings_file = DATA_DIR / "job_postings.csv"
    if postings_file.exists():
        with open(postings_file) as f:
            for row in csv.DictReader(f):
                c = row.get('company', '').strip()
                url = row.get('url', '').strip()
                if c and url:
                    companies.setdefault(c, set()).add(url)

    # matched_jobs.csv
    matched_file = DATA_DIR / "matched_jobs.csv"
    if matched_file.exists():
        with open(matched_file) as f:
            for row in csv.DictReader(f):
                c = row.get('company', '').strip()
                url = row.get('url', '').strip()
                if c and url:
                    companies.setdefault(c, set()).add(url)

    return {c: list(urls) for c, urls in companies.items()}


def get_followup_companies() -> set[str]:
    """Get company names from followup email files."""
    email_dir = DATA_DIR / "followup_emails"
    if not email_dir.exists():
        return set()

    companies = set()
    for f in email_dir.glob("*.txt"):
        # Pattern: followup_{Company}_{date}.txt
        parts = f.stem.split('_')
        if len(parts) >= 2:
            company = '_'.join(parts[1:-1])  # Skip 'followup' prefix and date suffix
            companies.add(company)
    return companies


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Find contact emails for companies")
    parser.add_argument("--company", type=str, help="Single company name")
    parser.add_argument("--limit", type=int, default=0, help="Max companies to process")
    parser.add_argument("--from-followups", action="store_true", help="Only companies with followup emails")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    parser.add_argument("--save", action="store_true", help="Save results to contact_emails.json")
    parser.add_argument("--batch", type=int, default=0, help="Process N companies per batch")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N companies")
    parser.add_argument("--save-each", action="store_true", help="Save after each company (crash-safe)")
    args = parser.parse_args()

    # Load existing results
    existing = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)

    # Build company → URL mapping
    company_urls = build_company_urls()
    print(f"Loaded {len(company_urls)} companies with URLs")

    # Filter
    if args.from_followups:
        followup_companies = get_followup_companies()
        company_urls = {c: urls for c, urls in company_urls.items() if c in followup_companies}
        print(f"Filtered to {len(company_urls)} companies with followup emails")

    if args.company:
        company_urls = {args.company: company_urls.get(args.company, [])}

    # Sort companies for consistent batching
    all_companies = sorted(company_urls.items())

    # Apply offset
    if args.offset > 0:
        all_companies = all_companies[args.offset:]
        print(f"Skipped {args.offset} companies (offset)")

    # Apply batch limit
    if args.batch > 0:
        all_companies = all_companies[:args.batch]

    company_urls = dict(all_companies)

    if args.limit > 0:
        items = list(company_urls.items())[:args.limit]
        company_urls = dict(items)

    print(f"Processing {len(company_urls)} companies...")
    print()

    results = dict(existing)  # Keep existing results
    found = 0
    not_found = 0
    already_known = 0

    with httpx.Client(headers=HEADERS) as client:
        for i, (company, urls) in enumerate(sorted(company_urls.items()), 1):
            # Skip if already found
            if company in results and results[company].get('best'):
                already_known += 1
                continue

            # Try to extract domain from each URL
            domains_tried = []
            best_result = None

            for url in urls:
                domain = extract_domain_from_url(url)
                if domain and domain not in domains_tried:
                    domains_tried.append(domain)
                    result = find_contact_email(client, domain)
                    if result['best']:
                        best_result = result
                        best_result['source_url'] = url
                        break  # Found one, stop trying other URLs
                    time.sleep(args.delay * 0.5)

            # If no domain found from URLs, try guessing from company name
            if not best_result and not domains_tried:
                guessed = guess_domains(company)
                for domain in guessed[:3]:  # Try max 3 TLDs
                    if domain in domains_tried:
                        continue
                    domains_tried.append(domain)
                    if verify_domain(domain):
                        result = find_contact_email(client, domain)
                        if result['best']:
                            best_result = result
                            best_result['source'] = 'guessed'
                            break
                        time.sleep(args.delay * 0.5)
                    else:
                        time.sleep(args.delay * 0.3)

            if best_result:
                results[company] = best_result
                found += 1
                print(f"[{i}/{len(company_urls)}] ✓ {company}: {best_result['best']} (from {best_result['domain']})")
            else:
                results[company] = {"domain": None, "emails": [], "best": None, "urls_tried": domains_tried}
                not_found += 1
                domain_info = domains_tried[0] if domains_tried else "no domain"
                print(f"[{i}/{len(company_urls)}] ✗ {company} ({domain_info})")

            # Incremental save
            if args.save_each:
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

            time.sleep(args.delay)

    # Summary
    print()
    print(f"═══ Summary ═══")
    print(f"  Found:     {found}")
    print(f"  Not found: {not_found}")
    print(f"  Already:   {already_known}")
    print(f"  Total:     {len(results)}")

    # Save
    if args.save or not args.company:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved to: {OUTPUT_FILE}")

    # Show stats
    with_email = sum(1 for v in results.values() if v.get('best'))
    print(f"\n  Companies with email: {with_email}/{len(results)}")


if __name__ == "__main__":
    main()
