#!/usr/bin/env python3
"""
Unified Job Pipeline Runner — single command to run the full pipeline.

Usage:
    python3 scripts/pipeline_runner.py              # Core pipeline (scrape+match+notify)
    python3 scripts/pipeline_runner.py --skip-scrape # Skip scraping (use existing data)
    python3 scripts/pipeline_runner.py --quick       # Quick run: match + promote + notify
    python3 scripts/pipeline_runner.py --full        # Full + analysis + enrichment
    python3 scripts/pipeline_runner.py --dry-run     # Show what would run, don't execute
    python3 scripts/pipeline_runner.py --health      # Health check
    python3 scripts/pipeline_runner.py --steps deep_scrape_jd,company_intel  # Specific steps

Pipeline Groups:
    scrape   - Job board scraping, dedup, health check
    match    - Job matching & scoring
    describe - JD scraping (basic + deep Firecrawl)
    promote  - Auto-promote, tailor resumes, auto-apply
    notify   - Telegram notifications
    digest   - Daily digest, portfolio sync, weekly report
    analysis - Keyword rotation, backup, follow-up, skills, salary
    enrich   - Company intelligence, freelance proposals
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "domains" / "book-dev" / "book-scraping" / "scripts"
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
LOG_DIR = DATA_DIR

# Pipeline steps in order
PIPELINE_STEPS = [
    {
        "name": "scrape_postings",
        "label": "Scrape Job Postings",
        "cmd": [sys.executable, str(SCRIPTS / "scrape_job_postings.py")],
        "group": "scrape",
    },
    {
        "name": "dedup_jobs",
        "label": "Deduplicate Jobs",
        "cmd": [sys.executable, str(SCRIPTS / "job_dedup.py"), "--clean", "--matched"],
        "group": "scrape",
    },
    {
        "name": "board_health",
        "label": "Board Health Check",
        "cmd": [sys.executable, str(SCRIPTS / "board_health.py"), "--send-telegram"],
        "group": "scrape",
    },
    {
        "name": "match_jobs",
        "label": "Match & Score Jobs",
        "cmd": [sys.executable, str(SCRIPTS / "match_jobs.py"), "--top", "50", "--min-score", "2"],
        "group": "match",
    },
    {
        "name": "scrape_descriptions",
        "label": "Scrape Job Descriptions",
        "cmd": [sys.executable, str(SCRIPTS / "scrape_job_descriptions.py"), "--top", "10"],
        "group": "describe",
    },
    {
        "name": "deep_scrape_jd",
        "label": "Deep JD Scrape (Firecrawl)",
        "cmd": [sys.executable, str(SCRIPTS / "deep_scrape_jd.py"), "--top", "20", "--min-score", "8"],
        "group": "describe",
    },
    {
        "name": "re_match",
        "label": "Re-Match with Descriptions",
        "cmd": [sys.executable, str(SCRIPTS / "match_jobs.py"), "--top", "50", "--min-score", "2"],
        "group": "describe",
    },
    {
        "name": "auto_promote",
        "label": "Auto-Promote to Tracker",
        "cmd": [sys.executable, str(SCRIPTS / "auto_promote_jobs.py"), "--backfill", "--min-score", "15", "--top", "20"],
        "group": "promote",
    },
    {
        "name": "job_notify",
        "label": "Telegram Job Notifications",
        "cmd": [sys.executable, str(SCRIPTS / "job_notify.py"), "--top", "10", "--min-score", "8"],
        "group": "notify",
    },
    {
        "name": "auto_tailor",
        "label": "Auto-Tailor Resumes (Score 40+)",
        "cmd": [sys.executable, str(SCRIPTS / "auto_tailor.py"), "--min-score", "40", "--limit", "3"],
        "group": "promote",
    },
    {
        "name": "auto_apply",
        "label": "Auto-Apply (Score 80+)",
        "cmd": [sys.executable, str(SCRIPTS / "auto_apply.py"), "--min-score", "80", "--limit", "3", "--send-telegram"],
        "group": "promote",
    },
    {
        "name": "daily_digest",
        "label": "Daily Digest (Dashboard + Telegram)",
        "cmd": [sys.executable, str(SCRIPTS / "daily_digest.py")],
        "group": "digest",
    },
    {
        "name": "keyword_rotation",
        "label": "Smart Keyword Rotation",
        "cmd": [sys.executable, str(SCRIPTS / "keyword_rotation.py")],
        "group": "analysis",
    },
    {
        "name": "pipeline_backup",
        "label": "Pipeline Backup & Rotation",
        "cmd": [sys.executable, str(SCRIPTS / "pipeline_backup.py")],
        "group": "analysis",
    },
    {
        "name": "followup",
        "label": "Follow-up Tracker",
        "cmd": [sys.executable, str(SCRIPTS / "followup_tracker.py"), "--days", "7", "--send-telegram", "--generate-emails"],
        "group": "analysis",
    },
    {
        "name": "skills_gap",
        "label": "Skills Gap Analysis",
        "cmd": [sys.executable, str(SCRIPTS / "skills_gap_analyzer.py"), "--top", "15", "--send-telegram"],
        "group": "analysis",
    },
    {
        "name": "salary_benchmark",
        "label": "Salary Benchmarking",
        "cmd": [sys.executable, str(SCRIPTS / "salary_benchmark.py"), "--send-telegram"],
        "group": "analysis",
    },
    {
        "name": "company_intel",
        "label": "Company Intelligence",
        "cmd": [sys.executable, str(SCRIPTS / "company_intel.py"), "--top", "15", "--min-score", "8"],
        "group": "enrich",
    },
    {
        "name": "portfolio_sync",
        "label": "Portfolio Data Sync",
        "cmd": [sys.executable, str(SCRIPTS / "portfolio_sync.py")],
        "group": "digest",
    },
    {
        "name": "weekly_report",
        "label": "Weekly Report to Telegram",
        "cmd": [sys.executable, str(SCRIPTS / "weekly_report.py"), "--send-telegram"],
        "group": "digest",
    },
    {
        "name": "freelance_proposal",
        "label": "Freelance Auto-Proposal",
        "cmd": [sys.executable, str(SCRIPTS / "freelance_proposal.py"), "--top", "5"],
        "group": "enrich",
    },
    {
        "name": "scam_detection",
        "label": "Job Scam Detection",
        "cmd": [sys.executable, str(SCRIPTS / "job_scam_detector.py"), "--top", "20"],
        "group": "analysis",
    },
    {
        "name": "daily_job_digest",
        "label": "Daily Job Digest",
        "cmd": [sys.executable, str(SCRIPTS / "daily_job_digest.py")],
        "group": "digest",
    },
    {
        "name": "skills_gap_v2",
        "label": "Skills Gap Analysis v2",
        "cmd": [sys.executable, str(SCRIPTS / "skills_gap_analyzer.py"), "--top", "15"],
        "group": "analysis",
    },
    {
        "name": "auto_seed_tracker",
        "label": "Auto-Seed Application Tracker",
        "cmd": [sys.executable, str(SCRIPTS / "auto_seed_tracker.py"), "--min-score", "8"],
        "group": "promote",
    },
    {
        "name": "resume_select",
        "label": "Multi-Resume Auto-Select",
        "cmd": [sys.executable, str(SCRIPTS / "multi_resume_manager.py"), "--list"],
        "group": "promote",
    },
    {
        "name": "pipeline_health",
        "label": "Pipeline Health Monitor",
        "cmd": [sys.executable, str(SCRIPTS / "pipeline_health_monitor.py")],
        "group": "analysis",
    },
]


def run_step(step: dict, dry_run: bool = False) -> tuple:
    """Run a single pipeline step. Returns (success, duration_seconds)."""
    name = step["name"]
    label = step["label"]
    cmd = step["cmd"]

    if dry_run:
        print(f"  [DRY] {label}")
        print(f"        {' '.join(cmd)}")
        return True, 0

    print(f"  ▶ {label}...", end=" ", flush=True)
    start = time.time()

    log_file = LOG_DIR / f"pipeline_{name}.log"
    try:
        with open(log_file, "w") as log:
            log.write(f"# Pipeline run: {datetime.now().isoformat()}\n")
            log.write(f"# Command: {' '.join(cmd)}\n\n")
            result = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,  # 5 min timeout per step
                cwd=str(ROOT),
            )
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"✓ ({elapsed:.1f}s)")
            return True, elapsed
        else:
            print(f"✗ (exit {result.returncode}, {elapsed:.1f}s) — see {log_file}")
            return False, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"✗ (timeout after 300s) — see {log_file}")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ ({e})")
        return False, elapsed


def get_log_age(name: str) -> float | None:
    """Return hours since last log, or None if no log exists."""
    log_file = LOG_DIR / f"pipeline_{name}.log"
    if not log_file.exists():
        return None
    mtime = log_file.stat().st_mtime
    return (time.time() - mtime) / 3600


def check_last_run_status(name: str) -> str:
    """Check if last run of a step succeeded. Returns 'ok', 'failed', 'unknown', 'missing'."""
    log_file = LOG_DIR / f"pipeline_{name}.log"
    if not log_file.exists():
        return "missing"
    try:
        lines = log_file.read_text().splitlines()
        # Check for actual Python crashes in last 20 lines (not data containing 'error')
        tail = lines[-20:] if len(lines) > 20 else lines
        for line in reversed(tail):
            low = line.lower()
            # Only flag actual crashes, not data values containing 'error'
            if "traceback" in low:
                return "failed"
            if any(exc in line for exc in ("ValueError:", "KeyError:", "TypeError:",
                                            "ImportError:", "NameError:", "SyntaxError:",
                                            "FileNotFoundError:", "PermissionError:")):
                return "failed"
        return "ok"
    except Exception:
        return "unknown"


def get_data_freshness() -> dict:
    """Check freshness of key data files."""
    files = {
        "job_postings.csv": DATA_DIR / "job_postings.csv",
        "matched_jobs.csv": DATA_DIR / "matched_jobs.csv",
        "apply_tracker.csv": DATA_DIR / "apply_tracker.csv",
        "job_descriptions.csv": DATA_DIR / "job_descriptions.csv",
    }
    freshness = {}
    for name, path in files.items():
        if path.exists():
            mtime = path.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            freshness[name] = {
                "age_hours": round(age_hours, 1),
                "size_bytes": path.stat().st_size,
                "stale": age_hours > 48,
            }
        else:
            freshness[name] = {"age_hours": None, "size_bytes": 0, "stale": True}
    return freshness


def run_health_check(auto_recover: bool = False):
    """Run pipeline health check and optionally auto-recover failed steps."""
    print(f"\n{'='*60}")
    print(f"  PIPELINE HEALTH CHECK")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    issues = []
    warnings = []

    # 1. Check each step's last run
    print("  Step Status:")
    for step in PIPELINE_STEPS:
        name = step["name"]
        label = step["label"]
        age = get_log_age(name)
        status = check_last_run_status(name)

        if age is None:
            icon = "⚪"
            detail = "never run"
            warnings.append(f"{label}: never run")
        elif status == "failed":
            icon = "🔴"
            detail = f"FAILED ({age:.1f}h ago)"
            issues.append(name)
        elif age > 48:
            icon = "🟡"
            detail = f"stale ({age:.1f}h ago)"
            warnings.append(f"{label}: stale ({age:.1f}h ago)")
        else:
            icon = "🟢"
            detail = f"ok ({age:.1f}h ago)"

        print(f"    {icon} {label:40s} {detail}")

    # 2. Data freshness
    print(f"\n  Data Freshness:")
    freshness = get_data_freshness()
    for name, info in freshness.items():
        if info["age_hours"] is None:
            icon = "⚪"
            detail = "missing"
            issues.append(f"data_{name}")
        elif info["stale"]:
            icon = "🟡"
            detail = f"stale ({info['age_hours']:.1f}h old)"
            warnings.append(f"{name}: stale")
        else:
            icon = "🟢"
            detail = f"fresh ({info['age_hours']:.1f}h old, {info['size_bytes']:,} bytes)"
        print(f"    {icon} {name:30s} {detail}")

    # 3. Summary
    print(f"\n  Summary:")
    if not issues and not warnings:
        print(f"    ✅ All systems healthy!")
    else:
        if issues:
            print(f"    🔴 {len(issues)} issue(s): {', '.join(issues)}")
        if warnings:
            print(f"    🟡 {len(warnings)} warning(s): {', '.join(warnings)}")

    # 4. Auto-recover
    if auto_recover and issues:
        failed_steps = [s for s in PIPELINE_STEPS if s["name"] in issues and not s["name"].startswith("data_")]
        if failed_steps:
            print(f"\n  Auto-Recovering {len(failed_steps)} failed step(s):")
            for step in failed_steps:
                print(f"\n  ▶ Re-running: {step['label']}")
                success, elapsed = run_step(step)
                if success:
                    print(f"    ✓ Recovered ({elapsed:.1f}s)")
                else:
                    print(f"    ✗ Still failing — check logs")

    # 5. Save health report
    health = {
        "timestamp": datetime.now().isoformat(),
        "issues": issues,
        "warnings": warnings,
        "freshness": freshness,
        "healthy": len(issues) == 0 and len(warnings) == 0,
    }
    health_file = DATA_DIR / "pipeline_health.json"
    with open(health_file, "w") as f:
        json.dump(health, f, indent=2)
    print(f"\n  Health report saved: {health_file}")
    print(f"{'='*60}\n")

    return len(issues) == 0


def main():
    parser = argparse.ArgumentParser(description="Unified Job Pipeline Runner")
    parser.add_argument("--quick", action="store_true", help="Quick run: match + promote + notify only")
    parser.add_argument("--full", action="store_true", help="Full pipeline + analysis (skills gap, salary)")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping steps")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--steps", default="", help="Comma-separated step names to run (e.g. 'match_jobs,auto_promote')")
    parser.add_argument("--health", action="store_true", help="Run health check instead of pipeline")
    parser.add_argument("--auto-recover", action="store_true", help="With --health, auto-rerun failed steps")
    args = parser.parse_args()

    # Health check mode
    if args.health:
        ok = run_health_check(auto_recover=args.auto_recover)
        sys.exit(0 if ok else 1)

    # Determine which groups to run
    if args.steps:
        selected = set(args.steps.split(","))
        steps = [s for s in PIPELINE_STEPS if s["name"] in selected]
    elif args.quick:
        steps = [s for s in PIPELINE_STEPS if s["group"] in ("match", "promote", "notify")]
    elif args.full:
        steps = PIPELINE_STEPS[:]
    else:
        # Default: everything except analysis and enrich
        steps = [s for s in PIPELINE_STEPS if s["group"] not in ("analysis", "enrich")]

    if args.skip_scrape:
        steps = [s for s in steps if s["group"] != "scrape"]

    # Banner
    print(f"\n{'='*60}")
    print(f"  JOB PIPELINE RUNNER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print(f"  [DRY RUN MODE]")
    print(f"{'='*60}")
    print(f"\n  Steps to execute ({len(steps)}):")
    for s in steps:
        print(f"    • {s['label']}")
    print()

    if args.dry_run:
        print("  Commands:")
        for s in steps:
            run_step(s, dry_run=True)
        return

    # Execute
    results = []
    total_start = time.time()
    for step in steps:
        success, elapsed = run_step(step)
        results.append((step["label"], success, elapsed))

    total_elapsed = time.time() - total_start

    # Summary
    print(f"\n{'='*60}")
    print(f"  PIPELINE SUMMARY")
    print(f"{'='*60}")
    ok = sum(1 for _, s, _ in results if s)
    fail = sum(1 for _, s, _ in results if not s)
    for label, success, elapsed in results:
        status = "✓" if success else "✗"
        print(f"  {status} {label} ({elapsed:.1f}s)")
    print(f"\n  Total: {ok} passed, {fail} failed, {total_elapsed:.1f}s")
    print(f"  Logs: {LOG_DIR}/pipeline_*.log")
    print(f"{'='*60}\n")

    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
