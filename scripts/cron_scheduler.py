#!/usr/bin/env python3
"""
Pipeline Cron Scheduler — Automated daily/weekly pipeline runs.

Generates a crontab configuration and provides a scheduler daemon
for running pipeline steps on schedule:

Daily (6:00 AM):
  - Full pipeline run (scrape + match + describe + promote + notify)
  - Follow-up tracker with email generation
  - Portfolio sync

Weekly (Sunday 8:00 PM):
  - Company intelligence enrichment
  - Deep JD scrape for top matches
  - Weekly report to Telegram
  - Freelance proposal generation

Usage:
    python3 cron_scheduler.py --install          # Install crontab entries
    python3 cron_scheduler.py --uninstall        # Remove crontab entries
    python3 cron_scheduler.py --show             # Show current schedule
    python3 cron_scheduler.py --daemon           # Run as daemon scheduler
    python3 cron_scheduler.py --run-daily        # Run daily tasks now
    python3 cron_scheduler.py --run-weekly       # Run weekly tasks now
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "scripts"
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
CRON_LOG = DATA_DIR / "cron_scheduler_log.json"
CRON_MARKER = "# BOOK-PIPELINE-CRON"

PYTHON = sys.executable


def get_daily_commands():
    """Get commands for daily pipeline run."""
    return [
        {
            "name": "pipeline_full",
            "label": "Full Pipeline Run",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'pipeline_runner.py'} --full --send-telegram",
            "schedule": "0 6 * * *",  # 6:00 AM daily
        },
        {
            "name": "followup",
            "label": "Follow-up Tracker",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'followup_tracker.py'} --days 5 --send-telegram --generate-emails",
            "schedule": "30 6 * * *",  # 6:30 AM daily
        },
        {
            "name": "portfolio_sync",
            "label": "Portfolio Sync",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'portfolio_sync.py'} --send-telegram",
            "schedule": "0 7 * * *",  # 7:00 AM daily
        },
        {
            "name": "daily_digest",
            "label": "Daily Digest",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'daily_digest.py'} --send-telegram",
            "schedule": "0 8 * * *",  # 8:00 AM daily
        },
        {
            "name": "daily_job_digest",
            "label": "Daily Job Digest",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'daily_job_digest.py'} --send-telegram",
            "schedule": "30 8 * * *",  # 8:30 AM daily
        },
        {
            "name": "scam_scan",
            "label": "Job Scam Scan",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'job_scam_detector.py'} --top 20 --send-telegram",
            "schedule": "0 9 * * *",  # 9:00 AM daily
        },
        {
            "name": "auto_seed",
            "label": "Auto-Seed Application Tracker",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'auto_seed_tracker.py'} --min-score 8 --send-telegram",
            "schedule": "30 9 * * *",  # 9:30 AM daily
        },
        {
            "name": "pipeline_health",
            "label": "Pipeline Health Monitor",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'pipeline_health_monitor.py'} --send-telegram",
            "schedule": "0 10 * * *",  # 10:00 AM daily
        },
    ]


def get_weekly_commands():
    """Get commands for weekly pipeline run."""
    return [
        {
            "name": "deep_scrape",
            "label": "Deep JD Scrape",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'deep_scrape_jd.py'} --top 20 --send-telegram",
            "schedule": "0 20 * * 0",  # Sunday 8:00 PM
        },
        {
            "name": "company_intel",
            "label": "Company Intelligence",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'company_intel.py'} --top 15 --send-telegram",
            "schedule": "30 20 * * 0",  # Sunday 8:30 PM
        },
        {
            "name": "freelance_proposal",
            "label": "Freelance Proposals",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'freelance_proposal.py'} --top 5 --send-telegram",
            "schedule": "0 21 * * 0",  # Sunday 9:00 PM
        },
        {
            "name": "weekly_report",
            "label": "Weekly Report",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'weekly_report.py'} --send-telegram",
            "schedule": "30 21 * * 0",  # Sunday 9:30 PM
        },
        {
            "name": "auto_blog",
            "label": "Auto Blog Generator",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'auto_blog.py'} --send-telegram",
            "schedule": "0 22 * * 0",  # Sunday 10:00 PM
        },
        {
            "name": "rss_aggregate",
            "label": "RSS Feed Aggregation",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'rss_aggregator.py'} --send-telegram",
            "schedule": "30 22 * * 0",  # Sunday 10:30 PM
        },
        {
            "name": "linkedin_optimizer",
            "label": "LinkedIn Profile Optimizer",
            "cmd": f"cd {ROOT} && {PYTHON} {SCRIPTS_DIR / 'linkedin_profile_optimizer.py'} --send-telegram",
            "schedule": "0 23 * * 0",  # Sunday 11:00 PM
        },
    ]


def run_task(task, dry_run=False):
    """Run a single pipeline task."""
    print(f"\n{'='*60}")
    print(f"  Running: {task['label']}")
    print(f"  Command: {task['cmd']}")
    print(f"{'='*60}")

    if dry_run:
        print("[DRY-RUN] Skipping execution")
        return {"status": "dry-run", "task": task["name"]}

    start = time.time()
    try:
        result = subprocess.run(
            task["cmd"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        elapsed = time.time() - start
        status = "success" if result.returncode == 0 else "failed"
        print(f"[{status.upper()}] {task['label']} ({elapsed:.1f}s)")
        if result.returncode != 0:
            print(f"  STDERR: {result.stderr[:500]}")
        return {
            "status": status,
            "task": task["name"],
            "elapsed": round(elapsed, 1),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {task['label']} exceeded 600s")
        return {"status": "timeout", "task": task["name"]}
    except Exception as e:
        print(f"[ERROR] {task['label']}: {e}")
        return {"status": "error", "task": task["name"], "error": str(e)}


def run_daily(dry_run=False):
    """Run all daily tasks."""
    print("\n📅 Running DAILY pipeline tasks...")
    tasks = get_daily_commands()
    results = []
    for task in tasks:
        result = run_task(task, dry_run=dry_run)
        results.append(result)
    log_run("daily", results)
    return results


def run_weekly(dry_run=False):
    """Run all weekly tasks."""
    print("\n📅 Running WEEKLY pipeline tasks...")
    tasks = get_weekly_commands()
    results = []
    for task in tasks:
        result = run_task(task, dry_run=dry_run)
        results.append(result)
    log_run("weekly", results)
    return results


def log_run(run_type, results):
    """Log scheduler run."""
    log = {}
    if CRON_LOG.exists():
        try:
            log = json.loads(CRON_LOG.read_text())
        except Exception:
            log = {}
    if "runs" not in log:
        log["runs"] = []
    log["runs"].append({
        "type": run_type,
        "timestamp": datetime.now().isoformat(),
        "results": results,
    })
    log["runs"] = log["runs"][-100:]  # Keep last 100 runs
    log["last_daily"] = datetime.now().isoformat() if run_type == "daily" else log.get("last_daily", "")
    log["last_weekly"] = datetime.now().isoformat() if run_type == "weekly" else log.get("last_weekly", "")
    CRON_LOG.write_text(json.dumps(log, indent=2))


def install_crontab():
    """Install crontab entries for pipeline scheduling."""
    all_tasks = get_daily_commands() + get_weekly_commands()

    # Get existing crontab
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except Exception:
        existing = ""

    # Remove old entries
    lines = [
        line for line in existing.split("\n")
        if CRON_MARKER not in line and line.strip()
    ]

    # Add new entries
    for task in all_tasks:
        cron_line = f"{task['schedule']} {task['cmd']} >> {DATA_DIR / 'cron.log'} 2>&1 {CRON_MARKER}"
        lines.append(cron_line)

    new_crontab = "\n".join(lines) + "\n"

    # Install
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            print(f"[OK] Installed {len(all_tasks)} cron entries")
            show_schedule()
        else:
            print(f"[ERROR] crontab install failed: {proc.stderr}")
    except Exception as e:
        print(f"[ERROR] Failed to install crontab: {e}")


def uninstall_crontab():
    """Remove crontab entries."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except Exception:
        existing = ""

    lines = [
        line for line in existing.split("\n")
        if CRON_MARKER not in line
    ]
    new_crontab = "\n".join(lines) + "\n" if lines else ""

    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            print("[OK] Removed pipeline cron entries")
        else:
            print(f"[ERROR] crontab uninstall failed: {proc.stderr}")
    except Exception as e:
        print(f"[ERROR] Failed to uninstall crontab: {e}")


def show_schedule():
    """Show current pipeline schedule."""
    print("\n📅 Pipeline Schedule:")
    print("-" * 60)

    print("\n  DAILY TASKS:")
    for task in get_daily_commands():
        print(f"    {task['schedule']:15s}  {task['label']}")

    print("\n  WEEKLY TASKS:")
    for task in get_weekly_commands():
        print(f"    {task['schedule']:15s}  {task['label']}")

    # Show actual crontab
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode == 0:
            cron_lines = [
                l for l in result.stdout.split("\n")
                if CRON_MARKER in l
            ]
            if cron_lines:
                print(f"\n  Active crontab entries: {len(cron_lines)}")
            else:
                print("\n  ⚠️  No pipeline entries in crontab (run --install)")
        else:
            print("\n  ⚠️  No crontab configured")
    except Exception:
        print("\n  ⚠️  Could not read crontab")

    # Show last run info
    if CRON_LOG.exists():
        try:
            log = json.loads(CRON_LOG.read_text())
            print(f"\n  Last daily run: {log.get('last_daily', 'never')[:19]}")
            print(f"  Last weekly run: {log.get('last_weekly', 'never')[:19]}")
        except Exception:
            pass
    print()


def run_daemon():
    """Run as a simple daemon scheduler (for systems without cron)."""
    print("🤖 Starting pipeline scheduler daemon...")
    print("   Press Ctrl+C to stop\n")

    daily_hour = 6
    weekly_day = 0  # Sunday
    weekly_hour = 20

    while True:
        now = datetime.now()
        try:
            # Daily tasks
            if now.hour == daily_hour and now.minute == 0:
                print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}] Triggering daily tasks...")
                run_daily()

            # Weekly tasks
            if now.weekday() == weekly_day and now.hour == weekly_hour and now.minute == 0:
                print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}] Triggering weekly tasks...")
                run_weekly()

            time.sleep(55)  # Check every ~1 minute
        except KeyboardInterrupt:
            print("\n[STOP] Scheduler daemon stopped")
            break
        except Exception as e:
            print(f"[ERROR] Daemon loop: {e}")
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Pipeline Cron Scheduler")
    parser.add_argument("--install", action="store_true", help="Install crontab entries")
    parser.add_argument("--uninstall", action="store_true", help="Remove crontab entries")
    parser.add_argument("--show", action="store_true", help="Show current schedule")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon scheduler")
    parser.add_argument("--run-daily", action="store_true", help="Run daily tasks now")
    parser.add_argument("--run-weekly", action="store_true", help="Run weekly tasks now")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()

    print("=" * 60)
    print("  Pipeline Cron Scheduler")
    print("=" * 60)

    if args.install:
        install_crontab()
    elif args.uninstall:
        uninstall_crontab()
    elif args.show:
        show_schedule()
    elif args.daemon:
        run_daemon()
    elif args.run_daily:
        run_daily(dry_run=args.dry_run)
    elif args.run_weekly:
        run_weekly(dry_run=args.dry_run)
    else:
        show_schedule()
        parser.print_help()


if __name__ == "__main__":
    main()
