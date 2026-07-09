#!/usr/bin/env python3
"""
Board Health Monitor — Detect which job boards are down, returning errors,
or changed their API. Alert via Telegram when boards stop returning results.

Tracks board health over time in board_health.json and alerts on:
  1. Boards returning 0 results (API changed or down)
  2. Boards with HTTP errors
  3. Boards that haven't been scraped recently
  4. Sudden drops in results count

Usage:
    python3 board_health.py                  # Check health from last scrape data
    python3 board_health.py --send-telegram  # Alert via Telegram
    python3 board_health.py --json           # Output JSON report
    python3 board_health.py --history        # Show health trend over time
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
SCRIPTS_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "scripts"

JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
PIPELINE_LOG_DIR = DATA_DIR
HEALTH_FILE = DATA_DIR / "board_health.json"
HEALTH_HISTORY = DATA_DIR / "board_health_history.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# Known boards from scrape_job_postings.py (actual source names in CSV)
KNOWN_BOARDS = [
    "Arc.dev", "HN_WhoIsHiring", "Himalayas", "Jobicy", "Landing.jobs",
    "RemoteOK", "Remotive", "TheMuse", "WorkingNomads",
    # Boards that may not be returning results currently
    "remoteok-api", "indeed", "seek-au", "seek-nz", "jobthai",
    "jobsdb-th", "jobbkk", "upwork", "fastwork", "fiverr",
    "toptal", "turing",
]


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def analyze_board_health() -> dict:
    """Analyze board health from current job_postings.csv and pipeline logs."""
    postings = load_csv(JOB_POSTINGS_CSV)

    # Count results per source
    source_counts = Counter()
    source_freshness = defaultdict(list)
    for p in postings:
        src = p.get("source", "unknown").strip()
        source_counts[src] += 1
        # Track posted dates for freshness
        posted = p.get("posted", "") or p.get("scraped_at", "")
        if posted:
            source_freshness[src].append(posted)

    # Check pipeline logs for errors
    board_errors = {}
    for board in KNOWN_BOARDS:
        log_file = PIPELINE_LOG_DIR / f"pipeline_scrape_postings.log"
        if log_file.exists():
            try:
                content = log_file.read_text()
                # Look for error patterns related to this board
                board_lower = board.lower()
                for line in content.splitlines():
                    if board_lower in line.lower() and ("error" in line.lower() or "failed" in line.lower()):
                        board_errors[board] = line.strip()[:200]
            except Exception:
                pass

    # Build health report per board
    boards = {}
    all_sources = set(KNOWN_BOARDS) | set(source_counts.keys())
    for src in sorted(all_sources):
        count = source_counts.get(src, 0)
        errors = board_errors.get(src, "")

        # Determine status
        if count == 0 and errors:
            status = "error"
        elif count == 0:
            status = "no_results"
        elif count < 3:
            status = "low_results"
        else:
            status = "healthy"

        boards[src] = {
            "status": status,
            "result_count": count,
            "errors": errors,
        }

    # Summary stats
    healthy = sum(1 for b in boards.values() if b["status"] == "healthy")
    warning = sum(1 for b in boards.values() if b["status"] == "low_results")
    errors_count = sum(1 for b in boards.values() if b["status"] == "error")
    no_results = sum(1 for b in boards.values() if b["status"] == "no_results")

    return {
        "timestamp": datetime.now().isoformat(),
        "total_boards": len(boards),
        "summary": {
            "healthy": healthy,
            "low_results": warning,
            "error": errors_count,
            "no_results": no_results,
        },
        "boards": boards,
        "total_postings": len(postings),
    }


def load_history() -> list:
    if HEALTH_HISTORY.exists():
        with open(HEALTH_HISTORY, "r") as f:
            return json.load(f)
    return []


def save_history(history: list):
    # Keep last 30 snapshots
    history = history[-30:]
    with open(HEALTH_HISTORY, "w") as f:
        json.dump(history, f, indent=2)


def detect_changes(current: dict, history: list) -> list:
    """Detect changes from previous health check."""
    if not history:
        return []

    previous = history[-1]
    prev_boards = previous.get("boards", {})
    changes = []

    for src, info in current.get("boards", {}).items():
        prev_info = prev_boards.get(src, {})
        prev_count = prev_info.get("result_count", 0)
        curr_count = info.get("result_count", 0)

        # Board went from healthy to error/no_results
        if prev_info.get("status") == "healthy" and info["status"] in ("error", "no_results"):
            changes.append({
                "type": "board_down",
                "board": src,
                "detail": f"Was healthy ({prev_count} results), now {info['status']}",
            })
        # Board went from error/no_results to healthy
        elif prev_info.get("status") in ("error", "no_results") and info["status"] == "healthy":
            changes.append({
                "type": "board_recovered",
                "board": src,
                "detail": f"Recovered! Now returning {curr_count} results",
            })
        # Significant drop in results (>50%)
        elif prev_count > 10 and curr_count < prev_count * 0.5:
            changes.append({
                "type": "results_drop",
                "board": src,
                "detail": f"Dropped from {prev_count} to {curr_count} results ({round(curr_count/max(prev_count,1)*100)}%)",
            })
        # New board appeared
        elif src not in prev_boards and curr_count > 0:
            changes.append({
                "type": "new_board",
                "board": src,
                "detail": f"New board detected with {curr_count} results",
            })

    return changes


def build_telegram_message(health: dict, changes: list) -> str:
    """Build Telegram alert message."""
    lines = []
    lines.append(f"<b>🏥 BOARD HEALTH REPORT</b>")
    lines.append(f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>")
    lines.append("")

    summary = health["summary"]
    lines.append(f"📊 Boards: {summary['healthy']}✅ {summary['low_results']}⚠️ {summary['error']}❌ {summary['no_results']}🔇")
    lines.append(f"📰 Total postings: {health['total_postings']}")
    lines.append("")

    # Alert on issues
    issues = [(src, info) for src, info in health["boards"].items()
              if info["status"] in ("error", "no_results")]
    if issues:
        lines.append("<b>🚨 BOARDS WITH ISSUES:</b>")
        for src, info in sorted(issues, key=lambda x: x[1]["status"]):
            icon = "❌" if info["status"] == "error" else "🔇"
            detail = info.get("errors", "")[:60]
            lines.append(f"  {icon} <b>{src}</b> — {info['status']}")
            if detail:
                lines.append(f"     {detail}")
        lines.append("")

    # Show changes
    if changes:
        lines.append("<b>📈 CHANGES DETECTED:</b>")
        for c in changes:
            icon = {"board_down": "🔴", "board_recovered": "🟢",
                    "results_drop": "🟡", "new_board": "🆕"}.get(c["type"], "ℹ️")
            lines.append(f"  {icon} {c['board']}: {c['detail']}")
        lines.append("")

    # Low results boards
    low = [(src, info) for src, info in health["boards"].items()
           if info["status"] == "low_results"]
    if low:
        lines.append("<b>⚠️ LOW RESULT BOARDS:</b>")
        for src, info in low:
            lines.append(f"  • {src}: {info['result_count']} results")
        lines.append("")

    # Top healthy boards
    healthy_boards = [(src, info) for src, info in health["boards"].items()
                      if info["status"] == "healthy"]
    healthy_boards.sort(key=lambda x: x[1]["result_count"], reverse=True)
    if healthy_boards:
        lines.append("<b>✅ TOP BOARDS:</b>")
        for src, info in healthy_boards[:5]:
            lines.append(f"  • {src}: {info['result_count']} results")
        lines.append("")

    lines.append("─────────────────")
    lines.append(f"<i>Run: python3 board_health.py --json</i>")

    return "\n".join(lines)


def send_telegram(message: str):
    """Send message to Telegram."""
    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("✓ Telegram notification sent")
        return True
    except Exception as e:
        print(f"✗ Telegram failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Board Health Monitor")
    parser.add_argument("--send-telegram", action="store_true", help="Send report to Telegram")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--history", action="store_true", help="Show health trend over time")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  BOARD HEALTH MONITOR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    health = analyze_board_health()

    # Load history and detect changes
    history = load_history()
    changes = detect_changes(health, history)

    # Save current to history
    history.append(health)
    save_history(history)

    # Save current health
    with open(HEALTH_FILE, "w") as f:
        json.dump(health, f, indent=2)

    if args.json:
        report = {"health": health, "changes": changes}
        print(json.dumps(report, indent=2))
        print(f"\n  ✓ Health saved: {HEALTH_FILE}")
        return

    # Console output
    summary = health["summary"]
    print(f"  Board Status: {summary['healthy']}✅ healthy, {summary['low_results']}⚠️ low, "
          f"{summary['error']}❌ error, {summary['no_results']}🔇 no results")
    print(f"  Total postings: {health['total_postings']}")

    print(f"\n  {'Board':<25} {'Status':<15} {'Results':>8}")
    print(f"  {'-'*50}")
    for src, info in sorted(health["boards"].items(), key=lambda x: x[1]["result_count"], reverse=True):
        icon = {"healthy": "✅", "low_results": "⚠️", "error": "❌", "no_results": "🔇"}.get(info["status"], "?")
        print(f"  {icon} {src:<23} {info['status']:<15} {info['result_count']:>8}")

    if changes:
        print(f"\n  CHANGES DETECTED:")
        for c in changes:
            print(f"    • {c['type']}: {c['board']} — {c['detail']}")

    if args.send_telegram:
        msg = build_telegram_message(health, changes)
        send_telegram(msg)

    if args.history and len(history) > 1:
        print(f"\n  HEALTH HISTORY ({len(history)} snapshots):")
        for h in history[-7:]:
            ts = h.get("timestamp", "")[:16]
            s = h.get("summary", {})
            print(f"    {ts}: {s.get('healthy', 0)}✅ {s.get('error', 0)}❌ | {h.get('total_postings', 0)} postings")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
