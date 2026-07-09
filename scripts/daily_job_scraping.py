#!/usr/bin/env python3
"""
Daily Job Scraping Automation
Runs all scrapers, matchers, and analysis tools.
Produces a summary report with actionable insights.

Usage:
    python3 daily_job_scraping.py              # Full pipeline
    python3 daily_job_scraping.py --quick       # Scrape + match only
    python3 daily_job_scraping.py --analysis     # Analysis tools only
    python3 daily_job_scraping.py --followup     # Include follow-up check
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "domains" / "book-dev" / "book-scraping" / "data"

def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=PROJECT_ROOT,
        capture_output=False,
        text=True
    )
    
    if result.returncode != 0:
        print(f"  ❌ {description} failed with exit code {result.returncode}")
        return False
    return True

def count_csv_rows(filepath):
    """Count rows in a CSV file."""
    if not filepath.exists():
        return 0
    with open(filepath, 'r') as f:
        return sum(1 for _ in f) - 1  # Subtract header

def generate_summary():
    """Generate a summary report of today's scraping results."""
    print(f"\n{'='*60}")
    print(f"  📊 DAILY SUMMARY - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # Count jobs
    job_postings = count_csv_rows(DATA_DIR / "job_postings.csv")
    matched_jobs = count_csv_rows(DATA_DIR / "matched_jobs.csv")
    pipeline_leads = count_csv_rows(DATA_DIR / "pipeline.csv")
    apply_tracker = count_csv_rows(DATA_DIR / "apply_tracker.csv")
    descriptions = count_csv_rows(DATA_DIR / "job_descriptions.csv")
    
    print(f"  📋 Remote Job Postings: {job_postings:,}")
    print(f"  🎯 Matched Jobs: {matched_jobs:,}")
    print(f"  💼 Freelance Pipeline: {pipeline_leads:,}")
    print(f"  📝 Applications Tracked: {apply_tracker:,}")
    print(f"  📄 Job Descriptions: {descriptions:,}")
    
    # Read matched jobs breakdown
    matched_file = DATA_DIR / "matched_jobs.csv"
    hot = strong = match = 0
    if matched_file.exists():
        with open(matched_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                score = int(row.get("score", 0))
                if score >= 80:
                    hot += 1
                elif score >= 60:
                    strong += 1
                elif score >= 40:
                    match += 1
        
        print(f"\n  🔥 Hot Leads (80+): {hot}")
        print(f"  ⭐ Strong Matches (60-79): {strong}")
        print(f"  ✓ Good Matches (40-59): {match}")
    
    # Apply tracker breakdown
    tracker_file = DATA_DIR / "apply_tracker.csv"
    if tracker_file.exists():
        status_counts = {}
        with open(tracker_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
        if status_counts:
            print(f"\n  📊 Application Status:")
            for status, count in sorted(status_counts.items()):
                print(f"     {status}: {count}")
    
    print(f"\n{'='*60}")
    print(f"  ✅ Daily scraping complete!")
    print(f"{'='*60}\n")
    
    # Save summary to file
    summary_file = PROJECT_ROOT / "data" / "briefings" / f"daily-jobs-{datetime.now().strftime('%Y-%m-%d')}.log"
    with open(summary_file, 'w') as f:
        f.write(f"Daily Job Scraping Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"Remote Job Postings: {job_postings:,}\n")
        f.write(f"Matched Jobs: {matched_jobs:,}\n")
        f.write(f"Freelance Pipeline: {pipeline_leads:,}\n")
        f.write(f"Applications Tracked: {apply_tracker:,}\n")
        f.write(f"Job Descriptions: {descriptions:,}\n\n")
        if matched_file.exists():
            f.write(f"Hot Leads (80+): {hot}\n")
            f.write(f"Strong Matches (60-79): {strong}\n")
            f.write(f"Good Matches (40-59): {match}\n")
        if status_counts:
            f.write(f"\nApplication Status:\n")
            for status, count in sorted(status_counts.items()):
                f.write(f"  {status}: {count}\n")
    
    print(f"  📄 Summary saved to: {summary_file}\n")

def main():
    parser = argparse.ArgumentParser(description="Daily Job Scraping Automation")
    parser.add_argument("--quick", action="store_true", help="Scrape + match only")
    parser.add_argument("--analysis", action="store_true", help="Analysis tools only")
    parser.add_argument("--followup", action="store_true", help="Include follow-up check")
    parser.add_argument("--scrape-desc", action="store_true", help="Scrape job descriptions")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  🚀 DAILY JOB SCRAPING AUTOMATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Analysis-only mode
    if args.analysis:
        run_command(
            f"python3 {SCRIPTS_DIR}/skills_gap_analyzer.py --top 10",
            "🔍 Running Skills Gap Analyzer"
        )
        run_command(
            f"python3 {SCRIPTS_DIR}/salary_benchmark.py",
            "💰 Running Salary Benchmark"
        )
        run_command(
            f"python3 {SCRIPTS_DIR}/followup_tracker.py --days 7",
            "📬 Checking Application Follow-ups"
        )
        return
    
    # Step 1: Remote job postings (6 sources)
    success1 = run_command(
        f"python3 {SCRIPTS_DIR}/scrape_job_postings.py --boards 'remoteok-api,himalayas,landing-jobs,jobicy,hn-hiring,remotive'",
        "📡 Scraping Remote Job Postings (6 sources)"
    )
    
    # Step 2: Freelance jobs (3 platforms)
    success2 = run_command(
        f"python3 {SCRIPTS_DIR}/scrape_freelance_jobs.py --platform both",
        "💼 Scraping Freelance Platforms (Upwork + Fastwork)"
    )
    
    # Step 3: Job matching
    success3 = run_command(
        f"python3 {SCRIPTS_DIR}/filter_job_matches.py",
        "🎯 Running Job Matcher"
    )
    
    if args.quick:
        generate_summary()
        return
    
    # Step 4: Scrape job descriptions for top matches
    if args.scrape_desc:
        run_command(
            f"python3 {SCRIPTS_DIR}/scrape_job_descriptions.py --top 5",
            "📄 Scraping Job Descriptions (top 5)"
        )
    
    # Step 5: Follow-up check
    if args.followup:
        run_command(
            f"python3 {SCRIPTS_DIR}/followup_tracker.py --days 7",
            "📬 Checking Application Follow-ups"
        )
    
    # Step 6: Generate summary
    generate_summary()

if __name__ == "__main__":
    main()
