#!/usr/bin/env python3
"""
Daily Digest - Generates pipeline dashboard + sends Telegram summary.
Combines dashboard generation, pipeline stats, and Telegram notification.

Usage:
    python3 daily_digest.py
    python3 daily_digest.py --no-dashboard   # telegram only
    python3 daily_digest.py --no-telegram    # dashboard only
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
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
JOB_DESC_CSV = DATA_DIR / "job_descriptions.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def load_pipeline_health() -> dict | None:
    """Load pipeline health report if exists."""
    health_file = DATA_DIR / "pipeline_health.json"
    if not health_file.exists():
        return None
    try:
        with open(health_file) as f:
            return json.load(f)
    except Exception:
        return None


def load_skills_trends() -> dict | None:
    """Load skills trends snapshot if exists."""
    trends_file = DATA_DIR / "skills_trends.json"
    if not trends_file.exists():
        return None
    try:
        with open(trends_file) as f:
            return json.load(f)
    except Exception:
        return None


def load_pipeline_metrics() -> dict | None:
    """Load pipeline analytics metrics if exists."""
    metrics_file = DATA_DIR / "pipeline_metrics.json"
    if not metrics_file.exists():
        return None
    try:
        with open(metrics_file) as f:
            return json.load(f)
    except Exception:
        return None


def count_stuck_applications() -> dict:
    """Count applications stuck in applied/notified status >7 days."""
    tracker = load_csv(APPLY_TRACKER)
    cutoff = datetime.now() - timedelta(days=7)
    
    stuck_applied = 0
    stuck_notified = 0
    
    for entry in tracker:
        status = entry.get("status", "")
        updated_at = entry.get("updated_at", "")
        
        if status not in ("applied", "notified"):
            continue
        
        try:
            updated = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
            if updated < cutoff:
                if status == "applied":
                    stuck_applied += 1
                elif status == "notified":
                    stuck_notified += 1
        except (ValueError, TypeError):
            pass
    
    return {"stuck_applied": stuck_applied, "stuck_notified": stuck_notified}


def gather_digest_stats() -> dict:
    """Gather stats for the daily digest."""
    postings = load_csv(JOB_POSTINGS_CSV)
    matched = load_csv(MATCHED_CSV)
    tracker = load_csv(APPLY_TRACKER)
    descriptions = load_csv(JOB_DESC_CSV)

    now = datetime.now()

    # Recent postings (last 24h)
    recent_24h = 0
    for r in postings:
        try:
            scraped = datetime.strptime(r.get("scraped_at", ""), "%Y-%m-%d %H:%M:%S")
            if (now - scraped).days < 1:
                recent_24h += 1
        except (ValueError, TypeError):
            pass

    # Recent postings (last 7d)
    recent_7d = 0
    for r in postings:
        try:
            scraped = datetime.strptime(r.get("scraped_at", ""), "%Y-%m-%d %H:%M:%S")
            if (now - scraped).days <= 7:
                recent_7d += 1
        except (ValueError, TypeError):
            pass

    # Source breakdown
    source_counts = Counter(r.get("source", "unknown") for r in postings)

    # Top matched jobs
    top_jobs = sorted(matched, key=lambda x: float(x.get("score", x.get("_score", 0))), reverse=True)[:5]

    # Application statuses
    app_statuses = Counter(r.get("status", "unknown") for r in tracker)

    # Description coverage
    desc_success = sum(1 for r in descriptions if r.get("status") == "success")

    # Pipeline health
    health = load_pipeline_health()
    
    # Skills trends
    trends = load_skills_trends()
    
    # Pipeline metrics (analytics)
    pipeline_metrics = load_pipeline_metrics()
    
    # Stuck applications
    stuck = count_stuck_applications()

    return {
        "date": now.strftime("%Y-%m-%d"),
        "total_postings": len(postings),
        "total_matched": len(matched),
        "total_descriptions": len(descriptions),
        "desc_success": desc_success,
        "total_applications": len(tracker),
        "match_rate": round(len(matched) / max(len(postings), 1) * 100, 1),
        "desc_rate": round(len(descriptions) / max(len(matched), 1) * 100, 1),
        "recent_24h": recent_24h,
        "recent_7d": recent_7d,
        "sources": dict(source_counts.most_common(10)),
        "top_jobs": [
            {
                "title": j.get("title", "")[:50],
                "company": j.get("company", "")[:30],
                "score": j.get("score", j.get("_score", "0")),
                "location": j.get("location", "")[:30],
                "url": j.get("url", ""),
            }
            for j in top_jobs
        ],
        "app_statuses": dict(app_statuses),
        "health": health,
        "trends": trends,
        "stuck": stuck,
        "pipeline_metrics": pipeline_metrics,
    }


def generate_dashboard_html():
    """Generate the HTML dashboard by calling pipeline_dashboard module."""
    try:
        from pipeline_dashboard import generate_dashboard, OUTPUT_HTML
        generate_dashboard(OUTPUT_HTML)
        print(f"  ✓ Dashboard generated: {OUTPUT_HTML}")
        return str(OUTPUT_HTML)
    except Exception as e:
        print(f"  ✗ Dashboard generation failed: {e}")
        return None


def build_telegram_message(stats: dict) -> str:
    """Build Telegram digest message with enhanced pipeline summary."""
    lines = [
        f"📊 <b>DAILY PIPELINE DIGEST</b>",
        f"📅 {stats['date']}",
        "",
        f"🔢 <b>PIPELINE STATS</b>",
        f"  • Job postings: <b>{stats['total_postings']}</b> ({stats['recent_24h']} new today, {stats['recent_7d']} this week)",
        f"  • Matched jobs: <b>{stats['total_matched']}</b> ({stats['match_rate']}%)",
        f"  • Descriptions: <b>{stats['total_descriptions']}</b> ({stats['desc_success']} success, {stats['desc_rate']}% coverage)",
        f"  • Applications: <b>{stats['total_applications']}</b>",
        "",
    ]

    # Pipeline health status
    if stats.get("health"):
        health = stats["health"]
        lines.append("🏥 <b>PIPELINE HEALTH</b>")
        status = health.get("overall_status", "unknown")
        status_icon = "✅" if status == "healthy" else "⚠️" if status == "warning" else "❌"
        lines.append(f"  {status_icon} Status: <b>{status.upper()}</b>")
        
        steps = health.get("steps", {})
        ok_count = sum(1 for s in steps.values() if s.get("status") == "ok")
        total_steps = len(steps)
        lines.append(f"  • Steps running: {ok_count}/{total_steps}")
        
        warnings = health.get("warnings", [])
        if warnings:
            lines.append(f"  • Warnings: {len(warnings)}")
        lines.append("")

    # Follow-up alerts
    stuck = stats.get("stuck", {})
    stuck_applied = stuck.get("stuck_applied", 0)
    stuck_notified = stuck.get("stuck_notified", 0)
    if stuck_applied > 0 or stuck_notified > 0:
        lines.append("⏰ <b>FOLLOW-UP ALERTS</b>")
        if stuck_applied > 0:
            lines.append(f"  • <b>{stuck_applied}</b> applications stuck (applied >7 days, no response)")
        if stuck_notified > 0:
            lines.append(f"  • <b>{stuck_notified}</b> notifications stuck (notified >7 days, haven't applied)")
        lines.append(f"  💡 Run: <code>python3 followup_tracker.py --remind</code>")
        lines.append("")

    # Top 5 jobs
    if stats["top_jobs"]:
        lines.append("🏆 <b>TOP 5 MATCHED JOBS</b>")
        for i, j in enumerate(stats["top_jobs"], 1):
            lines.append(f"  {i}. <b>{j['title']}</b> (score: {j['score']})")
            lines.append(f"     🏢 {j['company']} | 📍 {j['location']}")
            if j["url"]:
                lines.append(f"     🔗 <a href=\"{j['url']}\">Apply</a>")
        lines.append("")

    # Application status
    if stats["app_statuses"]:
        lines.append("📋 <b>APPLICATION STATUS</b>")
        for status, count in stats["app_statuses"].items():
            lines.append(f"  • {status}: {count}")
        lines.append("")

    # Skills trends snapshot
    if stats.get("trends"):
        trends = stats["trends"]
        lines.append("🎯 <b>SKILLS TRENDS</b>")
        
        trending = trends.get("trending_skills", [])[:5]
        if trending:
            skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in trending]
            lines.append(f"  🔥 Trending: {', '.join(skill_names)}")
        
        missing = trends.get("missing_skills", [])[:5]
        if missing:
            skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in missing]
            lines.append(f"  ⚠️ Missing: {', '.join(skill_names)}")
        
        lines.append(f"  💡 Run: <code>python3 skills_gap_analyzer.py --json-output</code>")
        lines.append("")

    # Analytics insights (boards, keywords, salary)
    pm = stats.get("pipeline_metrics")
    if pm:
        lines.append("📊 <b>ANALYTICS INSIGHTS</b>")
        
        # Top boards
        boards = pm.get("board_effectiveness", [])[:3]
        if boards:
            board_names = [f"{b['source']} ({b['effectiveness']})" for b in boards]
            lines.append(f"  📡 Top boards: {', '.join(board_names)}")
        
        # Top keywords
        keywords = pm.get("keyword_performance", [])[:3]
        if keywords:
            kw_names = [f"{k['keyword']} ({k['effectiveness']})" for k in keywords]
            lines.append(f"  🔑 Top keywords: {', '.join(kw_names)}")
        
        # Salary snapshot
        salary = pm.get("salary_insights", {})
        if salary.get("available"):
            lines.append(f"  💰 Salary median: ${salary.get('median', 0):,} | avg: ${salary.get('avg', 0):,}")
        
        lines.append(f"  💡 Run: <code>python3 pipeline_analytics.py --html</code>")
        lines.append("")

    # Source breakdown
    lines.append("📡 <b>SOURCES</b>")
    for src, count in list(stats["sources"].items())[:5]:
        lines.append(f"  • {src}: {count} jobs")
    lines.append("")

    lines.append("💡 Run <code>python3 pipeline_dashboard.py --open</code> for full dashboard")

    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ✗ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

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
        print("  ✓ Telegram digest sent")
        return True
    except Exception as e:
        print(f"  ✗ Telegram send failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Daily Pipeline Digest")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard generation")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args()

    print(f"\n{'='*80}")
    print(f"  DAILY PIPELINE DIGEST - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}\n")

    # 1. Gather stats
    print("Gathering pipeline stats...")
    stats = gather_digest_stats()
    print(f"  ✓ {stats['total_postings']} postings, {stats['total_matched']} matched, {stats['total_descriptions']} descriptions")

    # 2. Generate dashboard
    if not args.no_dashboard:
        print("\nGenerating HTML dashboard...")
        generate_dashboard_html()

    # 3. Send Telegram
    if not args.no_telegram:
        print("\nSending Telegram digest...")
        message = build_telegram_message(stats)
        send_telegram(message)

    # 4. Save digest stats as JSON
    digest_json = DATA_DIR / "daily_digest.json"
    with open(digest_json, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  ✓ Digest stats saved: {digest_json}")

    print(f"\n{'='*80}")
    print(f"  DIGEST COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
