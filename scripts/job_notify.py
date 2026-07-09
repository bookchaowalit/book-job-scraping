#!/usr/bin/env python3
"""
Daily job scraping + matching + Telegram notification.
Runs full scrape pipeline, matches jobs, and sends top matches to Telegram.

Usage:
    python3 job_notify.py
    python3 job_notify.py --min-score 8
    python3 job_notify.py --top 10
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import scraper and matcher
from scrape_job_postings import main as scrape_main
from match_jobs import score_job, is_relevant_title, is_preferred_location, RELOCATION_KEYWORDS, parse_salary_value

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
INPUT_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_LOG = DATA_DIR / "apply_tracker.csv"
PIPELINE_METRICS = DATA_DIR / "pipeline_metrics.json"

# Priority scoring weights
PRIORITY_WEIGHTS = {
    "base_score": 1.0,       # Base match score
    "salary": 0.3,           # Salary factor
    "freshness": 0.2,        # Recency factor
    "board_quality": 0.15,   # Board effectiveness
    "apply_history": -0.2,   # Penalty for already-applied companies
}


def send_telegram(message: str, inline_buttons: list = None):
    """Send message to Telegram with optional inline buttons."""
    import httpx
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    
    # Add inline keyboard buttons if provided
    if inline_buttons:
        keyboard = {"inline_keyboard": inline_buttons}
        payload["reply_markup"] = json.dumps(keyboard)
    
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"✓ Telegram notification sent")
        return True
    except Exception as e:
        print(f"✗ Telegram notification failed: {e}")
        return False


def log_apply_status(url: str, status: str, note: str = ""):
    """Log apply status to tracker CSV (update-in-place to avoid duplicates)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["url", "status", "note", "updated_at"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                    row["updated_at"] = now
                    found = True
                entries.append(row)

    if not found:
        entries.append({"url": url, "status": status, "note": note, "updated_at": now})

    # Write back (deduplicated, filtered to fieldnames only)
    with open(APPLY_LOG, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def load_board_quality() -> dict:
    """Load board effectiveness scores from pipeline_metrics.json."""
    if not PIPELINE_METRICS.exists():
        return {}
    try:
        with open(PIPELINE_METRICS, "r") as f:
            metrics = json.load(f)
        boards = metrics.get("board_effectiveness", [])
        return {b["source"]: b.get("score", 0) for b in boards if b.get("source")}
    except Exception:
        return {}


def load_applied_companies() -> set:
    """Load set of companies already applied to."""
    companies = set()
    if not APPLY_LOG.exists():
        return companies
    try:
        with open(APPLY_LOG, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "applied":
                    # We don't have company in tracker, but we track URLs
                    pass
    except Exception:
        pass
    return companies


def compute_freshness_score(posted: str) -> float:
    """Compute freshness score (0-10) based on posted date string."""
    if not posted:
        return 3.0  # Unknown = medium
    posted_lower = posted.lower().strip()
    if "hour" in posted_lower or "minute" in posted_lower or "second" in posted_lower:
        return 10.0
    if "today" in posted_lower or "yesterday" in posted_lower:
        return 9.0
    if "day" in posted_lower:
        try:
            days = int("".join(filter(str.isdigit, posted_lower)) or "0")
            if days <= 1:
                return 9.0
            elif days <= 3:
                return 8.0
            elif days <= 7:
                return 6.0
            elif days <= 14:
                return 4.0
            else:
                return 2.0
        except (ValueError, TypeError):
            return 3.0
    return 3.0


def compute_priority_score(job: dict, board_quality: dict) -> float:
    """Compute enhanced priority score combining multiple factors.
    Returns a float used for final sorting of notifications."""
    base_score = float(job.get("_score", 0))

    # Salary factor (0-10 scale)
    salary_val = parse_salary_value(job.get("salary", ""))
    if salary_val >= 200000:
        salary_score = 10.0
    elif salary_val >= 150000:
        salary_score = 8.0
    elif salary_val >= 100000:
        salary_score = 6.0
    elif salary_val >= 70000:
        salary_score = 4.0
    elif salary_val > 0:
        salary_score = 2.0
    else:
        salary_score = 1.0  # No salary info = low but not zero

    # Freshness factor (0-10)
    freshness = compute_freshness_score(job.get("posted", ""))

    # Board quality factor (0-10)
    source = job.get("source", "")
    bq = board_quality.get(source, 5.0)  # Default medium if unknown

    # Combine with weights
    w = PRIORITY_WEIGHTS
    priority = (
        base_score * w["base_score"]
        + salary_score * w["salary"]
        + freshness * w["freshness"]
        + bq * w["board_quality"]
    )

    return round(priority, 1)


def format_job_message(jobs: list, total_scraped: int, total_matched: int) -> tuple:
    """Format top jobs as Telegram message with inline buttons.
    Returns (message_text, inline_buttons_list)."""
    
    lines = []
    lines.append(f"<b>🎯 TOP JOB MATCHES</b>")
    lines.append(f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>")
    lines.append("")
    lines.append(f"📊 Scraped: {total_scraped} | Matched: {total_matched}")
    lines.append("")
    
    # Build inline buttons: each job gets Apply + Skip buttons
    inline_buttons = []
    
    for i, job in enumerate(jobs, 1):
        score = job["_score"]
        stars = "⭐" * min(score // 3, 5)
        reloc = " 🏝️" if job.get("_relocation") else ""
        ai_fit_str = f" [AI:{job['_ai_fit']}%]" if job.get("_ai_fit") else ""
        
        title = job.get("title", "")[:50]
        company = job.get("company", "")[:30]
        location = job.get("location", "")[:30]
        salary = job.get("salary", "")
        url = job.get("url", "")
        
        lines.append(f"<b>{i}. {stars} (score: {score}){reloc}{ai_fit_str}</b>")
        lines.append(f"  {title}")
        if company:
            lines.append(f"  🏢 {company}")
        if location:
            lines.append(f"  📍 {location}")
        if salary:
            lines.append(f"  💰 {salary}")
        if job.get("_ai_missing"):
            lines.append(f"  ⚠️ Missing: {job['_ai_missing'][:40]}")
        if url:
            lines.append(f"  🔗 {url[:60]}")
        lines.append("")
        
        # Add inline buttons for this job
        if url:
            row = []
            row.append({"text": f"✅ Apply #{i}", "url": url})
            row.append({"text": f"📋 Applied #{i}", "callback_data": f"applied:{i}"})
            row.append({"text": f"⏭️ Skip #{i}", "callback_data": f"skip:{i}"})
            inline_buttons.append(row)
    
    lines.append("─────────────────")
    lines.append(f"<i>✅ Apply = open link | 📋 Applied = mark done | ⏭️ Skip = pass</i>")
    
    return "\n".join(lines), inline_buttons


def main():
    parser = argparse.ArgumentParser(description="Daily job scrape + Telegram notify")
    parser.add_argument("--top", type=int, default=10, help="Send top N jobs")
    parser.add_argument("--min-score", type=int, default=8, help="Minimum score to notify")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping, use existing data")
    parser.add_argument("--ai-match", action="store_true", help="Use AI to analyze job fit (slower)")
    parser.add_argument("--ai-limit", type=int, default=5, help="Limit AI analysis to top N jobs")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  JOB SCRAPING + TELEGRAM NOTIFICATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Step 1: Scrape
    if not args.skip_scrape:
        print("[1/3] Running full scrape...")
        try:
            scrape_main(
                boards="remoteok-api,himalayas,landing-jobs,jobicy,indeed,seek-au,seek-nz,jobthai,jobsdb-th,jobbkk,hn-hiring,remotive,upwork,fastwork,fiverr,toptal,arc,workingnomads,turing,themuse",
                keywords="python,react,next.js,typescript,full-stack,developer,AI engineer,backend,frontend,node.js,FastAPI,Django"
            )
        except Exception as e:
            print(f"✗ Scrape failed: {e}")
            sys.exit(1)
    else:
        print("[1/3] Skipping scrape (using existing data)")
    
    # Step 2: Match
    print("\n[2/3] Matching jobs...")
    if not INPUT_CSV.exists():
        print(f"✗ {INPUT_CSV} not found")
        sys.exit(1)
    
    jobs = []
    with open(INPUT_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    
    total_scraped = len(jobs)
    print(f"  Loaded {total_scraped} jobs")
    
    # Score and filter
    scored_jobs = []
    for job in jobs:
        score, matched, relocation = score_job(job)
        if score < args.min_score:
            continue
        if not is_relevant_title(job.get("title", "")):
            continue
        if not is_preferred_location(job.get("location", "")):
            continue
        job["_score"] = score
        job["_matched"] = ", ".join(matched)
        job["_relocation"] = "YES" if relocation else ""
        scored_jobs.append(job)
    
    # Priority scoring: factor in salary, freshness, board quality
    board_quality = load_board_quality()
    for job in scored_jobs:
        job["_priority"] = compute_priority_score(job, board_quality)
    scored_jobs.sort(key=lambda x: x["_priority"], reverse=True)
    total_matched = len(scored_jobs)

    # AI matching (optional)
    if args.ai_match and scored_jobs:
        print(f"\n🤖 Running AI resume matching on top {args.ai_limit} jobs...")
        from match_jobs import ai_match_job
        ai_count = 0
        for job in scored_jobs[:args.ai_limit]:
            url = job.get("url", "")
            if not url:
                continue
            print(f"  Analyzing: {job.get('title', '')[:40]}...")
            ai_result = ai_match_job(url)
            job["_ai_fit"] = ai_result.get("fit_score", 0)
            job["_ai_missing"] = ", ".join(ai_result.get("missing_skills", []))
            job["_ai_notes"] = ai_result.get("notes", "")[:100]
            ai_count += 1
            print(f"    AI fit: {job['_ai_fit']}% | Missing: {job['_ai_missing'] or 'none'}")
        print(f"  ✓ AI analysis complete ({ai_count} jobs)")
        # Re-sort by combined score
        for job in scored_jobs[:args.ai_limit]:
            ai_fit = job.get("_ai_fit", 0)
            if ai_fit > 0:
                job["_score"] = job["_score"] + (ai_fit // 10)
        scored_jobs.sort(key=lambda x: x["_score"], reverse=True)
    
    top_jobs = scored_jobs[:args.top]

    print(f"  Matched: {total_matched} jobs (score >= {args.min_score})")
    print(f"  Top {len(top_jobs)} jobs selected (by priority score)")
    
    # Step 3: Notify
    if not top_jobs:
        print("\n[3/3] No high-score jobs found, skipping notification")
        return
    
    print(f"\n[3/3] Sending Telegram notification...")
    message, inline_buttons = format_job_message(top_jobs, total_scraped, total_matched)
    
    if send_telegram(message, inline_buttons=inline_buttons):
        # Log all sent jobs as "notified" in tracker
        for job in top_jobs:
            url = job.get("url", "")
            if url:
                log_apply_status(url, "notified", f"score={job['_score']}")
        print(f"\n✓ Done! Sent {len(top_jobs)} jobs to Telegram with inline buttons")
        print(f"  Apply tracker: {APPLY_LOG}")

        # Persist matched jobs to CSV (including AI fields)
        _persist_matched_jobs(scored_jobs, args.ai_match)
    else:
        print(f"\n✗ Notification failed")
        sys.exit(1)


def _persist_matched_jobs(scored_jobs: list, has_ai: bool = False):
    """Persist scored jobs to matched_jobs.csv for callback handler reference."""
    fieldnames = ["title", "company", "location", "salary", "url", "source",
                  "keyword", "posted", "_score", "_priority", "_matched", "_relocation"]
    if has_ai:
        fieldnames.extend(["_ai_fit", "_ai_missing", "_ai_notes"])
    with open(MATCHED_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for job in scored_jobs:
            writer.writerow(job)
    print(f"  Saved {len(scored_jobs)} matched jobs to {MATCHED_CSV}")


if __name__ == "__main__":
    main()
