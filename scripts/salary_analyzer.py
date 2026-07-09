#!/usr/bin/env python3
"""
Salary Market Rate Analyzer
Analyzes matched jobs by salary ranges, location, and tech stack to determine market value.
Generates HTML chart with visualizations.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REPORTS_DIR = DATA_DIR / "salary_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_matched_jobs():
    """Load matched jobs with salary data."""
    jobs = []
    csv_path = DATA_DIR / "matched_jobs.csv"
    if not csv_path.exists():
        return jobs
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jobs.append(row)
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    return jobs


def load_job_postings():
    """Load all job postings."""
    jobs = []
    csv_path = DATA_DIR / "job_postings.csv"
    if not csv_path.exists():
        return jobs
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jobs.append(row)
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    return jobs


def parse_salary(salary_str):
    """Parse salary string into numeric range."""
    if not salary_str:
        return None, None

    salary_str = str(salary_str).strip().lower()
    salary_str = salary_str.replace(",", "").replace("฿", "").replace("$", "").replace("฿", "")

    # Pattern: "100k-150k" or "100000-150000"
    range_match = re.search(r'(\d+)[kK]?\s*[-–]\s*(\d+)[kK]?', salary_str)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        if "k" in salary_str:
            low *= 1000
            high *= 1000
        return low, high

    # Single value: "100k" or "100000"
    single_match = re.search(r'(\d+)[kK]', salary_str)
    if single_match:
        val = int(single_match.group(1)) * 1000
        return val, val

    # Min/max fields
    min_match = re.search(r'(\d+)', salary_str)
    if min_match:
        val = int(min_match.group(1))
        if val < 1000:
            val *= 1000
        return val, val

    return None, None


def analyze_salaries(jobs):
    """Comprehensive salary analysis."""
    results = {
        "total_jobs": len(jobs),
        "with_salary": 0,
        "salary_ranges": [],
        "by_location": defaultdict(list),
        "by_tech": defaultdict(list),
        "by_experience": defaultdict(list),
        "by_category": defaultdict(list),
        "overall_min": float("inf"),
        "overall_max": 0,
        "overall_avg_low": 0,
        "overall_avg_high": 0,
    }

    all_lows = []
    all_highs = []

    for job in jobs:
        salary_raw = job.get("salary_min", "") or job.get("salary", "") or job.get("salary_range", "")
        low, high = parse_salary(salary_raw)

        if low is None:
            continue

        results["with_salary"] += 1
        results["salary_ranges"].append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "low": low,
            "high": high,
            "tech": job.get("matched_keywords", job.get("tech_stack", "")),
        })

        all_lows.append(low)
        all_highs.append(high)

        # By location
        loc = job.get("location", "Unknown")
        loc_key = "Remote" if "remote" in loc.lower() else loc.split(",")[-1].strip() if "," in loc else loc
        results["by_location"][loc_key].append((low, high))

        # By tech stack
        tech = job.get("matched_keywords", job.get("tech_stack", ""))
        if tech:
            for t in re.split(r'[,;|]+', tech):
                t = t.strip().lower()
                if t and len(t) > 2:
                    results["by_tech"][t].append((low, high))

        # By experience level
        title = job.get("title", "").lower()
        if "senior" in title or "sr" in title:
            results["by_experience"]["Senior"].append((low, high))
        elif "junior" in title or "jr" in title:
            results["by_experience"]["Junior"].append((low, high))
        elif "lead" in title or "principal" in title or "staff" in title:
            results["by_experience"]["Lead/Staff"].append((low, high))
        elif "mid" in title:
            results["by_experience"]["Mid-level"].append((low, high))
        else:
            results["by_experience"]["Not specified"].append((low, high))

    if all_lows:
        results["overall_min"] = min(all_lows)
        results["overall_max"] = max(all_highs)
        results["overall_avg_low"] = sum(all_lows) / len(all_lows)
        results["overall_avg_high"] = sum(all_highs) / len(all_highs)
        results["median_low"] = sorted(all_lows)[len(all_lows) // 2]
        results["median_high"] = sorted(all_highs)[len(all_highs) // 2]

    return results


def format_salary(amount, currency="USD"):
    """Format salary amount."""
    if amount >= 1000:
        return f"${amount / 1000:.0f}K"
    return f"${amount:.0f}"


def generate_html_report(results):
    """Generate interactive HTML report with charts."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Prepare chart data
    location_data = []
    for loc, salaries in sorted(results["by_location"].items(), key=lambda x: -len(x[1]))[:15]:
        avg_low = sum(s[0] for s in salaries) / len(salaries)
        avg_high = sum(s[1] for s in salaries) / len(salaries)
        location_data.append({
            "location": loc,
            "avg_low": round(avg_low),
            "avg_high": round(avg_high),
            "count": len(salaries),
        })

    tech_data = []
    for tech, salaries in sorted(results["by_tech"].items(), key=lambda x: -len(x[1]))[:20]:
        if len(salaries) >= 2:
            avg_low = sum(s[0] for s in salaries) / len(salaries)
            avg_high = sum(s[1] for s in salaries) / len(salaries)
            tech_data.append({
                "tech": tech,
                "avg_low": round(avg_low),
                "avg_high": round(avg_high),
                "count": len(salaries),
            })

    exp_data = []
    for level, salaries in results["by_experience"].items():
        if salaries:
            avg_low = sum(s[0] for s in salaries) / len(salaries)
            avg_high = sum(s[1] for s in salaries) / len(salaries)
            exp_data.append({
                "level": level,
                "avg_low": round(avg_low),
                "avg_high": round(avg_high),
                "count": len(salaries),
            })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Salary Market Analysis — {timestamp}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin-bottom: 8px; color: #38bdf8; }}
h2 {{ font-size: 20px; margin: 30px 0 15px; color: #818cf8; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
.subtitle {{ color: #94a3b8; margin-bottom: 30px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
.stat-card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
.stat-value {{ font-size: 28px; font-weight: 700; color: #38bdf8; }}
.stat-label {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
.chart-container {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #334155; }}
.bar-row {{ display: flex; align-items: center; margin: 8px 0; }}
.bar-label {{ width: 150px; font-size: 13px; color: #cbd5e1; flex-shrink: 0; }}
.bar-track {{ flex: 1; height: 24px; background: #0f172a; border-radius: 6px; position: relative; overflow: hidden; }}
.bar-fill {{ height: 100%; border-radius: 6px; background: linear-gradient(90deg, #3b82f6, #8b5cf6); display: flex; align-items: center; padding-left: 8px; font-size: 11px; color: white; min-width: 60px; }}
.bar-count {{ position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 11px; color: #64748b; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #1e293b; font-size: 13px; }}
th {{ color: #94a3b8; font-weight: 600; background: #1e293b; }}
td {{ color: #cbd5e1; }}
tr:hover td {{ background: #1e293b44; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-high {{ background: #065f46; color: #6ee7b7; }}
.badge-mid {{ background: #78350f; color: #fbbf24; }}
.badge-low {{ background: #7f1d1d; color: #fca5a5; }}
</style>
</head>
<body>
<div class="container">
<h1>💰 Salary Market Analysis</h1>
<p class="subtitle">Generated {timestamp} | Based on {results['total_jobs']} jobs ({results['with_salary']} with salary data)</p>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value">{format_salary(results['overall_avg_low'])} — {format_salary(results['overall_avg_high'])}</div>
    <div class="stat-label">Average Salary Range</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{format_salary(results.get('median_low', 0))} — {format_salary(results.get('median_high', 0))}</div>
    <div class="stat-label">Median Salary Range</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{format_salary(results['overall_min'])} — {format_salary(results['overall_max'])}</div>
    <div class="stat-label">Full Range</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{results['with_salary']}</div>
    <div class="stat-label">Jobs with Salary Data</div>
  </div>
</div>

<h2>📍 Salary by Location</h2>
<div class="chart-container">
"""

    max_salary = max((d["avg_high"] for d in location_data), default=1)
    for d in location_data:
        width_pct = (d["avg_high"] / max_salary * 100) if max_salary else 0
        html += f"""<div class="bar-row">
  <div class="bar-label">{d['location']}</div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{width_pct:.0f}%">{format_salary(d['avg_low'])} — {format_salary(d['avg_high'])}</div>
    <span class="bar-count">n={d['count']}</span>
  </div>
</div>"""

    html += """</div>

<h2>🛠️ Salary by Tech Stack</h2>
<div class="chart-container">
"""

    max_tech = max((d["avg_high"] for d in tech_data), default=1)
    for d in tech_data:
        width_pct = (d["avg_high"] / max_tech * 100) if max_tech else 0
        html += f"""<div class="bar-row">
  <div class="bar-label">{d['tech']}</div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{width_pct:.0f}%">{format_salary(d['avg_low'])} — {format_salary(d['avg_high'])}</div>
    <span class="bar-count">n={d['count']}</span>
  </div>
</div>"""

    html += """</div>

<h2>📊 Salary by Experience Level</h2>
<div class="chart-container">
"""

    for d in exp_data:
        badge_class = "badge-high" if d["level"] in ["Lead/Staff", "Senior"] else "badge-mid" if d["level"] == "Mid-level" else "badge-low"
        html += f"""<div class="bar-row">
  <div class="bar-label">{d['level']}</div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{(d['avg_high'] / max(d['avg_high'], 1) * 100):.0f}%">
      {format_salary(d['avg_low'])} — {format_salary(d['avg_high'])}
    </div>
    <span class="bar-count">n={d['count']}</span>
  </div>
</div>"""

    html += f"""</div>

<h2>📋 Top Paying Positions</h2>
<table>
<tr><th>Title</th><th>Company</th><th>Location</th><th>Salary Range</th></tr>
"""

    top_jobs = sorted(results["salary_ranges"], key=lambda x: -x["high"])[:20]
    for j in top_jobs:
        html += f"<tr><td>{j['title'][:50]}</td><td>{j['company'][:25]}</td><td>{j['location'][:20]}</td><td>{format_salary(j['low'])} — {format_salary(j['high'])}</td></tr>"

    html += """</table>
</div>
</body>
</html>"""

    return html


def print_summary(results):
    """Print text summary."""
    print(f"\n💰 Salary Market Analysis")
    print(f"{'=' * 60}")
    print(f"  Total jobs analyzed: {results['total_jobs']}")
    print(f"  With salary data: {results['with_salary']}")

    if results['with_salary'] > 0:
        print(f"\n  📊 Overall Range:")
        print(f"     Average: {format_salary(results['overall_avg_low'])} — {format_salary(results['overall_avg_high'])}")
        print(f"     Median:  {format_salary(results.get('median_low', 0))} — {format_salary(results.get('median_high', 0))}")
        print(f"     Min-Max: {format_salary(results['overall_min'])} — {format_salary(results['overall_max'])}")

        print(f"\n  📍 By Location (top 10):")
        for loc, salaries in sorted(results["by_location"].items(), key=lambda x: -len(x[1]))[:10]:
            avg_low = sum(s[0] for s in salaries) / len(salaries)
            avg_high = sum(s[1] for s in salaries) / len(salaries)
            print(f"     {loc:20s} {format_salary(avg_low):>8s} — {format_salary(avg_high):>8s}  (n={len(salaries)})")

        print(f"\n  🛠️  By Tech Stack (top 10):")
        for tech, salaries in sorted(results["by_tech"].items(), key=lambda x: -len(x[1]))[:10]:
            if len(salaries) >= 2:
                avg_low = sum(s[0] for s in salaries) / len(salaries)
                avg_high = sum(s[1] for s in salaries) / len(salaries)
                print(f"     {tech:20s} {format_salary(avg_low):>8s} — {format_salary(avg_high):>8s}  (n={len(salaries)})")

        print(f"\n  📈 By Experience Level:")
        for level, salaries in results["by_experience"].items():
            if salaries:
                avg_low = sum(s[0] for s in salaries) / len(salaries)
                avg_high = sum(s[1] for s in salaries) / len(salaries)
                print(f"     {level:20s} {format_salary(avg_low):>8s} — {format_salary(avg_high):>8s}  (n={len(salaries)})")

    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Salary Market Rate Analyzer")
    parser.add_argument("--analyze", action="store_true", help="Run salary analysis")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    parser.add_argument("--summary", action="store_true", help="Print text summary")
    parser.add_argument("--all", action="store_true", help="Generate everything")
    args = parser.parse_args()

    if args.analyze or args.summary or args.html or args.all:
        jobs = load_matched_jobs()
        if not jobs:
            jobs = load_job_postings()
        if not jobs:
            print("❌ No job data found. Run the pipeline first.")
            return

        print(f"\n📊 Analyzing {len(jobs)} jobs...")
        results = analyze_salaries(jobs)
        print_summary(results)

        if args.html or args.all:
            html = generate_html_report(results)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = REPORTS_DIR / f"salary_analysis_{timestamp}.html"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\n✅ HTML report saved: {filepath}")

        # Save JSON data
        json_data = {k: v for k, v in results.items() if k not in ["salary_ranges"]}
        json_data["salary_ranges"] = results["salary_ranges"][:50]
        json_path = REPORTS_DIR / "salary_analysis_latest.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
