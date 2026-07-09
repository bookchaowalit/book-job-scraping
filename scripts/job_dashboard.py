#!/usr/bin/env python3
"""
Job Pipeline Dashboard — generates a self-contained HTML dashboard
showing job scraping stats, source breakdown, price distribution, and top matches.

Usage:
    python3 job_dashboard.py                    # Generate HTML dashboard
    python3 job_dashboard.py --open             # Generate and open in browser
    python3 job_dashboard.py --output path.html # Custom output path
"""

import argparse
import csv
import json
import os
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
OUTPUT_DIR = ROOT / "data" / "briefings"

JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"

# Board display names and icons — keyed by actual CSV source values
BOARD_META = {
    "RemoteOK":       {"name": "RemoteOK",     "icon": "🌐", "type": "job"},
    "Himalayas":      {"name": "Himalayas",    "icon": "🏔️", "type": "job"},
    "Landing.jobs":   {"name": "Landing.jobs", "icon": "🛬", "type": "job"},
    "Jobicy":         {"name": "Jobicy",       "icon": "🧊", "type": "job"},
    "Indeed":         {"name": "Indeed",       "icon": "🔎", "type": "job"},
    "Seek.AU":        {"name": "Seek AU",      "icon": "🦘", "type": "job"},
    "Seek.NZ":        {"name": "Seek NZ",      "icon": "🥝", "type": "job"},
    "JobThai":        {"name": "JobThai",      "icon": "🇹🇭", "type": "job"},
    "JobsDB-TH":      {"name": "JobsDB TH",    "icon": "🇹🇭", "type": "job"},
    "JobBKK":         {"name": "JobBKK",       "icon": "🇹🇭", "type": "job"},
    "HN_WhoIsHiring": {"name": "HN Hiring",   "icon": "🧡", "type": "job"},
    "Remotive":       {"name": "Remotive",     "icon": "📡", "type": "job"},
    "Arc.dev":        {"name": "Arc.dev",      "icon": "💎", "type": "job"},
    "WorkingNomads":  {"name": "WorkingNomads","icon": "🌍", "type": "job"},
    "Turing":         {"name": "Turing",       "icon": "🧠", "type": "job"},
    "Upwork":         {"name": "Upwork",       "icon": "🟢", "type": "freelance"},
    "Fastwork":       {"name": "Fastwork",     "icon": "⚡", "type": "freelance"},
    "Fiverr":         {"name": "Fiverr",       "icon": "💚", "type": "freelance"},
    "Toptal":         {"name": "Toptal",       "icon": "🔷", "type": "freelance"},
}

# Apply tracker CSV
APPLY_TRACKER_CSV = DATA_DIR / "apply_tracker.csv"


def load_csv(filepath: Path) -> list:
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def parse_price(price_str: str) -> float:
    """Extract numeric value from price string."""
    if not price_str:
        return 0.0
    import re
    nums = re.findall(r'[\d,]+\.?\d*', price_str.replace(',', ''))
    if nums:
        try:
            return float(nums[0])
        except ValueError:
            return 0.0
    return 0.0


def generate_dashboard_data() -> dict:
    """Process CSV data into dashboard-ready JSON."""
    jobs = load_csv(JOB_POSTINGS_CSV)
    matched = load_csv(MATCHED_JOBS_CSV)
    apply_tracker = load_csv(APPLY_TRACKER_CSV)

    # --- Apply tracker stats ---
    apply_stats = {
        "total_tracked": len(apply_tracker),
        "notified": 0,
        "applied": 0,
        "skipped": 0,
        "by_status": {},
    }
    for entry in apply_tracker:
        status = entry.get("status", "unknown")
        apply_stats["by_status"][status] = apply_stats["by_status"].get(status, 0) + 1
        if status == "notified":
            apply_stats["notified"] += 1
        elif status == "applied":
            apply_stats["applied"] += 1
        elif status == "skipped":
            apply_stats["skipped"] += 1

    # --- Source breakdown ---
    source_counts = Counter()
    source_with_salary = defaultdict(list)
    for j in jobs:
        src = j.get("source", "unknown")
        source_counts[src] += 1
        sal = j.get("salary", "") or j.get("price", "")
        if sal:
            val = parse_price(sal)
            if val > 0:
                source_with_salary[src].append(val)

    # --- Matched jobs breakdown ---
    score_field = "_score" if (matched and "_score" in matched[0]) else "score"
    score_buckets = {"20+": 0, "15-19": 0, "10-14": 0, "8-9": 0}
    for j in matched:
        score = int(j.get(score_field, 0))
        if score >= 20:
            score_buckets["20+"] += 1
        elif score >= 15:
            score_buckets["15-19"] += 1
        elif score >= 10:
            score_buckets["10-14"] += 1
        elif score >= 8:
            score_buckets["8-9"] += 1

    # --- Top matched jobs ---
    top_jobs = sorted(matched, key=lambda x: int(x.get(score_field, 0)), reverse=True)[:20]
    top_jobs_data = []
    for j in top_jobs:
        top_jobs_data.append({
            "title": (j.get("title", "") or "")[:60],
            "company": j.get("company", "") or "",
            "score": int(j.get(score_field, 0)),
            "salary": j.get("salary", "") or j.get("price", "") or "N/A",
            "source": j.get("source", ""),
            "url": j.get("url", ""),
            "posted": j.get("posted_date", "") or j.get("posted", "") or j.get("date", "") or "",
        })

    # --- Price distribution for freelance ---
    freelance_prices = {}
    for src in ["Upwork", "Fastwork", "Fiverr", "Toptal"]:
        prices = source_with_salary.get(src, [])
        if prices:
            freelance_prices[src] = {
                "min": min(prices),
                "max": max(prices),
                "avg": sum(prices) / len(prices),
                "count": len(prices),
            }

    # --- Board health ---
    board_health = []
    for board_id, meta in BOARD_META.items():
        count = source_counts.get(board_id, 0)
        prices = source_with_salary.get(board_id, [])
        board_health.append({
            "id": board_id,
            "name": meta["name"],
            "icon": meta["icon"],
            "type": meta["type"],
            "count": count,
            "with_price": len(prices),
            "price_coverage": f"{len(prices)*100//count}%" if count > 0 else "N/A",
            "status": "active" if count > 0 else "inactive",
        })

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_jobs": len(jobs),
        "total_matched": len(matched),
        "source_counts": dict(source_counts),
        "score_buckets": score_buckets,
        "top_jobs": top_jobs_data,
        "freelance_prices": freelance_prices,
        "board_health": board_health,
        "total_boards_active": sum(1 for b in board_health if b["status"] == "active"),
        "apply_stats": apply_stats,
    }


def generate_html(data: dict) -> str:
    """Generate self-contained HTML dashboard."""
    board_health_json = json.dumps(data["board_health"], ensure_ascii=False)
    source_counts_json = json.dumps(data["source_counts"], ensure_ascii=False)
    top_jobs_json = json.dumps(data["top_jobs"], ensure_ascii=False)
    freelance_prices_json = json.dumps(data["freelance_prices"], ensure_ascii=False)
    score_buckets_json = json.dumps(data["score_buckets"], ensure_ascii=False)
    apply_stats_json = json.dumps(data["apply_stats"], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Pipeline Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
  .header {{ text-align: center; margin-bottom: 32px; }}
  .header h1 {{ font-size: 28px; color: #f8fafc; margin-bottom: 4px; }}
  .header .subtitle {{ color: #94a3b8; font-size: 14px; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .stat-card {{ background: #1e293b; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #334155; }}
  .stat-card .value {{ font-size: 36px; font-weight: 700; color: #38bdf8; }}
  .stat-card .label {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
  @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155; }}
  .card h2 {{ font-size: 16px; color: #f8fafc; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
  .chart-container {{ position: relative; height: 300px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 10px 12px; color: #94a3b8; border-bottom: 1px solid #334155; font-weight: 500; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #334155; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; }}
  .badge-hot {{ background: #dc2626; color: white; }}
  .badge-strong {{ background: #ea580c; color: white; }}
  .badge-good {{ background: #2563eb; color: white; }}
  .badge-ok {{ background: #475569; color: white; }}
  .badge-active {{ background: #16a34a; color: white; }}
  .badge-inactive {{ background: #475569; color: #94a3b8; }}
  .source-tag {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 6px; font-size: 11px; background: #334155; }}
  .price-range {{ color: #4ade80; font-family: monospace; }}
  a {{ color: #38bdf8; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .footer {{ text-align: center; color: #475569; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b; }}
</style>
</head>
<body>

<div class="header">
  <h1>💼 Job Pipeline Dashboard</h1>
  <div class="subtitle">Generated: {data['generated_at']} | {data['total_boards_active']} boards active</div>
</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="value">{data['total_jobs']:,}</div>
    <div class="label">Total Jobs Scraped</div>
  </div>
  <div class="stat-card">
    <div class="value">{data['total_matched']:,}</div>
    <div class="label">Matched (Score ≥ 8)</div>
  </div>
  <div class="stat-card">
    <div class="value">{data['total_boards_active']}</div>
    <div class="label">Active Boards</div>
  </div>
  <div class="stat-card">
    <div class="value">{data['score_buckets'].get('20+', 0)}</div>
    <div class="label">Hot Jobs (Score 20+)</div>
  </div>
  <div class="stat-card">
    <div class="value">{data['apply_stats']['total_tracked']}</div>
    <div class="label">Jobs Tracked</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color: #4ade80;">{data['apply_stats']['applied']}</div>
    <div class="label">Applied</div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <h2>📊 Jobs by Source Board</h2>
    <div class="chart-container"><canvas id="sourceChart"></canvas></div>
  </div>
  <div class="card">
    <h2>🎯 Match Score Distribution</h2>
    <div class="chart-container"><canvas id="scoreChart"></canvas></div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <h2>💰 Freelance Price Ranges</h2>
    <div class="chart-container"><canvas id="priceChart"></canvas></div>
  </div>
  <div class="card">
    <h2>🏥 Board Health</h2>
    <table>
      <thead><tr><th>Board</th><th>Jobs</th><th>Price %</th><th>Status</th></tr></thead>
      <tbody id="boardHealthBody"></tbody>
    </table>
  </div>
</div>

<div class="card" style="margin-bottom: 32px;">
  <h2>🔥 Top 20 Matched Jobs</h2>
  <table>
    <thead><tr><th>Score</th><th>Title</th><th>Company</th><th>Source</th><th>Salary/Price</th><th>Posted</th></tr></thead>
    <tbody id="topJobsBody"></tbody>
  </table>
</div>

<div class="grid-2">
  <div class="card">
    <h2>📊 Apply Tracker Status</h2>
    <div class="chart-container"><canvas id="applyChart"></canvas></div>
  </div>
  <div class="card">
    <h2>📈 Tracker Summary</h2>
    <div id="applySummary" style="padding: 20px;"></div>
  </div>
</div>

<div class="footer">
  Solo Empire Job Pipeline | 19 boards | 12 keywords | Auto-updated daily at 8:30 AM
</div>

<script>
const boardHealth = {board_health_json};
const topJobs = {top_jobs_json};
const freelancePrices = {freelance_prices_json};
const scoreBuckets = {score_buckets_json};
const sourceCounts = {source_counts_json};
const applyStats = {apply_stats_json};

// Board health table
const bhBody = document.getElementById('boardHealthBody');
boardHealth.sort((a,b) => b.count - a.count).forEach(b => {{
  const row = document.createElement('tr');
  row.innerHTML = `
    <td><span class="source-tag">${{b.icon}} ${{b.name}}</span></td>
    <td>${{b.count.toLocaleString()}}</td>
    <td>${{b.price_coverage}}</td>
    <td><span class="badge ${{b.status === 'active' ? 'badge-active' : 'badge-inactive'}}">${{b.status}}</span></td>
  `;
  bhBody.appendChild(row);
}});

// Top jobs table
const tjBody = document.getElementById('topJobsBody');
topJobs.forEach(j => {{
  const scoreClass = j.score >= 20 ? 'badge-hot' : j.score >= 15 ? 'badge-strong' : j.score >= 10 ? 'badge-good' : 'badge-ok';
  const meta = boardHealth.find(b => b.id === j.source) || {{}};
  const row = document.createElement('tr');
  row.innerHTML = `
    <td><span class="badge ${{scoreClass}}">${{j.score}}</span></td>
    <td><a href="${{j.url}}" target="_blank">${{j.title}}</a></td>
    <td>${{j.company}}</td>
    <td><span class="source-tag">${{meta.icon || ''}} ${{meta.name || j.source}}</span></td>
    <td class="price-range">${{j.salary}}</td>
    <td>${{j.posted}}</td>
  `;
  tjBody.appendChild(row);
}});

// Source chart
const boardNames = boardHealth.map(b => b.name);
const boardCounts = boardHealth.map(b => b.count);
const boardColors = boardHealth.map(b => b.type === 'freelance' ? '#4ade80' : '#38bdf8');
new Chart(document.getElementById('sourceChart'), {{
  type: 'bar',
  data: {{ labels: boardNames, datasets: [{{ data: boardCounts, backgroundColor: boardColors, borderRadius: 4 }}] }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}, y: {{ grid: {{ display: false }}, ticks: {{ color: '#e2e8f0', font: {{ size: 11 }} }} }} }}
  }}
}});

// Score distribution chart
new Chart(document.getElementById('scoreChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(scoreBuckets),
    datasets: [{{ data: Object.values(scoreBuckets), backgroundColor: ['#dc2626', '#ea580c', '#2563eb', '#475569'], borderWidth: 0 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', padding: 16 }} }} }}
  }}
}});

// Freelance price chart
const fpKeys = Object.keys(freelancePrices);
if (fpKeys.length > 0) {{
  const fpLabels = fpKeys.map(k => k.charAt(0).toUpperCase() + k.slice(1));
  new Chart(document.getElementById('priceChart'), {{
    type: 'bar',
    data: {{
      labels: fpLabels,
      datasets: [
        {{ label: 'Min', data: fpKeys.map(k => freelancePrices[k].min), backgroundColor: '#475569', borderRadius: 4 }},
        {{ label: 'Avg', data: fpKeys.map(k => Math.round(freelancePrices[k].avg)), backgroundColor: '#38bdf8', borderRadius: 4 }},
        {{ label: 'Max', data: fpKeys.map(k => freelancePrices[k].max), backgroundColor: '#4ade80', borderRadius: 4 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
      scales: {{ x: {{ grid: {{ display: false }}, ticks: {{ color: '#e2e8f0' }} }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8', callback: v => '$' + v.toLocaleString() }} }} }}
    }}
  }});
}} else {{
  document.getElementById('priceChart').parentElement.innerHTML = '<p style="color:#94a3b8;text-align:center;padding:40px;">No freelance price data yet</p>';
}}

// Apply tracker chart
const applyLabels = Object.keys(applyStats.by_status);
const applyValues = Object.values(applyStats.by_status);
const applyColors = applyLabels.map(l => {{
  if (l === 'applied') return '#4ade80';
  if (l === 'notified') return '#38bdf8';
  if (l === 'skipped') return '#94a3b8';
  return '#475569';
}});
if (applyLabels.length > 0) {{
  new Chart(document.getElementById('applyChart'), {{
    type: 'doughnut',
    data: {{
      labels: applyLabels.map(l => l.charAt(0).toUpperCase() + l.slice(1)),
      datasets: [{{ data: applyValues, backgroundColor: applyColors, borderWidth: 0 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', padding: 16 }} }} }}
    }}
  }});
}} else {{
  document.getElementById('applyChart').parentElement.innerHTML = '<p style="color:#94a3b8;text-align:center;padding:40px;">No apply tracker data yet</p>';
}}

// Apply summary
const summaryDiv = document.getElementById('applySummary');
const total = applyStats.total_tracked || 0;
const convRate = total > 0 ? ((applyStats.applied / total) * 100).toFixed(1) : 0;
summaryDiv.innerHTML = `
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    <div style="text-align: center;">
      <div style="font-size: 32px; font-weight: 700; color: #38bdf8;">${{total}}</div>
      <div style="font-size: 13px; color: #94a3b8;">Total Tracked</div>
    </div>
    <div style="text-align: center;">
      <div style="font-size: 32px; font-weight: 700; color: #4ade80;">${{convRate}}%</div>
      <div style="font-size: 13px; color: #94a3b8;">Conversion Rate</div>
    </div>
    <div style="text-align: center;">
      <div style="font-size: 24px; color: #38bdf8;">${{applyStats.notified}}</div>
      <div style="font-size: 12px; color: #94a3b8;">Notified</div>
    </div>
    <div style="text-align: center;">
      <div style="font-size: 24px; color: #94a3b8;">${{applyStats.skipped}}</div>
      <div style="font-size: 12px; color: #94a3b8;">Skipped</div>
    </div>
  </div>
`;
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate Job Pipeline HTML Dashboard")
    parser.add_argument("--output", "-o", default=str(OUTPUT_DIR / "job_dashboard.html"),
                        help="Output HTML file path")
    parser.add_argument("--open", action="store_true", help="Open in browser after generation")
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Generating job dashboard...")

    data = generate_dashboard_data()
    html = generate_html(data)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Total jobs: {data['total_jobs']:,}")
    print(f"  Matched: {data['total_matched']:,}")
    print(f"  Active boards: {data['total_boards_active']}")
    print(f"  Dashboard saved to: {output_path}")

    if args.open:
        webbrowser.open(f"file://{output_path}")


if __name__ == "__main__":
    main()
