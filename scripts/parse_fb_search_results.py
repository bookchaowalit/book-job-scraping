#!/usr/bin/env python3
"""
Parse WebSearch results from Qoder tool for FB job posts.

This script processes pre-fetched search results (from WebSearch tool)
to extract company info and emails.

Usage:
    # 1. First, use WebSearch in Qoder to search for FB job posts
    # 2. Copy the results to a JSON file
    # 3. Run this script to parse and extract companies
    
    python3 scripts/parse_fb_search_results.py results.json
    python3 scripts/parse_fb_search_results.py results.json --apply
"""

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
CONTACT_FILE = DATA_DIR / "contact_emails.json"

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Known generic emails to skip
GENERIC_PREFIXES = {'info', 'support', 'hello', 'contact', 'careers', 'admin', 'sales'}


def extract_emails(text: str) -> list:
    """Extract valid emails from text."""
    emails = EMAIL_RE.findall(text)
    filtered = []
    for email in emails:
        prefix = email.lower().split('@')[0]
        if prefix in GENERIC_PREFIXES:
            continue
        if any(x in email.lower() for x in ['example.com', 'domain.com']):
            continue
        filtered.append(email)
    return list(set(filtered))


def extract_company_name(title: str, snippet: str) -> str:
    """Extract company name from title/snippet."""
    # Common patterns in Thai job posts
    patterns = [
        r'([A-Za-z0-9\s\.\-]+)\s+(?:is hiring|hiring|recruiting|looking for)',
        r'(?:hiring|jobs?|positions?)\s+(?:at|for|from)\s+([A-Za-z0-9\s\.\-]+)',
        r'^([A-Za-z0-9\s\.\-]+)\s*[-–—|]',
        r'บริษัท\s+([^\s]+(?:\s+[^\s]+)*)',  # Thai "บริษัท" prefix
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title + ' ' + snippet, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            company = re.sub(r'\s+', ' ', company)
            if 3 < len(company) < 50:
                return company
    
    return ''


def parse_results(results: list) -> dict:
    """Parse search results and extract company data."""
    companies = {}
    
    for result in results:
        title = result.get('title', '')
        url = result.get('url', '')
        snippet = result.get('snippet', '') or result.get('content', '')
        
        # Only process Facebook URLs
        if 'facebook.com' not in url:
            continue
        
        # Extract company name
        company = extract_company_name(title, snippet)
        if not company:
            continue
        
        # Extract emails
        emails = extract_emails(snippet)
        
        if company not in companies:
            companies[company] = {
                'name': company,
                'emails': emails,
                'source': 'FB search',
                'url': url,
            }
        elif emails and not companies[company]['emails']:
            companies[company]['emails'] = emails
    
    return companies


def add_to_pipeline(companies: dict, dry_run: bool = True):
    """Add companies to contact_emails.json."""
    if not Path(CONTACT_FILE).exists():
        contacts = {}
    else:
        with open(CONTACT_FILE) as f:
            contacts = json.load(f)
    
    new_count = 0
    updated_count = 0
    
    for company, data in companies.items():
        if company in contacts:
            if data['emails'] and not contacts[company].get('emails'):
                contacts[company]['emails'] = data['emails']
                contacts[company]['best'] = data['emails'][0]
                updated_count += 1
                print(f"  Updated: {company} → {data['emails'][0]}")
            continue
        
        emails = data['emails']
        best = emails[0] if emails else None
        
        contacts[company] = {
            'domain': None,
            'emails': emails,
            'best': best,
            'source': data['source'],
        }
        new_count += 1
        
        email_info = best or 'no email'
        print(f"  New: {company} ({email_info})")
    
    print(f"\nSummary:")
    print(f"  New contacts: {new_count}")
    print(f"  Updated contacts: {updated_count}")
    print(f"  Total in DB: {len(contacts)}")
    
    if dry_run:
        print(f"\n[DRY RUN] No changes written. Use --apply to save.")
        return
    
    with open(CONTACT_FILE, 'w') as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)
    print(f"Saved to {CONTACT_FILE}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Parse FB search results')
    parser.add_argument('input_file', help='JSON file with search results')
    parser.add_argument('--apply', action='store_true', help='Write changes to pipeline')
    
    args = parser.parse_args()
    
    print("="*60)
    print("Parse FB Search Results")
    print("="*60)
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Input: {args.input_file}")
    
    with open(args.input_file) as f:
        results = json.load(f)
    
    print(f"Loaded {len(results)} results")
    
    companies = parse_results(results)
    
    print(f"\nDiscovered {len(companies)} companies:")
    for company, data in sorted(companies.items()):
        emails = ', '.join(data['emails'][:2]) if data['emails'] else 'no email'
        print(f"  {company:40s} | {emails}")
    
    add_to_pipeline(companies, dry_run=not args.apply)


if __name__ == '__main__':
    main()
