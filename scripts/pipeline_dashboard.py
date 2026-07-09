#!/usr/bin/env python3
"""
Pipeline Dashboard Generator - Creates an HTML dashboard from pipeline data.
Generates a self-contained HTML file with charts and stats.

Usage:
    python3 pipeline_dashboard.py
    python3 pipeline_dashboard.py --output dashboard.html
    python3 pipeline_dashboard.py --open  # generate and open in browser
"""

import argparse
import csv
import json
import os
import sys
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
JOB_DESC_CSV = DATA_DIR / "job_descriptions.csv"
OUTPUT_HTML = DATA_DIR / "pipeline_dashboard.html"


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def gather_stats() -> dict:
    postings = load_csv(JOB_POSTINGS_CSV)
    matched = load_csv(MATCHED_CSV)
    tracker = load_csv(APPLY_TRACKER)
    descriptions = load_csv(JOB_DESC_CSV)

    # Source breakdown
    source_counts = Counter(r.get("source", "unknown") for r in postings)
    # Keyword breakdown
    keyword_counts = Counter(r.get("keyword", "unknown") for r in postings)
    # Location breakdown from matched jobs
    location_counts = Counter()
    for r in matched:
        loc = r.get("location", "")
        if "remote" in loc.lower():
            location_counts["Remote"] += 1
        elif "bangkok" in loc.lower() or "thailand" in loc.lower():
            location_counts["Thailand"] += 1
        elif "tokyo" in loc.lower() or "japan" in loc.lower():
            location_counts["Japan"] += 1
        elif "singapore" in loc.lower():
            location_counts["Singapore"] += 1
        elif "australia" in loc.lower() or "sydney" in loc.lower() or "melbourne" in loc.lower():
            location_counts["Australia"] += 1
        elif "new zealand" in loc.lower() or "auckland" in loc.lower():
            location_counts["New Zealand"] += 1
        elif "uk" in loc.lower() or "london" in loc.lower():
            location_counts["UK"] += 1
        elif "us" in loc.lower() or "usa" in loc.lower() or "san francisco" in loc.lower() or "new york" in loc.lower():
            location_counts["USA"] += 1
        else:
            location_counts["Other"] += 1

    # Score distribution from matched jobs
    score_buckets = {"9-10": 0, "7-8": 0, "5-6": 0, "3-4": 0, "1-2": 0}
    for r in matched:
        try:
            score = float(r.get("score", 0))
        except ValueError:
            continue
        if score >= 9: score_buckets["9-10"] += 1
        elif score >= 7: score_buckets["7-8"] += 1
        elif score >= 5: score_buckets["5-6"] += 1
        elif score >= 3: score_buckets["3-4"] += 1
        else: score_buckets["1-2"] += 1

    # Application tracker
    app_statuses = Counter(r.get("status", "unknown") for r in tracker)

    # Description scrape stats
    desc_statuses = Counter(r.get("status", "unknown") for r in descriptions)

    # Top companies
    company_counts = Counter(r.get("company", "Unknown") for r in matched[:200])

    # Recent scrapes (last 7 days from scraped_at)
    now = datetime.now()
    recent_count = 0
    for r in postings:
        try:
            scraped = datetime.strptime(r.get("scraped_at", ""), "%Y-%m-%d %H:%M:%S")
            if (now - scraped).days <= 7:
                recent_count += 1
        except (ValueError, TypeError):
            pass

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "totals": {
            "postings": len(postings),
            "matched": len(matched),
            "applications": len(tracker),
            "descriptions": len(descriptions),
            "match_rate": round(len(matched) / max(len(postings), 1) * 100, 1),
            "desc_rate": round(len(descriptions) / max(len(matched), 1) * 100, 1),
            "recent_7d": recent_count,
        },
        "sources": dict(source_counts.most_common(20)),
        "keywords": dict(keyword_counts.most_common(12)),
        "locations": dict(location_counts.most_common(10)),
        "scores": score_buckets,
        "app_statuses": dict(app_statuses),
        "desc_statuses": dict(desc_statuses),
        "top_companies": dict(company_counts.most_common(15)),
        "top_jobs": [
            {
                "title": r.get("title", "")[:60],
                "company": r.get("company", "")[:30],
                "score": r.get("score", "0"),
                "location": r.get("location", "")[:30],
                "url": r.get("url", ""),
                "source": r.get("source", ""),
            }
            for r in sorted(matched, key=lambda x: float(x.get("score", 0)), reverse=True)[:15]
        ],
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Pipeline Dashboard</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8; --green: #4ade80; --yellow: #facc15; --red: #f87171; --purple: #a78bfa; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, system-ui, sans-serif; padding: 20px; min-height: 100vh; }
  .header { text-align: center; margin-bottom: 30px; }
  .header h1 { font-size: 2rem; background: linear-gradient(135deg, var(--accent), var(--purple)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .header .subtitle { color: var(--muted); margin-top: 6px; font-size: 0.9rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .card h3 { font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }
  .stat-big { font-size: 2.5rem; font-weight: 700; color: var(--accent); }
  .stat-label { color: var(--muted); font-size: 0.85rem; margin-top: 4px; }
  .stat-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); }
  .stat-row:last-child { border-bottom: none; }
  .stat-row .label { color: var(--muted); }
  .stat-row .value { font-weight: 600; }
  .bar-chart { display: flex; flex-direction: column; gap: 8px; }
  .bar-item { display: flex; align-items: center; gap: 10px; }
  .bar-item .bar-label { width: 100px; font-size: 0.8rem; color: var(--muted); text-align: right; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-item .bar-track { flex: 1; height: 22px; background: rgba(56,189,248,0.1); border-radius: 4px; overflow: hidden; position: relative; }
  .bar-item .bar-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, var(--accent), var(--purple)); display: flex; align-items: center; padding-left: 8px; font-size: 0.75rem; font-weight: 600; color: white; min-width: 30px; }
  .table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .table th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px; border-bottom: 1px solid var(--border); }
  .table td { padding: 8px; border-bottom: 1px solid var(--border); }
  .table tr:hover td { background: rgba(56,189,248,0.05); }
  .table a { color: var(--accent); text-decoration: none; }
  .table a:hover { text-decoration: underline; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
  .badge-green { background: rgba(74,222,128,0.15); color: var(--green); }
  .badge-yellow { background: rgba(250,204,21,0.15); color: var(--yellow); }
  .badge-red { background: rgba(248,113,113,0.15); color: var(--red); }
  .badge-blue { background: rgba(56,189,248,0.15); color: var(--accent); }
  .full-width { grid-column: 1 / -1; }
  .pipeline-flow { display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
  .pipeline-step { text-align: center; padding: 16px 20px; background: rgba(56,189,248,0.08); border-radius: 10px; border: 1px solid var(--border); min-width: 120px; }
  .pipeline-step .step-num { font-size: 1.8rem; font-weight: 700; color: var(--accent); }
  .pipeline-step .step-label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  .pipeline-arrow { font-size: 1.5rem; color: var(--muted); }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .pipeline-flow { flex-direction: column; } .pipeline-arrow { transform: rotate(90deg); } }
</style>
</head>
<body>
<div class="header">
  <h1>Job Scraping Pipeline</h1>
  <div class="subtitle">Generated: __GENERATED_AT__</div>
</div>

<!-- Pipeline Flow -->
<div class="card full-width" style="margin-bottom:20px">
  <h3>Pipeline Flow</h3>
  <div class="pipeline-flow">
    <div class="pipeline-step"><div class="step-num">__POSTINGS__</div><div class="step-label">Job Postings</div></div>
    <div class="pipeline-arrow">&rarr;</div>
    <div class="pipeline-step"><div class="step-num">__MATCHED__</div><div class="step-label">Matched (__MATCH_RATE__%)</div></div>
    <div class="pipeline-arrow">&rarr;</div>
    <div class="pipeline-step"><div class="step-num">__DESCS__</div><div class="step-label">Descriptions (__DESC_RATE__%)</div></div>
    <div class="pipeline-arrow">&rarr;</div>
    <div class="pipeline-step"><div class="step-num">__APPS__</div><div class="step-label">Applications</div></div>
  </div>
</div>

<!-- KPI Cards -->
<div class="grid">
  <div class="card">
    <h3>Last 7 Days</h3>
    <div class="stat-big">__RECENT_7D__</div>
    <div class="stat-label">New postings scraped</div>
  </div>
  <div class="card">
    <h3>Match Rate</h3>
    <div class="stat-big">__MATCH_RATE__%</div>
    <div class="stat-label">__MATCHED__ of __POSTINGS__ jobs matched</div>
  </div>
  <div class="card">
    <h3>Description Coverage</h3>
    <div class="stat-big">__DESC_RATE__%</div>
    <div class="stat-label">__DESCS__ of __MATCHED__ matched jobs</div>
  </div>
  <div class="card">
    <h3>Applications</h3>
    <div class="stat-big">__APPS__</div>
    <div class="stat-label">Tracked applications</div>
  </div>
</div>

<!-- Charts Row -->
<div class="grid">
  <div class="card">
    <h3>Score Distribution</h3>
    <div class="bar-chart" id="score-chart"></div>
  </div>
  <div class="card">
    <h3>Top Sources</h3>
    <div class="bar-chart" id="source-chart"></div>
  </div>
  <div class="card">
    <h3>Locations</h3>
    <div class="bar-chart" id="location-chart"></div>
  </div>
  <div class="card">
    <h3>Keywords</h3>
    <div class="bar-chart" id="keyword-chart"></div>
  </div>
</div>

<!-- Top Jobs Table -->
<div class="grid">
  <div class="card full-width">
    <h3>Top 15 Matched Jobs</h3>
    <table class="table">
      <thead><tr><th>Score</th><th>Title</th><th>Company</th><th>Location</th><th>Source</th></tr></thead>
      <tbody id="jobs-table"></tbody>
    </table>
  </div>
</div>

<!-- Companies & App Status -->
<div class="grid">
  <div class="card">
    <h3>Top Companies</h3>
    <div class="bar-chart" id="company-chart"></div>
  </div>
  <div class="card">
    <h3>Application Status</h3>
    <div id="app-statuses"></div>
  </div>
</div>

<script>
const DATA = __DATA_JSON__;

function renderBarChart(el, data, color) {
  const max = Math.max(...Object.values(data), 1);
  const container = document.getElementById(el);
  container.innerHTML = Object.entries(data)
    .sort((a,b) => b[1] - a[1])
    .map(([label, val]) => `
      <div class="bar-item">
        <div class="bar-label" title="${label}">${label}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${(val/max*100).toFixed(1)}%;${color ? 'background:'+color : ''}">${val}</div>
        </div>
      </div>
    `).join('');
}

function scoreBadge(s) {
  const n = parseFloat(s);
  if (n >= 8) return 'badge-green';
  if (n >= 6) return 'badge-yellow';
  return 'badge-red';
}

// Render charts
renderBarChart('score-chart', DATA.scores, 'linear-gradient(90deg, #4ade80, #38bdf8)');
renderBarChart('source-chart', DATA.sources);
renderBarChart('location-chart', DATA.locations, 'linear-gradient(90deg, #a78bfa, #f472b6)');
renderBarChart('keyword-chart', DATA.keywords, 'linear-gradient(90deg, #facc15, #f97316)');
renderBarChart('company-chart', DATA.top_companies);

// Render jobs table
document.getElementById('jobs-table').innerHTML = DATA.top_jobs.map(j => `
  <tr>
    <td><span class="badge ${scoreBadge(j.score)}">${j.score}</span></td>
    <td><a href="${j.url}" target="_blank">${j.title}</a></td>
    <td>${j.company}</td>
    <td>${j.location}</td>
    <td><span class="badge badge-blue">${j.source}</span></td>
  </tr>
`).join('');

// Render app statuses
const appEl = document.getElementById('app-statuses');
const appData = DATA.app_statuses;
if (Object.keys(appData).length === 0) {
  appEl.innerHTML = '<div style="color:var(--muted);padding:20px;text-align:center">No applications tracked yet</div>';
} else {
  appEl.innerHTML = Object.entries(appData).map(([k,v]) => `
    <div class="stat-row"><span class="label">${k}</span><span class="value">${v}</span></div>
  `).join('');
}
</script>
</body>
</html>"""


def generate_dashboard(output_path: Path, open_browser: bool = False):
    stats = gather_stats()
    t = stats["totals"]

    html = HTML_TEMPLATE
    html = html.replace("__GENERATED_AT__", stats["generated_at"])
    html = html.replace("__POSTINGS__", str(t["postings"]))
    html = html.replace("__MATCHED__", str(t["matched"]))
    html = html.replace("__MATCH_RATE__", str(t["match_rate"]))
    html = html.replace("__DESCS__", str(t["descriptions"]))
    html = html.replace("__DESC_RATE__", str(t["desc_rate"]))
    html = html.replace("__APPS__", str(t["applications"]))
    html = html.replace("__RECENT_7D__", str(t["recent_7d"]))
    html = html.replace("__DATA_JSON__", json.dumps(stats, indent=2))

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")

    if open_browser:
        webbrowser.open(f"file://{output_path}")


def main():
    parser = argparse.ArgumentParser(description="Pipeline Dashboard Generator")
    parser.add_argument("--output", default="", help="Output HTML path")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()

    output = Path(args.output) if args.output else OUTPUT_HTML
    generate_dashboard(output, open_browser=args.open)


if __name__ == "__main__":
    main()
