#!/usr/bin/env python3
"""Extract emails from HN May and April 2026 scraped files."""

import re
import json
from pathlib import Path

# Files
MAY_FILE = "/home/bookchaowalit/.qoder/cache/projects/solo-empire-b022c04b/agent-tools/task-f7f/4b9a8a7a.txt"
APRIL_FILE = "/home/bookchaowalit/.qoder/cache/projects/solo-empire-b022c04b/agent-tools/task-f7f/1ce73e6d.txt"
CONTACTS_FILE = "/home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping/data/contact_emails.json"

def deobfuscate_email(text):
    """Convert [at] to @ and [dot] to ."""
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[dot\]\s*', '.', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+at\s+', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+over at\s+', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+dot\s+', '.', text, flags=re.IGNORECASE)
    return text

def extract_emails_with_context(text, source_month):
    """Extract emails and try to find company names."""
    contacts = []
    
    # Split by job postings (each starts with "- username")
    postings = re.split(r'\n- \w+', text)
    
    for posting in postings:
        if not posting.strip():
            continue
        
        # Deobfuscate first
        posting_clean = deobfuscate_email(posting)
        
        # Find all emails
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', posting_clean)
        
        if not emails:
            continue
        
        # Try to extract company name (usually first line after username)
        lines = posting.strip().split('\n')
        company = None
        for line in lines[:5]:
            # Look for company name patterns
            if '|' in line:
                parts = line.split('|')
                if len(parts) > 1:
                    company = parts[0].strip()
                    break
        
        if not company:
            # Try to find it in first line
            first_line = lines[0] if lines else ""
            match = re.match(r'^([A-Za-z0-9\s]+?)\s*\|', first_line)
            if match:
                company = match.group(1).strip()
        
        # Filter out individual seekers (gmail.com, etc.)
        filtered_emails = []
        for email in emails:
            email = email.lower().strip()
            domain = email.split('@')[1] if '@' in email else ''
            
            # Skip personal email providers
            if domain in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'proton.me']:
                continue
            
            filtered_emails.append(email)
        
        if filtered_emails and company:
            for email in filtered_emails:
                contacts.append({
                    'email': email,
                    'company': company,
                    'source': f'HN {source_month} 2026',
                    'domain': email.split('@')[1]
                })
    
    return contacts

def main():
    all_contacts = []
    
    # Read May file
    print("Reading May 2026 file...")
    with open(MAY_FILE, 'r', encoding='utf-8') as f:
        may_text = f.read()
    may_contacts = extract_emails_with_context(may_text, 'May')
    print(f"Found {len(may_contacts)} contacts in May 2026")
    all_contacts.extend(may_contacts)
    
    # Read April file
    print("Reading April 2026 file...")
    with open(APRIL_FILE, 'r', encoding='utf-8') as f:
        april_text = f.read()
    april_contacts = extract_emails_with_context(april_text, 'April')
    print(f"Found {len(april_contacts)} contacts in April 2026")
    all_contacts.extend(april_contacts)
    
    # Load existing contacts
    print(f"\nLoading existing contacts from {CONTACTS_FILE}...")
    with open(CONTACTS_FILE, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    
    # existing is a dict with company names as keys
    existing_emails = set()
    for company, data in existing.items():
        if data.get('emails'):
            existing_emails.update(data['emails'])
        if data.get('best'):
            existing_emails.add(data['best'])
    
    # Filter new contacts
    new_contacts = []
    for contact in all_contacts:
        if contact['email'] not in existing_emails:
            new_contacts.append(contact)
            existing_emails.add(contact['email'])
    
    print(f"\nTotal contacts found: {len(all_contacts)}")
    print(f"New contacts (not in existing): {len(new_contacts)}")
    
    # Save to file for review
    output_file = "/home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping/data/hn_may_april_contacts.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_contacts, f, indent=2)
    
    print(f"\nSaved {len(new_contacts)} new contacts to:")
    print(output_file)
    
    # Show sample
    print("\nSample contacts:")
    for contact in new_contacts[:10]:
        print(f"  {contact['email']} - {contact['company']}")

if __name__ == "__main__":
    main()
