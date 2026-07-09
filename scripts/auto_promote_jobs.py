#!/usr/bin/env python3
"""
Auto-promote top scored jobs from matched_jobs.csv to apply_tracker.csv.

Usage:
    python3 scripts/auto_promote_jobs.py
    python3 scripts/auto_promote_jobs.py --min-score 20 --top 10
    python3 scripts/auto_promote_jobs.py --backfill  # backfill title/company for existing entries
"""

import argparse
import csv
import os
import sys
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
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
TRACKER_CSV = DATA_DIR / "apply_tracker.csv"

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_matched_jobs() -> list:
    """Load matched jobs sorted by score descending."""
    if not MATCHED_CSV.exists():
        print(f"ERROR: {MATCHED_CSV} not found. Run match_jobs.py first.")
        sys.exit(1)
    jobs = []
    with open(MATCHED_CSV, "r") as f:
        for row in csv.DictReader(f):
            try:
                row["_score"] = int(row.get("score", row.get("_score", 0)))
            except (ValueError, TypeError):
                row["_score"] = 0
            jobs.append(row)
    jobs.sort(key=lambda x: x["_score"], reverse=True)
    return jobs


def load_tracker() -> dict:
    """Load existing tracker entries. Returns {url: row}."""
    if not TRACKER_CSV.exists():
        return {}
    entries = {}
    with open(TRACKER_CSV, "r") as f:
        for row in csv.DictReader(f):
            entries[row.get("url", "")] = row
    return entries


def save_tracker(entries: dict):
    """Save tracker entries back to CSV. Auto-detects schema (4-col or 6-col)."""
    rows = list(entries.values())
    # Detect schema from first entry
    has_title = any("title" in r for r in rows)
    fieldnames = ["url", "title", "company", "status", "note", "updated_at"] if has_title else ["url", "status", "note", "updated_at"]
    # Sort by updated_at descending
    rows.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    with open(TRACKER_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def backfill_tracker(entries: dict, jobs: list) -> int:
    """Backfill title/company for existing tracker entries from matched jobs."""
    job_map = {j.get("url", ""): j for j in jobs}
    updated = 0
    for url, entry in entries.items():
        if url in job_map:
            job = job_map[url]
            if not entry.get("title") and job.get("title"):
                entry["title"] = job["title"]
                updated += 1
            if not entry.get("company") and job.get("company"):
                entry["company"] = job["company"]
                updated += 1
            # Update note with current score
            if job.get("_score"):
                entry["note"] = f"score={job['_score']}"
    return updated


def promote_jobs(jobs: list, entries: dict, min_score: int, top_n: int) -> list:
    """Add new jobs to tracker. Returns list of newly added jobs."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added = []
    count = 0
    for job in jobs:
        if count >= top_n:
            break
        url = job.get("url", "")
        if not url:
            continue
        if url in entries:
            continue  # already tracked
        score = job.get("_score", 0)
        if score < min_score:
            continue
        # Add to tracker
        entries[url] = {
            "url": url,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": "notified",
            "note": f"score={score}",
            "updated_at": now,
        }
        added.append(job)
        count += 1
    return added


def promote_discovered(entries: dict, min_score: int) -> list:
    """Promote discovered entries with score >= min_score to notified status.
    Parses score from the 'note' field (e.g. 'Auto-seeded (score: 48)')."""
    import re
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    promoted = []
    for url, entry in entries.items():
        if entry.get("status") != "discovered":
            continue
        m = re.search(r"score[:\s]+(\d+)", entry.get("note", ""))
        score = int(m.group(1)) if m else 0
        if score >= min_score:
            entry["status"] = "notified"
            entry["updated_at"] = now
            entry["note"] = f"Auto-promoted (score={score}) {now}"
            promoted.append({**entry, "_score": score})
    promoted.sort(key=lambda x: x["_score"], reverse=True)
    return promoted


def send_telegram_notification(added_jobs: list):
    """Send Telegram notification about newly promoted jobs."""
    if not added_jobs or not TELEGRAM_BOT_TOKEN:
        return
    lines = [f"🚀 <b>Auto-Promoted {len(added_jobs)} Jobs to Tracker</b>\n"]
    for i, job in enumerate(added_jobs[:10], 1):
        title = job.get("title", "Unknown")[:50]
        company = job.get("company", "") or "N/A"
        score = job.get("_score", 0)
        url = job.get("url", "")
        salary = job.get("salary", "") or "N/A"
        lines.append(f"{i}. <b>{title}</b>")
        lines.append(f"   🏢 {company} | 💰 {salary} | ⭐ Score: {score}")
        if url:
            lines.append(f'   <a href="{url}">View & Apply</a>\n')
    message = "\n".join(lines)

    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        print(f"  ✓ Telegram notification sent ({len(added_jobs)} jobs)")
    except Exception as e:
        print(f"  ✗ Telegram notification failed: {e}")


def deduplicate_tracker(entries: dict) -> list:
    """Detect and merge duplicate tracker entries (same title+company, different URLs).
    Returns list of removed duplicate entries."""
    from collections import defaultdict

    STATUS_PRIORITY = {"offer": 4, "interviewing": 3, "applied": 2, "notified": 1, "rejected": 0, "withdrawn": 0}

    # Normalize title for comparison
    def norm(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum() or c.isspace()).strip()

    # Group by (normalized_title, normalized_company)
    groups = defaultdict(list)
    for url, entry in entries.items():
        key = (norm(entry.get("title", "")), norm(entry.get("company", "")))
        if key[0] and key[1]:  # Only dedup if both title and company exist
            groups[key].append(entry)
        else:
            groups[("__single__", url)] = [entry]  # Keep singles

    removed = []
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        # Sort by status priority desc, then updated_at desc
        group.sort(
            key=lambda e: (STATUS_PRIORITY.get(e.get("status", ""), 0), e.get("updated_at", "")),
            reverse=True,
        )
        keeper = group[0]
        for dup in group[1:]:
            dup_url = dup.get("url", "")
            removed.append(dup)
            if dup_url in entries:
                del entries[dup_url]
        # Merge notes from removed into keeper
        extra_notes = [d.get("note", "") for d in group[1:] if d.get("note")]
        if extra_notes:
            existing_note = keeper.get("note", "")
            keeper["note"] = f"{existing_note} | merged: {'; '.join(extra_notes)}".strip(" |")

    return removed


def main():
    parser = argparse.ArgumentParser(description="Auto-promote top jobs to apply tracker")
    parser.add_argument("--min-score", type=int, default=15, help="Minimum score to auto-promote")
    parser.add_argument("--top", type=int, default=20, help="Max jobs to promote per run")
    parser.add_argument("--backfill", action="store_true", help="Backfill title/company for existing entries")
    parser.add_argument("--dedup", action="store_true", help="Detect and merge duplicate entries (same title+company)")
    parser.add_argument("--promote-discovered", action="store_true", help="Promote discovered entries with score >= min_score to notified")
    parser.add_argument("--notify", action="store_true", default=True, help="Send Telegram notification")
    parser.add_argument("--no-notify", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args()

    jobs = load_matched_jobs()
    entries = load_tracker()
    print(f"Loaded {len(jobs)} matched jobs, {len(entries)} tracked applications")

    # Backfill existing entries
    if args.backfill:
        updated = backfill_tracker(entries, jobs)
        if updated:
            save_tracker(entries)
            print(f"  ✓ Backfilled {updated} fields in existing tracker entries")

    # Deduplicate
    if args.dedup:
        removed = deduplicate_tracker(entries)
        if removed:
            save_tracker(entries)
            print(f"\n  ✓ Deduplicated: removed {len(removed)} duplicate(s):")
            for dup in removed:
                print(f"    ✕ {dup.get('title', '')[:50]} @ {dup.get('company', '') or 'N/A'} ({dup.get('url', '')[:60]})")
        else:
            print(f"\n  ✓ No duplicates found")

    # Promote new jobs
    added = promote_jobs(jobs, entries, args.min_score, args.top)
    if added:
        save_tracker(entries)
        print(f"\n  ✓ Promoted {len(added)} new jobs to tracker (score >= {args.min_score}):")
        for job in added:
            print(f"    ⭐ {job.get('_score'):3d} | {job.get('title', '')[:50]} @ {job.get('company', '') or 'N/A'}")
        # Send notification
        if not args.no_notify:
            send_telegram_notification(added)
    else:
        print(f"\n  No new jobs to promote (score >= {args.min_score})")

    # Promote discovered entries
    if args.promote_discovered:
        disc_promoted = promote_discovered(entries, args.min_score)
        if disc_promoted:
            save_tracker(entries)
            print(f"\n  ✓ Promoted {len(disc_promoted)} discovered → notified (score >= {args.min_score}):")
            for job in disc_promoted[:10]:
                print(f"    ⭐ {job.get('_score'):3d} | {job.get('url', '')[:70]}")
            if len(disc_promoted) > 10:
                print(f"    ... and {len(disc_promoted) - 10} more")
            if not args.no_notify and disc_promoted:
                send_telegram_notification(disc_promoted)
        else:
            print(f"\n  No discovered entries to promote (score >= {args.min_score})")

    # Summary
    print(f"\n  Total tracked: {len(entries)} applications")
    print(f"  Saved to: {TRACKER_CSV}")


if __name__ == "__main__":
    main()
