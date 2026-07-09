#!/usr/bin/env python3
"""
Weekly Trend Report — Week-over-week comparison of pipeline metrics.

Tracks trends for:
  • New postings, match rates, description coverage
  • Salary shifts (median, avg)
  • Application funnel progress
  • Board effectiveness changes
  • Top keyword performance

Usage:
    python3 weekly_digest.py              # Send weekly trend report
    python3 weekly_digest.py --days 7     # Custom lookback range
    python3 weekly_digest.py --no-telegram # Local only
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
INPUT_CSV = DATA_DIR / "job_postings.csv"
HISTORY_CSV = DATA_DIR / "job_postings_history.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_LOG = DATA_DIR / "apply_tracker.csv"
JOB_DESC_CSV = DATA_DIR / "job_descriptions.csv"
SNAPSHOTS_JSON = DATA_DIR / "weekly_snapshots.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def send_telegram(message: str):
    """Send message to Telegram."""
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
        print(f"  ✓ Telegram sent")
        return True
    except Exception as e:
        print(f"  ✗ Telegram failed: {e}")
        return False


def load_snapshots() -> dict:
    """Load historical weekly snapshots."""
    if not SNAPSHOTS_JSON.exists():
        return {}
    try:
        with open(SNAPSHOTS_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def save_snapshots(snapshots: dict):
    """Save weekly snapshots."""
    with open(SNAPSHOTS_JSON, "w") as f:
        json.dump(snapshots, f, indent=2, default=str)


def capture_current_snapshot() -> dict:
    """Capture current pipeline metrics as a snapshot."""
    postings = load_csv(INPUT_CSV)
    matched = load_csv(MATCHED_CSV)
    tracker = load_csv(APPLY_LOG)
    descriptions = load_csv(JOB_DESC_CSV)

    now = datetime.now()
    week_key = now.strftime("%Y-W%W")

    # Recent counts
    recent_7d = 0
    for r in postings:
        try:
            scraped = datetime.strptime(r.get("scraped_at", ""), "%Y-%m-%d %H:%M:%S")
            if (now - scraped).days <= 7:
                recent_7d += 1
        except (ValueError, TypeError):
            pass

    # Match rate
    match_rate = round(len(matched) / max(len(postings), 1) * 100, 1)

    # Description coverage
    desc_success = sum(1 for r in descriptions if r.get("status") == "success")
    desc_rate = round(len(descriptions) / max(len(matched), 1) * 100, 1)

    # Application statuses
    app_statuses = Counter(r.get("status", "unknown") for r in tracker)

    # Source breakdown
    source_counts = Counter(r.get("source", "unknown") for r in postings)

    # Salary stats from matched
    salaries = []
    import re
    for m in matched:
        raw = m.get("salary", "").strip()
        if not raw or raw.lower() in ("not specified", "n/a", "none"):
            continue
        cleaned = raw.replace("$", "").replace(",", "").replace("•", "").strip()
        range_match = re.search(r'([\d.]+)\s*k?\s*[-–]\s*([\d.]+)\s*k?', cleaned, re.IGNORECASE)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if 'k' in cleaned.lower():
                low *= 1000
                high *= 1000
            salaries.append((low + high) / 2)
        else:
            single_match = re.search(r'([\d.]+)\s*k?', cleaned, re.IGNORECASE)
            if single_match:
                val = float(single_match.group(1))
                if 'k' in cleaned.lower():
                    val *= 1000
                if val > 0:
                    salaries.append(val)

    salary_median = 0
    salary_avg = 0
    if salaries:
        salaries.sort()
        n = len(salaries)
        mid = n // 2
        salary_median = round(salaries[mid]) if n % 2 else round((salaries[mid - 1] + salaries[mid]) / 2)
        salary_avg = round(sum(salaries) / n)

    return {
        "week": week_key,
        "captured_at": now.isoformat(),
        "total_postings": len(postings),
        "total_matched": len(matched),
        "total_descriptions": len(descriptions),
        "desc_success": desc_success,
        "total_applications": len(tracker),
        "match_rate": match_rate,
        "desc_rate": desc_rate,
        "recent_7d": recent_7d,
        "app_statuses": dict(app_statuses),
        "top_sources": dict(source_counts.most_common(5)),
        "salary_median": salary_median,
        "salary_avg": salary_avg,
        "salary_count": len(salaries),
    }


def compute_trends(current: dict, previous: dict | None) -> dict:
    """Compute week-over-week trends."""
    if not previous:
        return {}

    trends = {}
    for key in ["total_postings", "total_matched", "total_descriptions",
                 "total_applications", "match_rate", "desc_rate",
                 "recent_7d", "salary_median", "salary_avg"]:
        curr_val = current.get(key, 0)
        prev_val = previous.get(key, 0)
        delta = curr_val - prev_val
        if prev_val != 0:
            pct = round(delta / prev_val * 100, 1)
        else:
            pct = 0 if delta == 0 else 100
        trends[key] = {"current": curr_val, "previous": prev_val, "delta": delta, "pct": pct}

    # Application status trends
    curr_apps = current.get("app_statuses", {})
    prev_apps = previous.get("app_statuses", {})
    app_trends = {}
    all_statuses = set(list(curr_apps.keys()) + list(prev_apps.keys()))
    for status in all_statuses:
        c = curr_apps.get(status, 0)
        p = prev_apps.get(status, 0)
        app_trends[status] = {"current": c, "previous": p, "delta": c - p}
    trends["app_status_changes"] = app_trends

    return trends


def format_trend_arrow(delta: float, pct: float, invert: bool = False) -> str:
    """Format a trend indicator."""
    if abs(delta) < 0.5:
        return "→"
    positive = delta > 0
    if invert:
        positive = not positive
    if positive:
        return f"↑{abs(pct)}%"
    else:
        return f"↓{abs(pct)}%"


def build_telegram_message(current: dict, trends: dict, days: int) -> str:
    """Build the weekly trend report Telegram message."""
    lines = []
    lines.append("📊 <b>WEEKLY TREND REPORT</b>")
    lines.append(f"📅 {current['captured_at'][:10]} | Week {current['week']}")
    lines.append(f"📆 Last {days} days")
    lines.append("")

    # Overview with trends
    lines.append("📈 <b>PIPELINE OVERVIEW</b>")
    t = trends.get("total_postings", {})
    if t:
        arrow = format_trend_arrow(t["delta"], t["pct"])
        lines.append(f"  • Postings: <b>{t['current']}</b> ({arrow})")
    else:
        lines.append(f"  • Postings: <b>{current['total_postings']}</b>")

    t = trends.get("total_matched", {})
    if t:
        arrow = format_trend_arrow(t["delta"], t["pct"])
        lines.append(f"  • Matched: <b>{t['current']}</b> ({arrow})")
    else:
        lines.append(f"  • Matched: <b>{current['total_matched']}</b>")

    t = trends.get("match_rate", {})
    if t:
        arrow = format_trend_arrow(t["delta"], t["pct"])
        lines.append(f"  • Match rate: <b>{t['current']}%</b> ({arrow})")
    else:
        lines.append(f"  • Match rate: <b>{current['match_rate']}%</b>")

    t = trends.get("recent_7d", {})
    if t:
        lines.append(f"  • New this week: <b>{t['current']}</b> (was {t['previous']})")
    else:
        lines.append(f"  • New this week: <b>{current['recent_7d']}</b>")
    lines.append("")

    # Application funnel trends
    lines.append("📋 <b>APPLICATION PROGRESS</b>")
    t = trends.get("total_applications", {})
    if t:
        arrow = format_trend_arrow(t["delta"], t["pct"])
        lines.append(f"  • Total: <b>{t['current']}</b> ({arrow})")
    else:
        lines.append(f"  • Total: <b>{current['total_applications']}</b>")

    app_trends = trends.get("app_status_changes", {})
    for status, info in app_trends.items():
        if info["delta"] != 0:
            icon = "🟢" if info["delta"] > 0 else "🔴"
            lines.append(f"  {icon} {status}: {info['current']} ({info['delta']:+d})")
    lines.append("")

    # Salary trends
    if current.get("salary_count", 0) > 0:
        lines.append("💰 <b>SALARY TRENDS</b>")
        t = trends.get("salary_median", {})
        if t and t["delta"] != 0:
            arrow = format_trend_arrow(t["delta"], t["pct"])
            lines.append(f"  • Median: <b>${t['current']:,}</b> ({arrow})")
        elif t:
            lines.append(f"  • Median: <b>${t['current']:,}</b>")

        t = trends.get("salary_avg", {})
        if t and t["delta"] != 0:
            arrow = format_trend_arrow(t["delta"], t["pct"])
            lines.append(f"  • Average: <b>${t['current']:,}</b> ({arrow})")
        elif t:
            lines.append(f"  • Average: <b>${t['current']:,}</b>")

        lines.append(f"  • Jobs with salary: {current['salary_count']}")
        lines.append("")

    # Top sources
    if current.get("top_sources"):
        lines.append("📡 <b>TOP SOURCES</b>")
        for src, count in list(current["top_sources"].items())[:5]:
            lines.append(f"  • {src}: {count} jobs")
        lines.append("")

    # Description coverage
    t = trends.get("desc_rate", {})
    if t:
        lines.append("📝 <b>DESCRIPTION COVERAGE</b>")
        arrow = format_trend_arrow(t["delta"], t["pct"])
        lines.append(f"  • Rate: <b>{t['current']}%</b> ({arrow})")
        lines.append(f"  • Success: {current['desc_success']}/{current['total_descriptions']}")
        lines.append("")

    # Motivation
    lines.append("─────────────────")
    if trends:
        # Count positive trends
        positive = sum(1 for k, v in trends.items()
                       if isinstance(v, dict) and v.get("delta", 0) > 0)
        if positive >= 3:
            lines.append("🚀 <b>Pipeline is growing! Keep it up!</b>")
        elif positive >= 1:
            lines.append("💪 <b>Good progress this week!</b>")
        else:
            lines.append("🎯 <b>Focus on scraping and applying this week!</b>")
    else:
        lines.append("📌 <i>First snapshot recorded. Trends will appear next week!</i>")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Weekly Trend Report")
    parser.add_argument("--days", type=int, default=7, help="Look back N days")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  WEEKLY TREND REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Load snapshots
    snapshots = load_snapshots()

    # Get previous snapshot (last week)
    previous = None
    if snapshots:
        sorted_weeks = sorted(snapshots.keys())
        if sorted_weeks:
            previous = snapshots[sorted_weeks[-1]]

    # Capture current snapshot
    current = capture_current_snapshot()
    print(f"  Current snapshot: {current['total_postings']} postings, "
          f"{current['total_matched']} matched, {current['total_applications']} applications")

    # Compute trends
    trends = compute_trends(current, previous)
    if trends:
        print(f"  Comparing with: {previous.get('week', 'unknown')}")
    else:
        print(f"  No previous snapshot — recording first baseline")

    # Save current snapshot
    snapshots[current["week"]] = current
    save_snapshots(snapshots)
    print(f"  ✓ Snapshot saved for {current['week']}")

    # Build and display message
    message = build_telegram_message(current, trends, args.days)
    print(f"\n{'─'*60}")
    print(message)
    print(f"{'─'*60}\n")

    # Send to Telegram
    if not args.no_telegram:
        send_telegram(message)

    print(f"  Done.")


if __name__ == "__main__":
    main()
