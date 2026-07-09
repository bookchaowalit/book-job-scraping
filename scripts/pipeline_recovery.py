#!/usr/bin/env python3
"""
Pipeline Health Auto-Recovery — Detect failed cron runs, auto-retry with backoff,
alert on repeated failures, and maintain health history.

Usage:
    python pipeline_recovery.py --check
    python pipeline_recovery.py --recover
    python pipeline_recovery.py --history [--days 7]
    python pipeline_recovery.py --reset
    python pipeline_recovery.py --install-cron
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
HEALTH_DIR = DATA_DIR / "pipeline_health"
HEALTH_LOG = HEALTH_DIR / "health_log.json"
RECOVERY_STATE = HEALTH_DIR / "recovery_state.json"
PIPELINE_RUNNER = SCRIPT_DIR / "pipeline_runner.py"

# Telegram notification
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# Recovery settings
MAX_RETRIES = 3
BACKOFF_BASE_MINUTES = 5
FAILURE_THRESHOLD = 3  # Alert after N consecutive failures

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def send_telegram(message):
    """Send Telegram notification."""
    if not HAS_REQUESTS or not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass


def load_health_log():
    """Load pipeline health log."""
    if HEALTH_LOG.exists():
        return json.loads(HEALTH_LOG.read_text())
    return {"runs": [], "last_check": None}


def save_health_log(log):
    """Save pipeline health log."""
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    log["last_check"] = datetime.now().isoformat()
    HEALTH_LOG.write_text(json.dumps(log, indent=2, default=str))


def load_recovery_state():
    """Load recovery state."""
    if RECOVERY_STATE.exists():
        return json.loads(RECOVERY_STATE.read_text())
    return {"consecutive_failures": 0, "last_recovery": None, "retry_count": 0, "next_retry": None}


def save_recovery_state(state):
    """Save recovery state."""
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    RECOVERY_STATE.write_text(json.dumps(state, indent=2, default=str))


def check_pipeline_health():
    """Check if the pipeline ran successfully today."""
    health_log = load_health_log()
    runs = health_log.get("runs", [])

    today = datetime.now().strftime("%Y-%m-%d")
    today_runs = [r for r in runs if r.get("date", "") == today]

    # Check for recent successful run
    last_success = None
    last_failure = None
    for run in reversed(runs):
        if run.get("status") == "success" and not last_success:
            last_success = run
        if run.get("status") == "failure" and not last_failure:
            last_failure = run

    recovery_state = load_recovery_state()
    consecutive_failures = recovery_state.get("consecutive_failures", 0)

    print(f"\n🔍 PIPELINE HEALTH CHECK")
    print(f"  Date: {today}")
    print(f"  Today's runs: {len(today_runs)}")
    print(f"  Total runs logged: {len(runs)}")
    print(f"  Consecutive failures: {consecutive_failures}")

    if today_runs:
        latest = today_runs[-1]
        print(f"  Latest run: {latest.get('status', 'unknown')} at {latest.get('time', 'N/A')}")
        if latest.get("status") == "success":
            print(f"  ✅ Pipeline ran successfully today")
            return True
        else:
            print(f"  ❌ Latest run failed")
    else:
        print(f"  ⚠️  No runs today yet")

    # Check if pipeline is overdue
    if last_success:
        last_date = datetime.fromisoformat(last_success["date"] + "T" + last_success.get("time", "00:00"))
        hours_since = (datetime.now() - last_date).total_seconds() / 3600
        print(f"  Hours since last success: {hours_since:.1f}")
        if hours_since > 48:
            print(f"  🚨 PIPELINE OVERDUE — No success in {hours_since:.0f} hours!")

    return len(today_runs) > 0 and today_runs[-1].get("status") == "success"


def record_run(status, details=""):
    """Record a pipeline run result."""
    health_log = load_health_log()
    run_record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "status": status,
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }
    health_log["runs"].append(run_record)

    # Keep only last 90 days
    cutoff = (datetime.now() - timedelta(days=90)).isoformat()
    health_log["runs"] = [r for r in health_log["runs"] if r.get("timestamp", "") > cutoff]

    save_health_log(health_log)
    return run_record


def attempt_recovery():
    """Attempt to recover from pipeline failures."""
    recovery_state = load_recovery_state()
    consecutive_failures = recovery_state.get("consecutive_failures", 0)
    retry_count = recovery_state.get("retry_count", 0)

    print(f"\n🔄 PIPELINE RECOVERY")
    print(f"  Consecutive failures: {consecutive_failures}")
    print(f"  Retry count: {retry_count}")

    # Check if we should retry
    if recovery_state.get("next_retry"):
        next_retry = datetime.fromisoformat(recovery_state["next_retry"])
        if datetime.now() < next_retry:
            wait_minutes = (next_retry - datetime.now()).total_seconds() / 60
            print(f"  ⏳ Next retry in {wait_minutes:.0f} minutes")
            return False

    if retry_count >= MAX_RETRIES:
        print(f"  🚨 Max retries ({MAX_RETRIES}) reached. Manual intervention needed.")
        send_telegram(
            f"🚨 *Pipeline Recovery Failed*\n"
            f"Max retries ({MAX_RETRIES}) exhausted after {consecutive_failures} consecutive failures.\n"
            f"Manual intervention required!\n"
            f"Run: `python pipeline_recovery.py --check`"
        )
        return False

    # Calculate backoff
    backoff_minutes = BACKOFF_BASE_MINUTES * (2 ** retry_count)
    next_retry_time = datetime.now() + timedelta(minutes=backoff_minutes)

    print(f"  Attempting recovery (retry {retry_count + 1}/{MAX_RETRIES})...")
    print(f"  Backoff: {backoff_minutes} minutes")

    # Run pipeline in quick mode
    try:
        result = subprocess.run(
            [sys.executable, str(PIPELINE_RUNNER), "--steps", "match_jobs,auto_promote"],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode == 0:
            print(f"  ✅ Recovery successful!")
            record_run("recovery_success", f"Retry {retry_count + 1}")
            send_telegram(
                f"✅ *Pipeline Recovered*\n"
                f"Auto-recovery succeeded on retry {retry_count + 1}.\n"
                f"Previous failures: {consecutive_failures}"
            )
            # Reset state
            recovery_state["consecutive_failures"] = 0
            recovery_state["retry_count"] = 0
            recovery_state["next_retry"] = None
            recovery_state["last_recovery"] = datetime.now().isoformat()
            save_recovery_state(recovery_state)
            return True
        else:
            print(f"  ❌ Recovery failed: {result.stderr[:200]}")
            record_run("recovery_failure", result.stderr[:200])

            # Update state
            recovery_state["retry_count"] = retry_count + 1
            recovery_state["next_retry"] = next_retry_time.isoformat()
            save_recovery_state(recovery_state)
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Recovery timed out")
        record_run("recovery_timeout", "120s timeout")
        recovery_state["retry_count"] = retry_count + 1
        recovery_state["next_retry"] = next_retry_time.isoformat()
        save_recovery_state(recovery_state)
        return False
    except Exception as e:
        print(f"  ❌ Recovery error: {e}")
        record_run("recovery_error", str(e))
        return False


def show_history(days=7):
    """Show pipeline health history."""
    health_log = load_health_log()
    runs = health_log.get("runs", [])

    if not runs:
        print("No health history yet.")
        return

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent_runs = [r for r in runs if r.get("timestamp", "") > cutoff]

    if not recent_runs:
        print(f"No runs in the last {days} days.")
        return

    # Group by date
    by_date = {}
    for run in recent_runs:
        date = run.get("date", "unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(run)

    print(f"\n📊 PIPELINE HEALTH HISTORY (last {days} days)\n")
    print(f"  {'Date':<12} {'Runs':<6} {'Success':<8} {'Failed':<8} {'Status'}")
    print(f"  {'-'*50}")

    total_success = 0
    total_failed = 0

    for date in sorted(by_date.keys(), reverse=True):
        date_runs = by_date[date]
        success = sum(1 for r in date_runs if "success" in r.get("status", ""))
        failed = sum(1 for r in date_runs if "fail" in r.get("status", "") or "error" in r.get("status", ""))
        total_success += success
        total_failed += failed

        status = "✅" if success > 0 and failed == 0 else "⚠️" if success > 0 else "❌"
        print(f"  {date:<12} {len(date_runs):<6} {success:<8} {failed:<8} {status}")

    print(f"\n  Summary: {total_success} successes, {total_failed} failures")
    if total_success + total_failed > 0:
        rate = total_success / (total_success + total_failed) * 100
        print(f"  Health rate: {rate:.0f}%")


def reset_state():
    """Reset recovery state."""
    save_recovery_state({
        "consecutive_failures": 0,
        "last_recovery": None,
        "retry_count": 0,
        "next_retry": None,
    })
    print("Recovery state reset.")


def install_cron():
    """Install cron job for health monitoring."""
    print("Installing pipeline health monitoring cron job...\n")

    cron_line = "*/30 * * * * /usr/bin/python3 /home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping/scripts/pipeline_recovery.py --recover >> /home/bookchaowalit/book-everything/solo-empire/data/pipeline_health/cron.log 2>&1"

    print(f"  Cron entry:\n  {cron_line}\n")
    print("  To install, run:")
    print(f'  (crontab -l 2>/dev/null; echo "{cron_line}") | crontab -')
    print("\n  This will check pipeline health every 30 minutes and auto-recover if needed.")


def main():
    parser = argparse.ArgumentParser(description="Pipeline Health Auto-Recovery")
    parser.add_argument("--check", action="store_true", help="Check pipeline health")
    parser.add_argument("--recover", action="store_true", help="Attempt recovery")
    parser.add_argument("--history", action="store_true", help="Show health history")
    parser.add_argument("--days", type=int, default=7, help="History days")
    parser.add_argument("--reset", action="store_true", help="Reset recovery state")
    parser.add_argument("--install-cron", action="store_true", help="Install monitoring cron")
    parser.add_argument("--record", choices=["success", "failure"], help="Manually record a run")
    parser.add_argument("--details", default="", help="Details for manual record")
    args = parser.parse_args()

    if args.check:
        success = check_pipeline_health()
        if not success:
            # Record the failure
            recovery_state = load_recovery_state()
            recovery_state["consecutive_failures"] = recovery_state.get("consecutive_failures", 0) + 1
            save_recovery_state(recovery_state)

            if recovery_state["consecutive_failures"] >= FAILURE_THRESHOLD:
                send_telegram(
                    f"⚠️ *Pipeline Alert*\n"
                    f"{recovery_state['consecutive_failures']} consecutive failures detected.\n"
                    f"Auto-recovery will be attempted."
                )

    elif args.recover:
        attempt_recovery()

    elif args.history:
        show_history(args.days)

    elif args.reset:
        reset_state()

    elif args.install_cron:
        install_cron()

    elif args.record:
        record_run(args.record, args.details)
        print(f"Recorded: {args.record} — {args.details}")

    else:
        # Default: check + show history
        check_pipeline_health()
        print()
        show_history(3)


if __name__ == "__main__":
    main()
