#!/usr/bin/env python3
"""
Auto-Seed Application Tracker
Automatically add high-scoring matched jobs to the application tracker.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
MATCHED_JOBS = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
LOG_FILE = DATA_DIR / "auto_seed_log.json"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def load_matched_jobs(min_score=8):
    """Load matched jobs above minimum score."""
    if not MATCHED_JOBS.exists():
        print("❌ matched_jobs.csv not found")
        return []
    
    jobs = []
    with open(MATCHED_JOBS, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                score = int(row.get("score", 0))
                if score >= min_score:
                    jobs.append(row)
            except (ValueError, TypeError):
                continue
    
    # Sort by score descending
    jobs.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    return jobs


def load_application_tracker():
    """Load existing application tracker."""
    if not APPLY_TRACKER.exists():
        return []
    
    apps = []
    with open(APPLY_TRACKER, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            apps.append(row)
    return apps


def save_application_tracker(apps):
    """Save application tracker."""
    if not apps:
        return
    
    fieldnames = ["url", "title", "company", "status", "note", "updated_at"]
    with open(APPLY_TRACKER, "w", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(apps)


def send_telegram(message):
    """Send Telegram notification."""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")


def auto_seed(min_score=8, send_telegram_flag=False, dry_run=False):
    """Auto-seed application tracker from matched jobs."""
    print(f"\n{'='*60}")
    print(f"  AUTO-SEED APPLICATION TRACKER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Load data
    print(f"📊 Loading matched jobs (min score: {min_score})...")
    matched_jobs = load_matched_jobs(min_score)
    print(f"   Found {len(matched_jobs)} jobs")
    
    print(f"\n📋 Loading application tracker...")
    tracker = load_application_tracker()
    print(f"   Current applications: {len(tracker)}")
    
    # Find URLs already in tracker
    tracked_urls = {app.get("url", "") for app in tracker}
    
    # Find new jobs to add
    new_jobs = []
    for job in matched_jobs:
        url = job.get("url", "")
        if url and url not in tracked_urls:
            new_jobs.append(job)
    
    print(f"\n🆕 New jobs to add: {len(new_jobs)}")
    
    if not new_jobs:
        print("\n✅ No new jobs to seed")
        return
    
    if dry_run:
        print("\n[DRY RUN] Would add:")
        for job in new_jobs[:20]:
            score = job.get("score", 0)
            title = job.get("title", "")[:50]
            company = job.get("company", "")[:30]
            print(f"   • [{score}] {title} @ {company}")
        if len(new_jobs) > 20:
            print(f"   ... and {len(new_jobs) - 20} more")
        return
    
    # Add new jobs to tracker
    now = datetime.now().isoformat()
    for job in new_jobs:
        tracker.append({
            "url": job.get("url", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": "discovered",
            "note": f"Auto-seeded (score: {job.get('score', 0)})",
            "updated_at": now,
        })
    
    # Save
    save_application_tracker(tracker)
    print(f"\n✅ Added {len(new_jobs)} jobs to application tracker")
    print(f"   Total applications: {len(tracker)}")
    
    # Log
    log_data = {
        "timestamp": now,
        "added": len(new_jobs),
        "total": len(tracker),
        "min_score": min_score,
    }
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)
    print(f"   Log saved: {LOG_FILE.name}")
    
    # Telegram
    if send_telegram_flag and new_jobs:
        top_jobs = new_jobs[:10]
        msg = f"🌱 *Auto-Seeded {len(new_jobs)} Jobs*\n\n"
        msg += f"Min score: {min_score}+\n"
        msg += f"Total tracked: {len(tracker)}\n\n"
        msg += "*Top New Jobs:*\n"
        for job in top_jobs:
            score = job.get("score", 0)
            title = job.get("title", "")[:40]
            company = job.get("company", "")[:25]
            msg += f"• [{score}] {title} @ {company}\n"
        
        if len(new_jobs) > 10:
            msg += f"\n_...and {len(new_jobs) - 10} more_"
        
        send_telegram(msg)
        print("   📱 Telegram notification sent")


def main():
    parser = argparse.ArgumentParser(description="Auto-Seed Application Tracker")
    parser.add_argument("--min-score", type=int, default=8, help="Minimum match score (default: 8)")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram notification")
    parser.add_argument("--dry-run", action="store_true", help="Preview without adding")
    args = parser.parse_args()
    
    auto_seed(
        min_score=args.min_score,
        send_telegram_flag=args.send_telegram,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
