#!/usr/bin/env python3
"""
Telegram callback handler for job notification inline buttons.
Polls for callback queries (skip/apply actions) and updates apply_tracker.csv.

Usage:
    python3 telegram_callback_handler.py          # Run once (poll and process)
    python3 telegram_callback_handler.py --daemon # Run continuously (poll every 30s)
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
APPLY_LOG = DATA_DIR / "apply_tracker.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_matched_jobs() -> dict:
    """Load matched jobs CSV into dict keyed by job index."""
    if not MATCHED_CSV.exists():
        return {}
    jobs = {}
    with open(MATCHED_CSV, "r") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            jobs[str(i)] = row
    return jobs


def update_apply_tracker(url: str, status: str, note: str = ""):
    """Update or append entry in apply_tracker.csv."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing entries
    entries = []
    found = False
    if APPLY_LOG.exists():
        with open(APPLY_LOG, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") == url:
                    row["status"] = status
                    row["note"] = note
                    row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    found = True
                entries.append(row)
    
    if not found:
        entries.append({
            "url": url,
            "status": status,
            "note": note,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    
    # Write back
    fieldnames = ["url", "status", "note", "updated_at"]
    with open(APPLY_LOG, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def get_updates(offset: int = None) -> list:
    """Get pending updates from Telegram."""
    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])
    except Exception as e:
        print(f"  Warning: getUpdates failed: {e}")
        return []


def answer_callback(query_id: str, text: str = ""):
    """Answer a callback query to remove loading state."""
    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": query_id, "text": text, "show_alert": False}
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Warning: answerCallbackQuery failed: {e}")


def process_callback(callback_query: dict, jobs: dict):
    """Process a single callback query."""
    query_id = callback_query.get("id")
    data = callback_query.get("data", "")
    from_user = callback_query.get("from", {}).get("first_name", "User")
    
    if not (data.startswith("skip:") or data.startswith("applied:")):
        return
    
    action, job_idx = data.split(":", 1)
    job = jobs.get(job_idx)
    
    if job:
        url = job.get("url", "")
        title = job.get("title", "")[:40]
        
        if action == "applied":
            # Update tracker as applied
            update_apply_tracker(url, "applied", f"Marked by {from_user}")
            answer_callback(query_id, f"Applied: {title}")
            print(f"  ✓ {from_user} marked applied: {title}")
        elif action == "skip":
            # Update tracker as skipped
            update_apply_tracker(url, "skipped", f"Skipped by {from_user}")
            answer_callback(query_id, f"Skipped: {title}")
            print(f"  ✓ {from_user} skipped: {title}")
    else:
        answer_callback(query_id, "Job not found")
        print(f"  Warning: Job #{job_idx} not found in matched_jobs.csv")


def poll_once(last_update_id: int = 0) -> int:
    """Poll for callbacks once. Returns last processed update_id."""
    jobs = load_matched_jobs()
    if not jobs:
        print("  No matched jobs found, skipping")
        return last_update_id
    
    updates = get_updates(offset=last_update_id + 1 if last_update_id else None)
    
    for update in updates:
        update_id = update.get("update_id", 0)
        callback_query = update.get("callback_query")
        
        if callback_query:
            process_callback(callback_query, jobs)
        
        last_update_id = max(last_update_id, update_id)
    
    return last_update_id


def main():
    parser = argparse.ArgumentParser(description="Telegram callback handler for job buttons")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (daemon mode)")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  TELEGRAM CALLBACK HANDLER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    last_update_id = 0
    
    if args.daemon:
        print(f"Running in daemon mode (poll every {args.interval}s)...")
        while True:
            try:
                last_update_id = poll_once(last_update_id)
            except KeyboardInterrupt:
                print("\nShutting down...")
                break
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(args.interval)
    else:
        print("Running single poll...")
        last_update_id = poll_once(last_update_id)
        print("Done.")


if __name__ == "__main__":
    main()
