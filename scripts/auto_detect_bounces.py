#!/usr/bin/env python3
"""
Auto-detect bounced emails from Gmail and update send log.

Runs automatically to:
1. Search Gmail for bounce notifications (last 7 days)
2. Extract bounced email addresses
3. Mark them as bounced in application_send_log.json
4. Add to BAD_EMAILS in send_application_emails.py

Usage:
    python3 scripts/auto_detect_bounces.py              # Dry run
    python3 scripts/auto_detect_bounces.py --apply      # Actually update logs
    python3 scripts/auto_detect_bounces.py --days 14    # Check last 14 days
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[6]
    _env_path = _root / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        # Try workspace root
        load_dotenv("/home/bookchaowalit/book-everything/solo-empire/.env")
except ImportError:
    pass

# Paths
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEND_LOG_FILE = DATA_DIR / "application_send_log.json"
SEND_SCRIPT_FILE = Path(__file__).resolve().parent / "send_application_emails.py"


def load_gmail_service():
    """Load Gmail API service."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: google packages not installed. Run:")
        print("  pip3 install --user google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not (refresh_token and client_id and client_secret):
        print("ERROR: Gmail OAuth credentials not found in .env")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://mail.google.com/']
    )
    creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


def search_bounce_notifications(service, days: int = 7) -> list:
    """Search Gmail for bounce notifications."""
    query = f'from:mailer-daemon@googlemail.com newer_than:{days}d'
    
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100
        ).execute()
        
        messages = results.get('messages', [])
        print(f"Found {len(messages)} bounce notification(s) in last {days} days")
        return messages
    except Exception as e:
        print(f"ERROR searching Gmail: {e}")
        return []


def extract_bounced_email(service, message_id: str) -> str:
    """Extract the bounced email address from a bounce notification."""
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        # Check snippet first (faster)
        snippet = message.get('snippet', '')
        
        # Look for email pattern in snippet
        email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        matches = re.findall(email_pattern, snippet)
        
        # Filter out common non-bounce addresses
        bounce_emails = [
            m for m in matches 
            if not m.endswith('@googlemail.com') 
            and not m.endswith('@gmail.com')
            and m != 'mailer-daemon@googlemail.com'
        ]
        
        if bounce_emails:
            return bounce_emails[0]
        
        # If not in snippet, check message body
        payload = message.get('payload', {})
        body = ''
        
        if payload.get('body', {}).get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif payload.get('parts'):
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        
        if body:
            matches = re.findall(email_pattern, body)
            bounce_emails = [
                m for m in matches 
                if not m.endswith('@googlemail.com') 
                and not m.endswith('@gmail.com')
                and m != 'mailer-daemon@googlemail.com'
            ]
            if bounce_emails:
                return bounce_emails[0]
        
        return None
    except Exception as e:
        print(f"  Warning: Could not extract email from message {message_id}: {e}")
        return None


def load_send_log() -> list:
    """Load application send log."""
    if SEND_LOG_FILE.exists():
        return json.loads(SEND_LOG_FILE.read_text())
    return []


def save_send_log(log: list):
    """Save application send log."""
    with open(SEND_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def mark_as_bounced(send_log: list, email: str) -> int:
    """Mark all matching emails in send log as bounced."""
    updated = 0
    email_lower = email.lower()
    
    for entry in send_log:
        if entry.get('to', '').lower() == email_lower and entry.get('status') == 'sent':
            entry['status'] = 'bounced'
            entry['bounced_at'] = datetime.now().isoformat()
            entry['bounce_reason'] = 'auto-detected from Gmail bounce notification'
            updated += 1
    
    return updated


def update_bad_emails(email: str):
    """Add email to BAD_EMAILS in send_application_emails.py."""
    if not SEND_SCRIPT_FILE.exists():
        print(f"  Warning: {SEND_SCRIPT_FILE} not found, cannot update BAD_EMAILS")
        return
    
    content = SEND_SCRIPT_FILE.read_text()
    
    # Find BAD_EMAILS set
    bad_emails_match = re.search(r'BAD_EMAILS\s*=\s*\{([^}]+)\}', content, re.DOTALL)
    if not bad_emails_match:
        print("  Warning: Could not find BAD_EMAILS in send_application_emails.py")
        return
    
    bad_emails_str = bad_emails_match.group(1)
    
    # Check if already in set
    if f"'{email}'" in bad_emails_str or f'"{email}"' in bad_emails_str:
        return  # Already there
    
    # Add new email
    new_bad_emails_str = bad_emails_str.rstrip()
    if new_bad_emails_str and not new_bad_emails_str.endswith(','):
        new_bad_emails_str += ','
    new_bad_emails_str += f" '{email}',"
    
    new_content = content[:bad_emails_match.start(1)] + new_bad_emails_str + content[bad_emails_match.end(1):]
    SEND_SCRIPT_FILE.write_text(new_content)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Auto-detect bounced emails from Gmail')
    parser.add_argument('--apply', action='store_true', help='Actually update logs (default: dry run)')
    parser.add_argument('--days', type=int, default=7, help='Check last N days (default: 7)')
    
    args = parser.parse_args()
    
    print(f"{'='*70}")
    print(f"  AUTO BOUNCE DETECTOR")
    print(f"  {'DRY RUN' if not args.apply else 'APPLYING CHANGES'}")
    print(f"{'='*70}\n")
    
    # Load Gmail
    print("Loading Gmail API...")
    service = load_gmail_service()
    
    # Search for bounces
    print(f"\nSearching for bounce notifications (last {args.days} days)...")
    messages = search_bounce_notifications(service, args.days)
    
    if not messages:
        print("\nNo bounce notifications found.")
        return
    
    # Extract bounced emails
    print("\nExtracting bounced email addresses...")
    bounced_emails = []
    for msg in messages:
        email = extract_bounced_email(service, msg['id'])
        if email:
            bounced_emails.append(email)
            print(f"  Found: {email}")
    
    # Deduplicate
    bounced_emails = list(set(bounced_emails))
    print(f"\nUnique bounced emails: {len(bounced_emails)}")
    
    if not bounced_emails:
        print("\nNo bounced emails extracted.")
        return
    
    # Load send log
    print("\nLoading send log...")
    send_log = load_send_log()
    print(f"  Total entries: {len(send_log)}")
    
    # Mark as bounced
    total_updated = 0
    for email in bounced_emails:
        updated = mark_as_bounced(send_log, email)
        if updated > 0:
            print(f"  Marked {updated} entries as bounced for {email}")
            total_updated += updated
    
    print(f"\nTotal entries marked as bounced: {total_updated}")
    
    # Apply changes
    if args.apply:
        print("\nApplying changes...")
        save_send_log(send_log)
        print(f"  Saved send log to {SEND_LOG_FILE}")
        
        # Update BAD_EMAILS
        for email in bounced_emails:
            update_bad_emails(email)
        print(f"  Updated BAD_EMAILS in {SEND_SCRIPT_FILE}")
        
        print("\n✓ Changes applied successfully")
    else:
        print("\n" + "="*70)
        print("  DRY RUN - No changes made")
        print("  Use --apply to actually update logs")
        print("="*70)


if __name__ == '__main__':
    main()
