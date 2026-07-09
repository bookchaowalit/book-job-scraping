#!/usr/bin/env python3
"""
Weekly Pipeline Report — Sunday summary of all pipeline activity to Telegram.

Aggregates stats from all pipeline steps and sends a comprehensive
weekly digest covering: jobs scraped, matches, applications, follow-ups,
skills trends, salary benchmarks, and pipeline health.

Usage:
    python3 weekly_report.py                     # Generate + print report
    python3 weekly_report.py --send-telegram     # Send to Telegram
    python3 weekly_report.py --json              # Output as JSON
    python3 weekly_report.py --dry-run           # Preview without saving
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
WEEKLY_REPORT_JSON = DATA_DIR / "weekly_report.json"
WEEKLY_REPORT_LOG = DATA_DIR / "weekly_report_log.json"

# Pipeline data files
BOARDS_CSV = DATA_DIR / "boards.csv"
ALL_JOBS_CSV = DATA_DIR / "all_jobs.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER_CSV = DATA_DIR / "apply_tracker.csv"
TAILOR_LOG = DATA_DIR / "tailor_log.json"
DAILY_DIGEST_JSON = DATA_DIR / "daily_digest.json"
AUTO_APPLY_LOG = DATA_DIR / "auto_apply_log.json"
COMPANY_INTEL_CSV = DATA_DIR / "company_intel.csv"
DEEP_DESC_CSV = DATA_DIR / "job_descriptions_deep.csv"
SKILLS_GAP_CSV = DATA_DIR / "skills_gap.csv"
SALARY_CSV = DATA_DIR / "salary_benchmark.csv"
PIPELINE_HEALTH_JSON = DATA_DIR / "pipeline_health.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def count_csv_rows(filepath, min_rows=0):
    """Count rows in a CSV file."""
    if not filepath.exists():
        return 0
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = sum(1 for _ in reader)
            return max(rows, min_rows)
    except Exception:
        return 0


def count_recent_csv_rows(filepath, days=7):
    """Count rows added in last N days (by date field or file mtime)."""
    if not filepath.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    count = 0
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Try common date fields
                for field in ("scraped_at", "created_at", "matched_at", "date", "updated_at", "timestamp"):
                    date_str = row.get(field, "")
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            if dt.replace(tzinfo=None) >= cutoff:
                                count += 1
                                break
                        except ValueError:
                            continue
                else:
                    count += 1  # No date field found, count it
    except Exception:
        pass
    return count


def gather_weekly_stats():
    """Gather comprehensive weekly stats from all pipeline data."""
    stats = {}

    # ── Board Health ──
    stats["total_boards"] = count_csv_rows(BOARDS_CSV)
    healthy_boards = 0
    if BOARDS_CSV.exists():
        try:
            with open(BOARDS_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = row.get("status", "").lower()
                    if status in ("ok", "healthy", "active", ""):
                        healthy_boards += 1
        except Exception:
            pass
    stats["healthy_boards"] = healthy_boards

    # ── Jobs ──
    stats["total_jobs"] = count_csv_rows(ALL_JOBS_CSV)
    stats["jobs_this_week"] = count_recent_csv_rows(ALL_JOBS_CSV, days=7)

    # ── Matches ──
    stats["total_matched"] = count_csv_rows(MATCHED_CSV)
    stats["matched_this_week"] = count_recent_csv_rows(MATCHED_CSV, days=7)

    # High-score matches
    high_score_count = 0
    if MATCHED_CSV.exists():
        try:
            with open(MATCHED_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        score = float(row.get("score", 0))
                        if score >= 15:
                            high_score_count += 1
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
    stats["high_score_matches"] = high_score_count

    # ── Applications ──
    stats["total_applications"] = count_csv_rows(APPLY_TRACKER_CSV)
    app_statuses = {}
    if APPLY_TRACKER_CSV.exists():
        try:
            with open(APPLY_TRACKER_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = row.get("status", "unknown")
                    app_statuses[status] = app_statuses.get(status, 0) + 1
        except Exception:
            pass
    stats["application_statuses"] = app_statuses
    stats["auto_applied"] = app_statuses.get("auto_applied", 0)

    # ── Auto-Apply Log ──
    if AUTO_APPLY_LOG.exists():
        try:
            alog = json.loads(AUTO_APPLY_LOG.read_text())
            stats["auto_apply_runs"] = len(alog.get("runs", []))
            stats["auto_apply_total"] = len(alog.get("applied", []))
        except Exception:
            stats["auto_apply_runs"] = 0
            stats["auto_apply_total"] = 0

    # ── Tailored Resumes ──
    if TAILOR_LOG.exists():
        try:
            tlog = json.loads(TAILOR_LOG.read_text())
            stats["tailored_resumes"] = len(tlog.get("tailored", []))
        except Exception:
            stats["tailored_resumes"] = 0

    # ── Deep Scrapes ──
    stats["deep_scraped"] = count_csv_rows(DEEP_DESC_CSV)

    # ── Company Intel ──
    stats["companies_enriched"] = count_csv_rows(COMPANY_INTEL_CSV)

    # ── Skills Gap ──
    if SKILLS_GAP_CSV.exists():
        try:
            with open(SKILLS_GAP_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                gaps = list(reader)
                stats["skills_gaps"] = len(gaps)
                stats["top_gaps"] = [g.get("skill", "") for g in gaps[:5]]
        except Exception:
            stats["skills_gaps"] = 0
            stats["top_gaps"] = []

    # ── Salary Benchmark ──
    if SALARY_CSV.exists():
        try:
            with open(SALARY_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                benchmarks = list(reader)
                stats["salary_benchmarks"] = len(benchmarks)
        except Exception:
            stats["salary_benchmarks"] = 0

    # ── Pipeline Health ──
    if PIPELINE_HEALTH_JSON.exists():
        try:
            health = json.loads(PIPELINE_HEALTH_JSON.read_text())
            stats["last_pipeline_run"] = health.get("last_run", "unknown")
            stats["pipeline_status"] = health.get("status", "unknown")
        except Exception:
            stats["last_pipeline_run"] = "unknown"
            stats["pipeline_status"] = "unknown"

    # ── Follow-up ──
    stuck_count = 0
    if APPLY_TRACKER_CSV.exists():
        cutoff = datetime.now() - timedelta(days=7)
        try:
            with open(APPLY_TRACKER_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = row.get("status", "")
                    if status in ("applied", "notified"):
                        updated = row.get("updated_at", "")
                        if updated:
                            try:
                                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                                if dt.replace(tzinfo=None) < cutoff:
                                    stuck_count += 1
                            except ValueError:
                                stuck_count += 1
                        else:
                            stuck_count += 1
        except Exception:
            pass
    stats["stuck_applications"] = stuck_count

    stats["generated_at"] = datetime.now().isoformat()
    return stats


def build_telegram_message(stats):
    """Build comprehensive weekly report Telegram message."""
    week_num = datetime.now().isocalendar()[1]
    lines = [
        f"<b>📊 Weekly Pipeline Report — Week {week_num}</b>",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "<b>🔍 Scraping</b>",
        f"  Boards: {stats.get('healthy_boards', 0)}/{stats.get('total_boards', 0)} healthy",
        f"  Total Jobs: {stats.get('total_jobs', 0):,}",
        f"  New This Week: +{stats.get('jobs_this_week', 0):,}",
        "",
        "<b>🎯 Matching</b>",
        f"  Total Matched: {stats.get('total_matched', 0):,}",
        f"  New Matches: +{stats.get('matched_this_week', 0):,}",
        f"  High Score (15+): {stats.get('high_score_matches', 0)}",
        "",
        "<b>📝 Applications</b>",
        f"  Total: {stats.get('total_applications', 0)}",
        f"  Auto-Applied: {stats.get('auto_applied', 0)}",
        f"  Tailored Resumes: {stats.get('tailored_resumes', 0)}",
    ]

    # Application breakdown
    app_statuses = stats.get("application_statuses", {})
    if app_statuses:
        status_parts = []
        for s in ("notified", "applied", "auto_applied", "interviewing", "rejected", "withdrawn"):
            if s in app_statuses:
                status_parts.append(f"{s}: {app_statuses[s]}")
        if status_parts:
            lines.append(f"  Status: {' | '.join(status_parts)}")

    lines.extend([
        "",
        "<b>🔬 Enrichment</b>",
        f"  Deep JD Scrapes: {stats.get('deep_scraped', 0)}",
        f"  Companies Enriched: {stats.get('companies_enriched', 0)}",
        "",
        "<b>📈 Analytics</b>",
        f"  Skills Gaps: {stats.get('skills_gaps', 0)}",
        f"  Salary Benchmarks: {stats.get('salary_benchmarks', 0)}",
    ])

    top_gaps = stats.get("top_gaps", [])
    if top_gaps:
        lines.append(f"  Top Gaps: {', '.join(top_gaps[:5])}")

    lines.extend([
        "",
        "<b>⚠️ Alerts</b>",
        f"  Stuck Applications: {stats.get('stuck_applications', 0)}",
        f"  Pipeline Status: {stats.get('pipeline_status', 'unknown')}",
        f"  Last Run: {stats.get('last_pipeline_run', 'unknown')[:19]}",
    ])

    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3900] + "\n\n... (truncated)"
    return msg


def send_telegram(message):
    """Send message to Telegram."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print("[OK] Telegram notification sent")
        else:
            print(f"[WARN] Telegram returned {resp.status_code}")
    except Exception as e:
        print(f"[WARN] Telegram error: {e}")


def save_report(stats):
    """Save weekly report to JSON."""
    WEEKLY_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    WEEKLY_REPORT_JSON.write_text(json.dumps(stats, indent=2, default=str))
    print(f"[OK] Report saved to {WEEKLY_REPORT_JSON}")

    # Append to log
    log = []
    if WEEKLY_REPORT_LOG.exists():
        try:
            log = json.loads(WEEKLY_REPORT_LOG.read_text())
        except Exception:
            log = []
    log.append({
        "generated_at": stats.get("generated_at", ""),
        "total_jobs": stats.get("total_jobs", 0),
        "total_matched": stats.get("total_matched", 0),
        "total_applications": stats.get("total_applications", 0),
        "companies_enriched": stats.get("companies_enriched", 0),
    })
    # Keep last 52 weeks
    log = log[-52:]
    WEEKLY_REPORT_LOG.write_text(json.dumps(log, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Weekly Pipeline Report")
    parser.add_argument("--send-telegram", action="store_true", help="Send to Telegram")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    print("=" * 60)
    print("  Weekly Pipeline Report")
    print("=" * 60)

    stats = gather_weekly_stats()

    if args.json:
        print(json.dumps(stats, indent=2, default=str))
        return

    # Print summary
    print(f"\n  Boards: {stats.get('healthy_boards', 0)}/{stats.get('total_boards', 0)} healthy")
    print(f"  Total Jobs: {stats.get('total_jobs', 0):,}")
    print(f"  Jobs This Week: +{stats.get('jobs_this_week', 0):,}")
    print(f"  Total Matched: {stats.get('total_matched', 0):,}")
    print(f"  New Matches: +{stats.get('matched_this_week', 0):,}")
    print(f"  High Score: {stats.get('high_score_matches', 0)}")
    print(f"  Applications: {stats.get('total_applications', 0)}")
    print(f"  Auto-Applied: {stats.get('auto_applied', 0)}")
    print(f"  Tailored Resumes: {stats.get('tailored_resumes', 0)}")
    print(f"  Deep Scrapes: {stats.get('deep_scraped', 0)}")
    print(f"  Companies Enriched: {stats.get('companies_enriched', 0)}")
    print(f"  Skills Gaps: {stats.get('skills_gaps', 0)}")
    print(f"  Stuck Applications: {stats.get('stuck_applications', 0)}")

    if not args.dry_run:
        save_report(stats)

    if args.send_telegram:
        msg = build_telegram_message(stats)
        send_telegram(msg)

    print("\n[DONE] Weekly report complete")


if __name__ == "__main__":
    main()
