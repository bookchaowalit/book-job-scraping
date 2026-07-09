#!/usr/bin/env python3
"""
Daily Job Digest — Telegram Bot
Sends automated daily Telegram message with top matched jobs, stats, and action items.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

# Telegram config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_matched_jobs(limit=100):
    """Load matched jobs."""
    jobs = []
    csv_path = DATA_DIR / "matched_jobs.csv"
    if not csv_path.exists():
        return jobs
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                jobs.append(row)
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    return jobs


def load_applications():
    """Load application tracker."""
    tracker_path = DATA_DIR / "application_tracker.json"
    if not tracker_path.exists():
        return {"applications": []}
    try:
        with open(tracker_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"applications": []}


def load_health_log():
    """Load pipeline health log."""
    health_path = DATA_DIR / "pipeline_health" / "health_log.json"
    if not health_path.exists():
        return {}
    try:
        with open(health_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_recent_jobs(jobs, days=1):
    """Get jobs discovered in the last N days."""
    recent = []
    cutoff = datetime.now() - timedelta(days=days)
    for job in jobs:
        scraped_at = job.get("scraped_at", job.get("discovered_at", ""))
        if scraped_at:
            try:
                dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
                if dt.replace(tzinfo=None) >= cutoff:
                    recent.append(job)
            except Exception:
                pass
    return recent


def get_top_jobs(jobs, n=5):
    """Get top jobs by match score."""
    scored = []
    for job in jobs:
        score = float(job.get("match_score", job.get("score", 0)) or 0)
        scored.append((score, job))
    scored.sort(key=lambda x: -x[0])
    return [j for _, j in scored[:n]]


def compute_stats(jobs, applications):
    """Compute pipeline statistics."""
    apps = applications.get("applications", [])
    stages = {}
    for app in apps:
        stage = app.get("stage", "unknown")
        stages[stage] = stages.get(stage, 0) + 1

    return {
        "total_matched": len(jobs),
        "total_applications": len(apps),
        "stages": stages,
        "applied": stages.get("applied", 0),
        "screening": stages.get("screening", 0),
        "interview": stages.get("technical", 0) + stages.get("onsite", 0),
        "offers": stages.get("offer", 0),
    }


def format_digest_message(top_jobs, recent_jobs, stats, health):
    """Format the daily digest message."""
    today = datetime.now().strftime("%A, %B %d, %Y")

    # Header
    msg = f"🎯 <b>Daily Job Digest</b>\n"
    msg += f"📅 {today}\n"
    msg += f"{'━' * 25}\n\n"

    # Stats summary
    msg += f"📊 <b>Pipeline Stats</b>\n"
    msg += f"  📋 Total matched: {stats['total_matched']}\n"
    msg += f"  📨 Applications: {stats['total_applications']}\n"
    msg += f"  📝 Applied: {stats['applied']}\n"
    msg += f"  🔍 Screening: {stats['screening']}\n"
    msg += f"  🎤 Interview: {stats['interview']}\n"
    msg += f"  🎉 Offers: {stats['offers']}\n\n"

    # Top jobs
    if top_jobs:
        msg += f"⭐ <b>Top {len(top_jobs)} Matched Jobs</b>\n"
        for i, job in enumerate(top_jobs, 1):
            title = job.get("title", "N/A")[:40]
            company = job.get("company", "N/A")[:25]
            score = job.get("match_score", job.get("score", "N/A"))
            location = job.get("location", "")[:20]
            url = job.get("url", job.get("job_url", ""))

            msg += f"\n  {i}. <b>{title}</b>\n"
            msg += f"     🏢 {company}"
            if location:
                msg += f" | 📍 {location}"
            msg += f"\n     🎯 Score: {score}"
            if url:
                msg += f"\n     🔗 {url[:80]}"
            msg += "\n"

    # Recent jobs
    if recent_jobs and len(recent_jobs) > 0:
        msg += f"\n🆕 <b>New Jobs Today ({len(recent_jobs)})</b>\n"
        for job in recent_jobs[:5]:
            title = job.get("title", "N/A")[:35]
            company = job.get("company", "N/A")[:20]
            msg += f"  • {title} @ {company}\n"

    # Action items
    msg += f"\n{'━' * 25}\n"
    msg += f"📌 <b>Action Items</b>\n"

    if stats["screening"] > 0:
        msg += f"  ⚡ {stats['screening']} applications in screening — follow up!\n"
    if stats["interview"] > 0:
        msg += f"  🎤 {stats['interview']} interviews — prepare!\n"
    if stats["total_matched"] > 50:
        msg += f"  📋 {stats['total_matched']} matched jobs — review and apply\n"
    if not recent_jobs:
        msg += f"  ⚠️  No new jobs today — run pipeline\n"

    msg += f"\n🤖 Auto-generated by Job Pipeline"

    return msg


def send_telegram(message, parse_mode="HTML"):
    """Send message via Telegram Bot API."""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("✅ Telegram message sent!")
            return True
        else:
            print(f"❌ Telegram error: HTTP {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Daily Job Digest — Telegram Bot")
    parser.add_argument("--send", action="store_true", help="Send daily digest")
    parser.add_argument("--preview", action="store_true", help="Preview without sending")
    parser.add_argument("--days", type=int, default=1, help="Days lookback for recent jobs")
    parser.add_argument("--top", type=int, default=5, help="Number of top jobs to show")
    parser.add_argument("--stats-only", action="store_true", help="Show stats only")
    args = parser.parse_args()

    # Load data
    jobs = load_matched_jobs()
    applications = load_applications()
    health = load_health_log()

    if not jobs:
        print("⚠️  No matched jobs found. Run pipeline first.")
        if args.preview or args.send:
            msg = "⚠️ <b>Job Pipeline Alert</b>\n\nNo matched jobs found. Please run the pipeline."
            if args.send:
                send_telegram(msg)
            else:
                print(msg)
        return

    # Compute stats
    stats = compute_stats(jobs, applications)
    recent = get_recent_jobs(jobs, args.days)
    top = get_top_jobs(jobs, args.top)

    if args.stats_only:
        print(f"\n📊 Pipeline Stats")
        print(f"{'=' * 40}")
        print(f"  Total matched: {stats['total_matched']}")
        print(f"  Applications: {stats['total_applications']}")
        print(f"  Stages: {json.dumps(stats['stages'], indent=2)}")
        return

    # Generate message
    msg = format_digest_message(top, recent, stats, health)

    if args.preview or args.send:
        print(f"\n{'=' * 50}")
        # Strip HTML for preview
        preview = msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        print(preview)
        print(f"{'=' * 50}")

    if args.send:
        send_telegram(msg)
    elif args.preview:
        print("\n(PREVIEW MODE — not sent)")

    if not any([args.send, args.preview, args.stats_only]):
        parser.print_help()


if __name__ == "__main__":
    main()
