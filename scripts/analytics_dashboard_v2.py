#!/usr/bin/env python3
"""
Pipeline Analytics Dashboard v2
Advanced HTML analytics with charts: application funnel, response rate trends,
salary distribution, keyword effectiveness, weekly progress.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REPORTS_DIR = DATA_DIR / "analytics_dashboards"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(filename, limit=2000):
    """Load CSV data."""
    csv_path = DATA_DIR / filename
    if not csv_path.exists():
        return []
    try:
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                rows.append(row)
        return rows
    except Exception:
        return []


def load_json(filename):
    """Load JSON data."""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def compute_funnel(applications):
    """Compute application funnel data."""
    stages = Counter()
    for app in applications:
        stage = app.get("stage", "unknown")
        stages[stage] += 1

    funnel_order = [
        "discovered", "saved", "applied", "screening",
        "technical", "onsite", "offer", "accepted", "rejected", "withdrawn"
    ]

    funnel = []
    for stage in funnel_order:
        count = stages.get(stage, 0)
        funnel.append({"stage": stage, "count": count})

    return funnel


def compute_weekly_trend(jobs, weeks=12):
    """Compute weekly job discovery trend."""
    weekly = defaultdict(int)
    now = datetime.now()

    for job in jobs:
        date_str = job.get("scraped_at", job.get("discovered_at", ""))
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            week_key = dt.strftime("%Y-W%W")
            weekly[week_key] += 1
        except Exception:
            pass

    # Fill in missing weeks
    result = []
    for i in range(weeks - 1, -1, -1):
        dt = now - timedelta(weeks=i)
        week_key = dt.strftime("%Y-W%W")
        label = dt.strftime("%b %d")
        result.append({
            "week": week_key,
            "label": label,
            "count": weekly.get(week_key, 0),
        })

    return result


def compute_keyword_effectiveness(matched_jobs):
    """Analyze keyword match effectiveness."""
    keyword_stats = defaultdict(lambda: {"count": 0, "total_score": 0, "high_score": 0})

    for job in matched_jobs:
        keywords_str = job.get("matched_keywords", "")
        score = float(job.get("match_score", job.get("score", 0)) or 0)

        for kw in re.split(r'[,;|]+', keywords_str):
            kw = kw.strip().lower()
            if kw and len(kw) > 2:
                keyword_stats[kw]["count"] += 1
                keyword_stats[kw]["total_score"] += score
                keyword_stats[kw]["high_score"] = max(keyword_stats[kw]["high_score"], score)

    result = []
    for kw, stats in keyword_stats.items():
        avg_score = stats["total_score"] / stats["count"] if stats["count"] else 0
        result.append({
            "keyword": kw,
            "match_count": stats["count"],
            "avg_score": round(avg_score, 1),
            "max_score": round(stats["high_score"], 1),
        })

    return sorted(result, key=lambda x: -x["match_count"])[:30]


def compute_source_breakdown(jobs):
    """Breakdown jobs by source."""
    sources = Counter()
    for job in jobs:
        source = job.get("source", "unknown")
        sources[source] += 1
    return [{"source": s, "count": c} for s, c in sources.most_common(15)]


def compute_salary_distribution(jobs):
    """Compute salary distribution buckets."""
    buckets = defaultdict(int)
    for job in jobs:
        salary_str = job.get("salary_min", "") or job.get("salary", "")
        if not salary_str:
            continue
        salary_str = str(salary_str).replace(",", "").replace("$", "").lower()
        match = re.search(r'(\d+)', salary_str)
        if match:
            val = int(match.group(1))
            if "k" in salary_str or val < 10000:
                val *= 1000
            bucket = f"${val // 1000}K"
            buckets[bucket] += 1

    return [{"range": k, "count": v} for k, v in sorted(buckets.items())]


def compute_company_frequency(jobs, top_n=20):
    """Most frequently appearing companies."""
    companies = Counter()
    for job in jobs:
        company = job.get("company", "Unknown")
        if company and company != "Unknown":
            companies[company] += 1
    return [{"company": c, "count": n} for c, n in companies.most_common(top_n)]


def generate_html_dashboard(funnel, weekly_trend, keywords, sources, salary_dist, companies, stats):
    """Generate comprehensive HTML dashboard."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Funnel chart data
    funnel_labels = json.dumps([f["stage"] for f in funnel])
    funnel_values = json.dumps([f["count"] for f in funnel])

    # Weekly trend data
    trend_labels = json.dumps([w["label"] for w in weekly_trend])
    trend_values = json.dumps([w["count"] for w in weekly_trend])

    # Keyword chart data
    kw_labels = json.dumps([k["keyword"] for k in keywords[:15]])
    kw_values = json.dumps([k["match_count"] for k in keywords[:15]])

    # Source pie data
    source_labels = json.dumps([s["source"] for s in sources])
    source_values = json.dumps([s["count"] for s in sources])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Analytics Dashboard v2 — {timestamp}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ font-size: 28px; color: #38bdf8; margin-bottom: 5px; }}
h2 {{ font-size: 18px; color: #818cf8; margin: 25px 0 12px; border-bottom: 1px solid #334155; padding-bottom: 6px; }}
.subtitle {{ color: #64748b; margin-bottom: 25px; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-bottom: 20px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 18px; border: 1px solid #334155; }}
.card-title {{ font-size: 14px; color: #94a3b8; margin-bottom: 10px; }}
.card-value {{ font-size: 32px; font-weight: 700; color: #38bdf8; }}
.card-sub {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
.chart-box {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 15px; border: 1px solid #334155; }}
.bar-row {{ display: flex; align-items: center; margin: 6px 0; }}
.bar-label {{ width: 120px; font-size: 12px; color: #cbd5e1; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bar-track {{ flex: 1; height: 22px; background: #0f172a; border-radius: 5px; overflow: hidden; position: relative; }}
.bar-fill {{ height: 100%; border-radius: 5px; display: flex; align-items: center; padding-left: 6px; font-size: 11px; color: white; transition: width 0.5s ease; }}
.bar-fill.blue {{ background: linear-gradient(90deg, #3b82f6, #60a5fa); }}
.bar-fill.purple {{ background: linear-gradient(90deg, #8b5cf6, #a78bfa); }}
.bar-fill.green {{ background: linear-gradient(90deg, #10b981, #34d399); }}
.bar-fill.orange {{ background: linear-gradient(90deg, #f59e0b, #fbbf24); }}
.bar-fill.pink {{ background: linear-gradient(90deg, #ec4899, #f472b6); }}
.bar-count {{ position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 11px; color: #475569; }}
.funnel-step {{ display: flex; align-items: center; margin: 4px 0; }}
.funnel-bar {{ height: 28px; border-radius: 4px; display: flex; align-items: center; padding: 0 10px; font-size: 12px; color: white; font-weight: 600; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; padding: 8px 10px; color: #94a3b8; background: #0f172a; border-bottom: 1px solid #334155; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #1e293b44; color: #cbd5e1; }}
tr:hover td {{ background: #1e293b66; }}
.tag {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; background: #334155; color: #94a3b8; margin: 1px; }}
.progress-ring {{ display: inline-flex; align-items: center; gap: 8px; }}
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
.dot.green {{ background: #10b981; }}
.dot.yellow {{ background: #f59e0b; }}
.dot.red {{ background: #ef4444; }}
.dot.blue {{ background: #3b82f6; }}
</style>
</head>
<body>
<div class="container">
<h1>📊 Pipeline Analytics Dashboard v2</h1>
<p class="subtitle">Generated {timestamp} | Comprehensive job pipeline intelligence</p>

<!-- KPI Cards -->
<div class="grid">
  <div class="card">
    <div class="card-title">Total Jobs Discovered</div>
    <div class="card-value">{stats['total_jobs']}</div>
    <div class="card-sub">Across all sources</div>
  </div>
  <div class="card">
    <div class="card-title">Matched Jobs</div>
    <div class="card-value">{stats['matched_jobs']}</div>
    <div class="card-sub">With AI match scores</div>
  </div>
  <div class="card">
    <div class="card-title">Applications</div>
    <div class="card-value">{stats['total_applications']}</div>
    <div class="card-sub">Tracked submissions</div>
  </div>
  <div class="card">
    <div class="card-title">Interview Stage</div>
    <div class="card-value">{stats['interview_stage']}</div>
    <div class="card-sub">Active interviews</div>
  </div>
  <div class="card">
    <div class="card-title">Conversion Rate</div>
    <div class="card-value">{stats['conversion_rate']:.1f}%</div>
    <div class="card-sub">Applied → Interview</div>
  </div>
  <div class="card">
    <div class="card-title">Unique Companies</div>
    <div class="card-value">{stats['unique_companies']}</div>
    <div class="card-sub">In pipeline</div>
  </div>
</div>

<!-- Application Funnel -->
<h2>📈 Application Funnel</h2>
<div class="chart-box">
"""

    max_funnel = max(f["count"] for f in funnel) if funnel else 1
    colors = ["blue", "purple", "green", "orange", "pink", "blue", "purple", "green", "orange", "pink"]
    for i, f in enumerate(funnel):
        width = (f["count"] / max_funnel * 100) if max_funnel else 0
        color = colors[i % len(colors)]
        html += f"""<div class="funnel-step">
  <div class="bar-label">{f['stage']}</div>
  <div class="bar-track">
    <div class="bar-fill {color}" style="width:{max(width, 2):.0f}%">{f['count']}</div>
  </div>
</div>"""

    html += """</div>

<!-- Weekly Discovery Trend -->
<h2>📅 Weekly Job Discovery Trend</h2>
<div class="chart-box">
"""

    max_trend = max(w["count"] for w in weekly_trend) if weekly_trend else 1
    for w in weekly_trend:
        width = (w["count"] / max_trend * 100) if max_trend else 0
        html += f"""<div class="bar-row">
  <div class="bar-label">{w['label']}</div>
  <div class="bar-track">
    <div class="bar-fill blue" style="width:{max(width, 1):.0f}%">{w['count']}</div>
  </div>
</div>"""

    html += """</div>

<!-- Keyword Effectiveness -->
<h2>🔑 Keyword Effectiveness</h2>
<div class="chart-box">
"""

    max_kw = max(k["match_count"] for k in keywords[:15]) if keywords else 1
    for k in keywords[:15]:
        width = (k["match_count"] / max_kw * 100) if max_kw else 0
        html += f"""<div class="bar-row">
  <div class="bar-label" title="{k['keyword']}">{k['keyword']}</div>
  <div class="bar-track">
    <div class="bar-fill purple" style="width:{max(width, 1):.0f}%">{k['match_count']} (avg: {k['avg_score']})</div>
  </div>
</div>"""

    html += """</div>

<!-- Source Breakdown -->
<h2>🌐 Job Source Breakdown</h2>
<div class="chart-box">
"""

    max_src = max(s["count"] for s in sources) if sources else 1
    for s in sources:
        width = (s["count"] / max_src * 100) if max_src else 0
        html += f"""<div class="bar-row">
  <div class="bar-label">{s['source']}</div>
  <div class="bar-track">
    <div class="bar-fill green" style="width:{max(width, 1):.0f}%">{s['count']}</div>
  </div>
</div>"""

    html += """</div>

<!-- Top Companies -->
<h2>🏢 Top Companies in Pipeline</h2>
<div class="chart-box">
<table>
<tr><th>Company</th><th>Jobs Found</th><th>Presence</th></tr>
"""

    max_comp = companies[0]["count"] if companies else 1
    for c in companies[:15]:
        width = (c["count"] / max_comp * 100) if max_comp else 0
        html += f"""<tr>
  <td>{c['company']}</td>
  <td>{c['count']}</td>
  <td><div class="bar-track" style="height:16px"><div class="bar-fill orange" style="width:{max(width, 2):.0f}%">{c['count']}</div></div></td>
</tr>"""

    html += """</table>
</div>

<!-- Salary Distribution -->
<h2>💰 Salary Distribution</h2>
<div class="chart-box">
"""

    if salary_dist:
        max_sal = max(s["count"] for s in salary_dist) if salary_dist else 1
        for s in salary_dist:
            width = (s["count"] / max_sal * 100) if max_sal else 0
            html += f"""<div class="bar-row">
  <div class="bar-label">{s['range']}</div>
  <div class="bar-track">
    <div class="bar-fill pink" style="width:{max(width, 1):.0f}%">{s['count']}</div>
  </div>
</div>"""
    else:
        html += "<p style='color:#64748b'>No salary data available</p>"

    html += f"""</div>

<!-- Footer -->
<p style="text-align:center;color:#475569;margin-top:30px;font-size:12px">
  Pipeline Analytics Dashboard v2 | Auto-generated {timestamp} | Job Scraping Pipeline
</p>
</div>
</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser(description="Pipeline Analytics Dashboard v2")
    parser.add_argument("--generate", action="store_true", help="Generate dashboard")
    parser.add_argument("--stats", action="store_true", help="Print stats summary")
    parser.add_argument("--open", action="store_true", help="Open after generating")
    args = parser.parse_args()

    # Load all data
    job_postings = load_csv("job_postings.csv")
    matched_jobs = load_csv("matched_jobs.csv")
    app_tracker = load_json("application_tracker.json")
    applications = app_tracker.get("applications", [])

    # Compute all analytics
    funnel = compute_funnel(applications)
    weekly_trend = compute_weekly_trend(job_postings + matched_jobs)
    keywords = compute_keyword_effectiveness(matched_jobs)
    sources = compute_source_breakdown(job_postings + matched_jobs)
    salary_dist = compute_salary_distribution(matched_jobs)
    companies = compute_company_frequency(job_postings + matched_jobs)

    # Compute KPI stats
    all_companies = set()
    for j in job_postings + matched_jobs:
        c = j.get("company", "")
        if c:
            all_companies.add(c)

    interview_count = sum(1 for a in applications if a.get("stage") in ["technical", "onsite"])
    applied_count = sum(1 for a in applications if a.get("stage") in ["applied", "screening", "technical", "onsite", "offer"])
    conversion = (interview_count / applied_count * 100) if applied_count > 0 else 0

    stats = {
        "total_jobs": len(job_postings) + len(matched_jobs),
        "matched_jobs": len(matched_jobs),
        "total_applications": len(applications),
        "interview_stage": interview_count,
        "conversion_rate": conversion,
        "unique_companies": len(all_companies),
    }

    if args.stats:
        print(f"\n📊 Pipeline Stats")
        print(f"{'=' * 50}")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print(f"\n  Funnel stages:")
        for f in funnel:
            print(f"    {f['stage']}: {f['count']}")
        return

    if args.generate:
        print(f"\n📊 Generating Analytics Dashboard v2...")
        print(f"   Jobs: {stats['total_jobs']} | Matched: {stats['matched_jobs']} | Applications: {stats['total_applications']}")

        html = generate_html_dashboard(funnel, weekly_trend, keywords, sources, salary_dist, companies, stats)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = REPORTS_DIR / f"analytics_dashboard_{timestamp}.html"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        # Also save as latest
        latest_path = REPORTS_DIR / "analytics_dashboard_latest.html"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"\n✅ Dashboard generated: {filepath}")
        print(f"✅ Latest: {latest_path}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
