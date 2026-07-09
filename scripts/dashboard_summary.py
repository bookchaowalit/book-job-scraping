#!/usr/bin/env python3
"""
Generate a dashboard summary of the job search automation pipeline.

Shows:
- Contact emails found
- Followup emails drafted / sent / replied
- Jobs discovered / applied / notified
- Overall pipeline health

Usage:
    python3 scripts/dashboard_summary.py          # Print to terminal
    python3 scripts/dashboard_summary.py --json    # Output JSON
"""

import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"


def load_data():
    """Load all relevant data files."""
    data = {}

    # apply_tracker.csv
    tracker_file = DATA_DIR / "apply_tracker.csv"
    if tracker_file.exists():
        with open(tracker_file) as f:
            data['tracker'] = list(csv.DictReader(f))
    else:
        data['tracker'] = []

    # job_postings.csv
    postings_file = DATA_DIR / "job_postings.csv"
    if postings_file.exists():
        with open(postings_file) as f:
            data['postings'] = list(csv.DictReader(f))
    else:
        data['postings'] = []

    # matched_jobs.csv
    matched_file = DATA_DIR / "matched_jobs.csv"
    if matched_file.exists():
        with open(matched_file) as f:
            data['matched'] = list(csv.DictReader(f))
    else:
        data['matched'] = []

    # contact_emails.json
    ce_file = DATA_DIR / "contact_emails.json"
    if ce_file.exists():
        data['contacts'] = json.loads(ce_file.read_text())
    else:
        data['contacts'] = {}

    # auto_send_log.json
    log_file = DATA_DIR / "auto_send_log.json"
    if log_file.exists():
        data['send_log'] = json.loads(log_file.read_text())
    else:
        data['send_log'] = []

    # followup_emails/
    email_dir = DATA_DIR / "followup_emails"
    if email_dir.exists():
        data['followup_files'] = [f.name for f in email_dir.glob("*.txt")]
    else:
        data['followup_files'] = []

    return data


def generate_summary(data: dict) -> dict:
    """Generate summary statistics."""
    summary = {}

    # ── Job Postings ──
    postings = data.get('postings', [])
    summary['total_postings'] = len(postings)
    if postings:
        sources = Counter(r.get('source', 'unknown') for r in postings)
        summary['sources'] = dict(sources.most_common())

    # ── Matched Jobs ──
    summary['matched_jobs'] = len(data.get('matched', []))

    # ── Apply Tracker ──
    tracker = data.get('tracker', [])
    statuses = Counter(r.get('status', '') for r in tracker)
    summary['tracker_total'] = len(tracker)
    summary['tracker_statuses'] = dict(statuses.most_common())
    summary['discovered'] = statuses.get('discovered', 0)
    summary['notified'] = statuses.get('notified', 0)
    summary['applying'] = statuses.get('applying', 0)

    # ── Contact Emails ──
    contacts = data.get('contacts', {})
    with_email = sum(1 for v in contacts.values() if v.get('best'))
    summary['companies_total'] = len(contacts)
    summary['companies_with_email'] = with_email
    summary['companies_without_email'] = len(contacts) - with_email
    summary['email_coverage'] = f"{with_email}/{len(contacts)} ({100*with_email/max(len(contacts),1):.0f}%)"

    # ── Followup Emails ──
    followup_files = data.get('followup_files', [])
    summary['followup_drafts'] = len(followup_files)

    # ── Auto Send Log ──
    send_log = data.get('send_log', [])
    summary['emails_sent'] = len(send_log)
    sent_statuses = Counter(r.get('status', '') for r in send_log)
    summary['send_statuses'] = dict(sent_statuses.most_common())

    # ── Pipeline Health ──
    health = []
    if summary['companies_with_email'] < 100:
        health.append(f"⚠ Low email coverage: {summary['email_coverage']}")
    if summary['emails_sent'] == 0:
        health.append("⚠ No emails sent yet (auto-send not tested)")
    if summary['discovered'] > 0:
        health.append(f"ℹ {summary['discovered']} jobs still need processing")
    if not health:
        health.append("✓ Pipeline healthy")
    summary['health'] = health

    return summary


def print_summary(summary: dict):
    """Pretty-print the summary."""
    print()
    print("═" * 60)
    print("  📊 JOB SEARCH PIPELINE DASHBOARD")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("═" * 60)

    print(f"\n  📋 JOB POSTINGS")
    print(f"    Total scraped:      {summary['total_postings']}")
    print(f"    Matched to profile: {summary['matched_jobs']}")
    if summary.get('sources'):
        print(f"    Sources:")
        for src, count in summary['sources'].items():
            print(f"      {src:25s} {count}")

    print(f"\n  📊 APPLY TRACKER")
    print(f"    Total entries:      {summary['tracker_total']}")
    for status, count in summary.get('tracker_statuses', {}).items():
        print(f"      {status:20s} {count}")

    print(f"\n  📧 CONTACT EMAILS")
    print(f"    Companies total:    {summary['companies_total']}")
    print(f"    With email:         {summary['companies_with_email']}")
    print(f"    Without email:      {summary['companies_without_email']}")
    print(f"    Coverage:           {summary['email_coverage']}")

    print(f"\n  ✉️  FOLLOWUP EMAILS")
    print(f"    Drafts created:     {summary['followup_drafts']}")
    print(f"    Emails sent:        {summary['emails_sent']}")
    if summary.get('send_statuses'):
        for status, count in summary['send_statuses'].items():
            print(f"      {status:20s} {count}")

    print(f"\n  🔍 PIPELINE HEALTH")
    for h in summary.get('health', []):
        print(f"    {h}")

    print()
    print("═" * 60)
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Job search pipeline dashboard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = load_data()
    summary = generate_summary(data)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_summary(summary)


if __name__ == "__main__":
    main()
