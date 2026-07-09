#!/usr/bin/env python3
"""Clean extracted contacts and add to contact_emails.json and apply_tracker.csv."""

import re
import json
import csv
from datetime import datetime

BASE = "/home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping"
CONTACTS_FILE = f"{BASE}/data/contact_emails.json"
TRACKER_FILE = f"{BASE}/data/apply_tracker.csv"
RAW_CONTACTS = f"{BASE}/data/hn_may_april_contacts.json"

def clean_company_name(name):
    """Clean up messy company names from HN scraping."""
    # Remove leading dashes and dates like "-05-14" or "-coder2026-05-14"
    name = re.sub(r'^-+\w*\d{4}-\d{2}-\d{2}', '', name)
    name = re.sub(r'^-\d{2}-\d{2}', '', name)
    name = re.sub(r'^-\w+\d{4}-\d{2}-\d{2}', '', name)
    
    # Remove URLs
    name = re.sub(r'https?://[^\s)]+', '', name)
    name = re.sub(r'\(https?://[^\s)]+\)', '', name)
    
    # Remove trailing descriptions after " - "
    if ' - ' in name:
        name = name.split(' - ')[0]
    
    # Clean up whitespace and special chars
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)
    
    # Remove trailing parentheses content
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    
    return name.strip()

def main():
    # Load raw contacts
    with open(RAW_CONTACTS, 'r') as f:
        raw_contacts = json.load(f)
    
    print(f"Loaded {len(raw_contacts)} raw contacts")
    
    # Clean company names
    cleaned = []
    for c in raw_contacts:
        company = clean_company_name(c['company'])
        if company and len(company) > 1:
            c['company_clean'] = company
            cleaned.append(c)
    
    print(f"Cleaned: {len(cleaned)} contacts with valid company names")
    
    # Load existing contacts
    with open(CONTACTS_FILE, 'r') as f:
        contacts_db = json.load(f)
    
    # Add new contacts to contact_emails.json
    added = 0
    for c in cleaned:
        company = c['company_clean']
        email = c['email']
        
        if company not in contacts_db:
            contacts_db[company] = {
                "domain": c['domain'],
                "emails": [email],
                "best": email,
                "source": c['source']
            }
            added += 1
        else:
            # Company exists, add email if not already there
            if email not in contacts_db[company].get('emails', []):
                contacts_db[company]['emails'].append(email)
                if not contacts_db[company].get('best'):
                    contacts_db[company]['best'] = email
    
    print(f"Added {added} new companies to contact_emails.json")
    
    # Save updated contacts
    with open(CONTACTS_FILE, 'w') as f:
        json.dump(contacts_db, f, indent=2)
    
    # Load tracker
    tracker = []
    with open(TRACKER_FILE, 'r') as f:
        for row in csv.DictReader(f):
            tracker.append({k: row.get(k, "") for k in ["url", "title", "company", "status", "note", "updated_at"]})
    
    existing_companies = {row['company'].lower() for row in tracker}
    
    # Add new tracker entries
    added_tracker = 0
    now = datetime.now().strftime('%Y-%m-%d')
    
    for c in cleaned:
        company = c['company_clean']
        if company.lower() not in existing_companies:
            tracker.append({
                "url": f"https://{c['domain']}",
                "title": f"HN {c['source']} - {company}",
                "company": company,
                "status": "new",
                "note": f"Email: {c['email']}",
                "updated_at": now
            })
            existing_companies.add(company.lower())
            added_tracker += 1
    
    print(f"Added {added_tracker} new entries to apply_tracker.csv")
    
    # Save tracker
    with open(TRACKER_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["url", "title", "company", "status", "note", "updated_at"], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(tracker)
    
    print(f"\nSummary:")
    print(f"  Total raw contacts: {len(raw_contacts)}")
    print(f"  Cleaned contacts: {len(cleaned)}")
    print(f"  New companies in contact_emails.json: {added}")
    print(f"  New entries in apply_tracker.csv: {added_tracker}")
    print(f"  Total contacts in DB: {len(contacts_db)}")
    print(f"  Total tracker entries: {len(tracker)}")

if __name__ == "__main__":
    main()
