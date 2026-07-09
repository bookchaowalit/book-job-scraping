#!/usr/bin/env python3
"""
Auto-apply pipeline for discovered jobs.

Reads discovered jobs from apply_tracker, prioritizes them,
and prepares application packages.

Usage:
    python3 scripts/prepare_applications.py                    # Show priorities
    python3 scripts/prepare_applications.py --apply-top 10     # Prepare top 10
    python3 scripts/prepare_applications.py --company "Reddit" # Filter by company
"""

import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Import email templates
try:
    from email_templates import generate_application_email, is_thai_company
except ImportError:
    # Fallback if email_templates not available
    def generate_application_email(company, title, is_thai=False, source=''):
        return {'subject': f'Application for {title}', 'body': 'Dear Hiring Team,', 'language': 'en'}
    def is_thai_company(name):
        return False

# Import previous employers blocklist
try:
    from send_application_emails import PREVIOUS_EMPLOYERS
except ImportError:
    PREVIOUS_EMPLOYERS = set()


def is_previous_employer(company: str) -> bool:
    """Check if company matches a previous employer (case-insensitive partial match)."""
    c = company.lower().strip()
    return any(pe in c or c in pe for pe in PREVIOUS_EMPLOYERS)

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"
CONTACTS_FILE = DATA_DIR / "contact_emails.json"
APPLICATIONS_DIR = DATA_DIR / "applications"

# Keywords that indicate high-value jobs
HIGH_VALUE_KEYWORDS = [
    'senior', 'staff', 'principal', 'lead', 'architect',
    'remote', 'distributed',
    'python', 'golang', 'rust', 'typescript', 'react', 'node',
    'data', 'ml', 'ai', 'machine learning',
    'backend', 'fullstack', 'full-stack',
]

# Companies with multiple openings (prioritize)
PRIORITY_COMPANIES = ['Canonical', 'Reddit', 'Figma', 'Grafanalabs', 'TELUS Digital']


def load_discovered_jobs() -> list[dict]:
    """Load discovered jobs from tracker."""
    if not TRACKER_FILE.exists():
        return []
    
    jobs = []
    with open(TRACKER_FILE) as f:
        for row in csv.DictReader(f):
            if row.get('status') == 'discovered':
                jobs.append(row)
    return jobs


def load_contact_emails() -> dict:
    """Load contact emails for companies."""
    if not CONTACTS_FILE.exists():
        return {}
    return json.loads(CONTACTS_FILE.read_text())


def score_job(job: dict, contacts: dict) -> int:
    """Score a job by priority."""
    score = 0
    company = job.get('company', '').lower()
    title = job.get('title', '').lower()
    url = job.get('url', '')
    
    # Has contact email (can follow up)
    if company in contacts and contacts[company].get('best'):
        score += 10
    
    # Priority company
    for pc in PRIORITY_COMPANIES:
        if pc.lower() in company:
            score += 5
            break
    
    # High-value keywords in title
    for kw in HIGH_VALUE_KEYWORDS:
        if kw in title:
            score += 2
    
    # ATS platform (direct application possible)
    host = urlparse(url).hostname or ''
    if 'greenhouse' in host or 'lever.co' in host or 'ashbyhq' in host:
        score += 3
    
    # Senior/Staff level
    if any(level in title for level in ['senior', 'staff', 'principal', 'lead']):
        score += 5
    
    return score


def get_application_url(url: str) -> str:
    """Get the direct application URL for a job."""
    host = urlparse(url).hostname or ''
    
    # ATS platforms have direct apply URLs
    if 'greenhouse' in host:
        return url  # Already direct
    if 'lever.co' in host:
        return url
    if 'ashbyhq' in host:
        return url
    
    # Job boards - need to find the apply link
    # For now, return the job page URL
    return url


def prepare_application(job: dict, contacts: dict) -> dict:
    """Prepare an application package for a job."""
    company = job.get('company', '')
    title = job.get('title', '')
    url = job.get('url', '')
    source = job.get('source', '')
    
    # Get contact email if available
    contact_email = ''
    company_key = company.lower()
    if company_key in contacts and contacts[company_key].get('best'):
        contact_email = contacts[company_key]['best']
    
    # Detect if Thai company
    is_thai = is_thai_company(company)
    
    # Generate application email
    email = generate_application_email(company, title, is_thai=is_thai, source=source)
    
    return {
        'company': company,
        'title': title,
        'url': url,
        'apply_url': get_application_url(url),
        'contact_email': contact_email,
        'email_subject': email['subject'],
        'email_body': email['body'],
        'email_language': email['language'],
        'is_thai_company': is_thai,
        'prepared_at': datetime.now().isoformat(),
        'status': 'ready',
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Prepare job applications")
    parser.add_argument("--apply-top", type=int, default=0, help="Prepare top N jobs")
    parser.add_argument("--company", type=str, help="Filter by company name")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum score threshold")
    parser.add_argument("--dry-run", action="store_true", help="Don't save")
    args = parser.parse_args()
    
    # Load data
    jobs = load_discovered_jobs()
    contacts = load_contact_emails()
    
    print(f"Loaded {len(jobs)} discovered jobs")
    print(f"Loaded {len(contacts)} company contacts")
    
    # Score jobs
    scored_jobs = []
    skipped_employer = 0
    for job in jobs:
        company = job.get('company', '')
        # Skip previous employers
        if is_previous_employer(company):
            skipped_employer += 1
            continue
        score = score_job(job, contacts)
        if score >= args.min_score:
            scored_jobs.append((score, job))
    
    if skipped_employer:
        print(f"Skipped {skipped_employer} jobs from previous employers")
    
    # Sort by score
    scored_jobs.sort(reverse=True, key=lambda x: x[0])
    
    # Filter by company
    if args.company:
        scored_jobs = [(s, j) for s, j in scored_jobs 
                       if args.company.lower() in j.get('company', '').lower()]
    
    # Limit
    if args.apply_top > 0:
        scored_jobs = scored_jobs[:args.apply_top]
    
    # Display
    print(f"\n{'='*70}")
    print(f"  TOP PRIORITIES ({len(scored_jobs)} jobs)")
    print(f"{'='*70}\n")
    
    for i, (score, job) in enumerate(scored_jobs[:30], 1):
        company = job.get('company', '?')
        title = job.get('title', '?')
        url = job.get('url', '')
        has_email = '✓' if contacts.get(company.lower(), {}).get('best') else '✗'
        
        print(f"{i:3d}. [{score:2d}] {company[:25]:25s} | {title[:40]:40s} | {has_email}")
        print(f"     {url[:70]}")
    
    # Prepare applications
    if args.apply_top > 0 and not args.dry_run:
        APPLICATIONS_DIR.mkdir(exist_ok=True)
        
        prepared = []
        for score, job in scored_jobs:
            app = prepare_application(job, contacts)
            app['score'] = score
            prepared.append(app)
        
        # Save applications
        apps_file = APPLICATIONS_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(apps_file, 'w') as f:
            json.dump(prepared, f, indent=2)
        
        print(f"\n✓ Prepared {len(prepared)} applications")
        print(f"  Saved to: {apps_file}")
        
        # Update tracker status
        updated = 0
        rows = []
        with open(TRACKER_FILE) as f:
            rows = list(csv.DictReader(f))
        
        apply_urls = {app['url'] for app in prepared}
        for row in rows:
            if row.get('url') in apply_urls and row.get('status') == 'discovered':
                row['status'] = 'ready_to_apply'
                updated += 1
        
        if updated > 0:
            fieldnames = list(rows[0].keys())
            with open(TRACKER_FILE, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"  Updated {updated} tracker entries to 'ready_to_apply'")


if __name__ == "__main__":
    main()
