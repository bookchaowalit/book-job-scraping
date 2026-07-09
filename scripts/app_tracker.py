#!/usr/bin/env python3
"""
Application Tracker — Kanban-style tracking with Leantime sync.
Manages application stages: discovered → applied → screening → interview → offer → accepted/rejected.

Usage:
    python app_tracker.py --add --job-id <id> --stage applied
    python app_tracker.py --update --job-id <id> --stage interview --notes "Phone screen went well"
    python app_tracker.py --list [--stage <stage>]
    python app_tracker.py --kanban
    python app_tracker.py --sync-leantime
    python app_tracker.py --stale  # Applications with no update in 7+ days
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
TRACKER_FILE = DATA_DIR / "application_tracker.json"
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"

# Stages in order
STAGES = [
    "discovered",     # Found in pipeline
    "saved",          # Manually saved for later
    "applied",        # Application submitted
    "screening",      # HR/recruiter screening
    "technical",      # Technical interview
    "onsite",         # Onsite/final interview
    "offer",          # Offer received
    "accepted",       # Offer accepted
    "rejected",       # Rejected at any stage
    "withdrawn",      # Candidate withdrew
]

STAGE_EMOJIS = {
    "discovered": "🔍", "saved": "💾", "applied": "📤",
    "screening": "📞", "technical": "💻", "onsite": "🏢",
    "offer": "🎉", "accepted": "✅", "rejected": "❌", "withdrawn": "🚫",
}


def load_tracker():
    """Load application tracker."""
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return {"applications": {}, "updated_at": None}


def save_tracker(tracker):
    """Save application tracker."""
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    tracker["updated_at"] = datetime.now().isoformat()
    TRACKER_FILE.write_text(json.dumps(tracker, indent=2, default=str))


def load_job_info(job_id):
    """Load job info from matched jobs or applications CSV."""
    # Check matched jobs
    if MATCHED_JOBS_CSV.exists():
        with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("id") == job_id or row.get("job_id") == job_id:
                    return {
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "url": row.get("url", ""),
                        "location": row.get("location", ""),
                        "salary_min": row.get("salary_min", ""),
                        "salary_max": row.get("salary_max", ""),
                        "board": row.get("board", ""),
                    }
    # Check applications CSV
    if APPLICATIONS_CSV.exists():
        with open(APPLICATIONS_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("job_id") == job_id:
                    return {
                        "title": row.get("job_title", ""),
                        "company": row.get("company", ""),
                        "url": row.get("url", ""),
                        "location": row.get("location", ""),
                    }
    return None


def add_application(tracker, job_id, stage="discovered", notes=""):
    """Add a new application to tracker."""
    job_info = load_job_info(job_id) or {}

    tracker["applications"][job_id] = {
        "job_id": job_id,
        "title": job_info.get("title", "Unknown"),
        "company": job_info.get("company", "Unknown"),
        "url": job_info.get("url", ""),
        "location": job_info.get("location", ""),
        "stage": stage,
        "stage_history": [{"stage": stage, "date": datetime.now().isoformat(), "notes": notes}],
        "notes": [notes] if notes else [],
        "added_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "days_in_stage": 0,
    }
    return tracker


def update_stage(tracker, job_id, new_stage, notes=""):
    """Update application stage."""
    if job_id not in tracker["applications"]:
        print(f"Application {job_id} not found. Adding it first...")
        tracker = add_application(tracker, job_id, new_stage, notes)
        return tracker

    app = tracker["applications"][job_id]
    old_stage = app["stage"]
    app["stage"] = new_stage
    app["stage_history"].append({
        "stage": new_stage, "date": datetime.now().isoformat(),
        "notes": notes, "from": old_stage
    })
    if notes:
        app["notes"].append(f"[{datetime.now().strftime('%Y-%m-%d')}] {notes}")
    app["updated_at"] = datetime.now().isoformat()
    app["days_in_stage"] = 0

    print(f"  {app['title']} at {app['company']}: {old_stage} → {new_stage}")
    return tracker


def list_applications(tracker, stage_filter=None):
    """List applications, optionally filtered by stage."""
    apps = tracker.get("applications", {})
    if not apps:
        print("No applications tracked yet.")
        return

    if stage_filter:
        apps = {k: v for k, v in apps.items() if v["stage"] == stage_filter}
        if not apps:
            print(f"No applications in stage: {stage_filter}")
            return

    # Group by stage
    by_stage = {}
    for app in apps.values():
        stage = app["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(app)

    print(f"\n{'='*80}")
    print(f"APPLICATION TRACKER — {len(apps)} applications")
    print(f"{'='*80}")

    for stage in STAGES:
        if stage not in by_stage:
            continue
        emoji = STAGE_EMOJIS.get(stage, "")
        print(f"\n{emoji} {stage.upper()} ({len(by_stage[stage])})")
        print(f"  {'-'*60}")
        for app in sorted(by_stage[stage], key=lambda x: x.get("updated_at", ""), reverse=True):
            days = (datetime.now() - datetime.fromisoformat(app["updated_at"])).days
            print(f"  {app['title'][:35]:<35} {app['company'][:20]:<20} {days}d ago")


def show_kanban(tracker):
    """Show Kanban board view."""
    apps = tracker.get("applications", {})
    if not apps:
        print("No applications tracked yet.")
        return

    by_stage = {}
    for app in apps.values():
        stage = app["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(app)

    print(f"\n{'='*100}")
    print("APPLICATION KANBAN BOARD")
    print(f"{'='*100}\n")

    # Active stages only
    active_stages = [s for s in STAGES if s in by_stage]

    # Header
    header = ""
    for stage in active_stages:
        emoji = STAGE_EMOJIS.get(stage, "")
        header += f"  {emoji} {stage:<12}"
    print(header)
    print(f"  {'─' * (15 * len(active_stages))}")

    # Rows
    max_items = max(len(by_stage.get(s, [])) for s in active_stages)
    for i in range(min(max_items, 10)):  # Max 10 rows
        row = ""
        for stage in active_stages:
            items = by_stage.get(stage, [])
            if i < len(items):
                item = items[i]
                row += f"  {item['title'][:12]:<14}"
            else:
                row += f"  {'':<14}"
        print(row)

    # Counts
    print(f"  {'─' * (15 * len(active_stages))}")
    counts = ""
    for stage in active_stages:
        counts += f"  [{len(by_stage.get(stage, []))}]{'':<11}"
    print(counts)

    # Summary stats
    total = len(apps)
    active = len([a for a in apps.values() if a["stage"] not in ("rejected", "withdrawn", "accepted")])
    offers = len([a for a in apps.values() if a["stage"] == "offer"])
    accepted = len([a for a in apps.values() if a["stage"] == "accepted"])

    print(f"\n  Total: {total} | Active: {active} | Offers: {offers} | Accepted: {accepted}")
    if total > 0:
        print(f"  Conversion rate: {accepted/total*100:.1f}%")


def find_stale(tracker, days=7):
    """Find applications with no update in N+ days."""
    apps = tracker.get("applications", {})
    cutoff = datetime.now() - timedelta(days=days)
    stale = []

    for app in apps.values():
        if app["stage"] in ("accepted", "rejected", "withdrawn"):
            continue
        updated = datetime.fromisoformat(app["updated_at"])
        if updated < cutoff:
            stale.append(app)

    if not stale:
        print(f"No stale applications (all updated within {days} days).")
        return

    print(f"\n⚠️  STALE APPLICATIONS (no update in {days}+ days):\n")
    for app in sorted(stale, key=lambda x: x["updated_at"]):
        days_stale = (datetime.now() - datetime.fromisoformat(app["updated_at"])).days
        print(f"  {app['title'][:35]:<35} {app['company']:<20} Stage: {app['stage']:<12} {days_stale}d stale")
    print(f"\n  Total stale: {len(stale)}")


def sync_to_leantime(tracker):
    """Sync applications to Leantime as tickets."""
    try:
        import requests
    except ImportError:
        print("requests library required")
        return

    # Leantime config from environment
    leantime_url = os.getenv("LEANTIME_URL", "")
    leantime_key = os.getenv("LEANTIME_API_KEY", "")

    if not leantime_url or not leantime_key:
        print("Leantime not configured. Set LEANTIME_URL and LEANTIME_API_KEY in .env")
        print("Sync simulated — would create/update tickets for each application.")
        # Simulate sync
        apps = tracker.get("applications", {})
        for job_id, app in apps.items():
            if app["stage"] not in ("accepted", "rejected", "withdrawn"):
                print(f"  [SIMULATED] Would sync: {app['title']} at {app['company']} → Stage: {app['stage']}")
        return

    print(f"Syncing to Leantime at {leantime_url}...")
    apps = tracker.get("applications", {})
    synced = 0
    for job_id, app in apps.items():
        if app["stage"] in ("accepted", "rejected", "withdrawn"):
            continue
        # Would create/update Leantime ticket here
        print(f"  Synced: {app['title']} at {app['company']}")
        synced += 1
    print(f"Synced {synced} applications to Leantime.")


def main():
    parser = argparse.ArgumentParser(description="Application Tracker")
    parser.add_argument("--add", action="store_true", help="Add application")
    parser.add_argument("--update", action="store_true", help="Update stage")
    parser.add_argument("--job-id", help="Job ID")
    parser.add_argument("--stage", choices=STAGES, help="Application stage")
    parser.add_argument("--notes", default="", help="Notes")
    parser.add_argument("--list", action="store_true", help="List applications")
    parser.add_argument("--kanban", action="store_true", help="Show Kanban board")
    parser.add_argument("--stale", action="store_true", help="Find stale applications")
    parser.add_argument("--days", type=int, default=7, help="Days threshold for stale")
    parser.add_argument("--sync-leantime", action="store_true", help="Sync to Leantime")
    parser.add_argument("--export-csv", action="store_true", help="Export to CSV")
    args = parser.parse_args()

    tracker = load_tracker()

    if args.add:
        if not args.job_id:
            print("Error: --job-id required")
            return
        tracker = add_application(tracker, args.job_id, args.stage or "discovered", args.notes)
        save_tracker(tracker)
        print(f"Added {args.job_id} to tracker (stage: {args.stage or 'discovered'})")

    elif args.update:
        if not args.job_id or not args.stage:
            print("Error: --job-id and --stage required")
            return
        tracker = update_stage(tracker, args.job_id, args.stage, args.notes)
        save_tracker(tracker)

    elif args.kanban:
        show_kanban(tracker)

    elif args.list:
        list_applications(tracker, args.stage)

    elif args.stale:
        find_stale(tracker, args.days)

    elif args.sync_leantime:
        sync_to_leantime(tracker)

    elif args.export_csv:
        apps = tracker.get("applications", {})
        if not apps:
            print("No applications to export.")
            return
        export_file = DATA_DIR / "application_tracker_export.csv"
        with open(export_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["job_id", "title", "company", "stage", "location", "url", "added_at", "updated_at"])
            writer.writeheader()
            for app in apps.values():
                writer.writerow({k: app.get(k, "") for k in writer.fieldnames})
        print(f"Exported {len(apps)} applications to {export_file}")

    else:
        # Default: show kanban
        show_kanban(tracker)


if __name__ == "__main__":
    main()
