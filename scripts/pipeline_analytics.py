#!/usr/bin/env python3
"""
Pipeline Analytics — Conversion funnel, board scoring, keyword analysis,
salary insights, and metrics API for the job scraping pipeline.

Usage:
    python3 pipeline_analytics.py                  # full report
    python3 pipeline_analytics.py --json           # JSON output
    python3 pipeline_analytics.py --serve          # HTTP API on :8788
    python3 pipeline_analytics.py --serve --port 9090
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
APPLY_TRACKER = DATA_DIR / "apply_tracker.csv"
JOB_DESC_CSV = DATA_DIR / "job_descriptions.csv"
METRICS_JSON = DATA_DIR / "pipeline_metrics.json"


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# g1: Application Conversion Funnel
# ---------------------------------------------------------------------------

FUNNEL_ORDER = ["notified", "applied", "interviewing", "offer", "rejected", "withdrawn"]


def compute_conversion_funnel(tracker: list) -> dict:
    """Compute application conversion funnel from tracker entries."""
    status_counts = Counter(e.get("status", "unknown") for e in tracker)
    total = len(tracker)

    # Build funnel stages
    funnel = []
    active_statuses = ["notified", "applied", "interviewing", "offer"]
    for status in active_statuses:
        count = status_counts.get(status, 0)
        pct = round(count / max(total, 1) * 100, 1)
        funnel.append({"stage": status, "count": count, "pct": pct})

    # Add terminal states
    terminal = []
    for status in ["rejected", "withdrawn"]:
        count = status_counts.get(status, 0)
        if count > 0:
            terminal.append({"stage": status, "count": count,
                             "pct": round(count / max(total, 1) * 100, 1)})

    # Conversion rates between stages
    rates = {}
    for i in range(1, len(active_statuses)):
        prev = active_statuses[i - 1]
        curr = active_statuses[i]
        prev_count = status_counts.get(prev, 0)
        curr_count = status_counts.get(curr, 0)
        # Everyone past prev should have been in prev at some point
        # For notified→applied: applied / (total - rejected - withdrawn)
        active_total = total - status_counts.get("rejected", 0) - status_counts.get("withdrawn", 0)
        if prev == "notified":
            denominator = active_total
        else:
            denominator = status_counts.get(prev, 0) + status_counts.get(curr, 0)
            # Approximate: everyone in curr was also in prev
            for later in active_statuses[i + 1:]:
                denominator += status_counts.get(later, 0)
        rate = round(curr_count / max(denominator, 1) * 100, 1)
        rates[f"{prev}→{curr}"] = rate

    # Average time in each stage
    stage_durations = defaultdict(list)
    now = datetime.now()
    for entry in tracker:
        status = entry.get("status", "")
        updated_at = entry.get("updated_at", "")
        try:
            updated = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
            days_stuck = (now - updated).days
            stage_durations[status].append(days_stuck)
        except (ValueError, TypeError):
            pass

    avg_durations = {}
    for status, days_list in stage_durations.items():
        if days_list:
            avg_durations[status] = round(sum(days_list) / len(days_list), 1)

    return {
        "total_applications": total,
        "funnel": funnel,
        "terminal": terminal,
        "conversion_rates": rates,
        "avg_days_in_stage": avg_durations,
        "status_breakdown": dict(status_counts),
    }


# ---------------------------------------------------------------------------
# g2: Board Effectiveness Scoring
# ---------------------------------------------------------------------------

def score_board_effectiveness(postings: list, matched: list, tracker: list) -> list:
    """Score each job board on volume, match quality, and application potential."""
    # Build URL sets for cross-referencing
    matched_urls = {m.get("url", "") for m in matched}
    tracker_urls = {t.get("url", "") for t in tracker}

    # Per-source stats from postings
    source_stats = defaultdict(lambda: {
        "total_posted": 0, "matched": 0, "tracked": 0,
        "scores": [], "high_quality": 0
    })

    for p in postings:
        src = p.get("source", "unknown")
        source_stats[src]["total_posted"] += 1
        url = p.get("url", "")
        if url in matched_urls:
            source_stats[src]["matched"] += 1
        if url in tracker_urls:
            source_stats[src]["tracked"] += 1

    # Get scores from matched jobs
    for m in matched:
        src = m.get("source", "unknown")
        try:
            score = int(m.get("score", m.get("_score", 0)))
        except (ValueError, TypeError):
            score = 0
        source_stats[src]["scores"].append(score)
        if score >= 30:
            source_stats[src]["high_quality"] += 1

    # Compute final scores
    results = []
    for src, stats in source_stats.items():
        total = stats["total_posted"]
        matched_count = stats["matched"]
        scores = stats["scores"]
        avg_score = round(sum(scores) / max(len(scores), 1), 1)
        match_rate = round(matched_count / max(total, 1) * 100, 1)
        high_quality_pct = round(stats["high_quality"] / max(matched_count, 1) * 100, 1)

        # Composite effectiveness score (0-100)
        # 40% match rate + 30% avg score quality + 20% high quality pct + 10% volume
        volume_score = min(total / 50 * 100, 100)  # Normalize: 50+ = max
        score_component = (
            0.40 * match_rate +
            0.30 * min(avg_score / 60 * 100, 100) +
            0.20 * high_quality_pct +
            0.10 * volume_score
        )
        effectiveness = round(score_component, 1)

        results.append({
            "source": src,
            "total_posted": total,
            "matched": matched_count,
            "match_rate": match_rate,
            "avg_score": avg_score,
            "high_quality": stats["high_quality"],
            "high_quality_pct": high_quality_pct,
            "tracked": stats["tracked"],
            "effectiveness": effectiveness,
        })

    results.sort(key=lambda x: x["effectiveness"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# g3: Keyword Performance Analysis
# ---------------------------------------------------------------------------

def analyze_keyword_performance(postings: list, matched: list) -> list:
    """Analyze which keywords produce the best matches."""
    matched_urls = {m.get("url", "") for m in matched}

    # Build score lookup from matched
    url_scores = {}
    for m in matched:
        url = m.get("url", "")
        try:
            score = int(m.get("score", m.get("_score", 0)))
        except (ValueError, TypeError):
            score = 0
        url_scores[url] = score

    # Per-keyword stats
    kw_stats = defaultdict(lambda: {
        "total": 0, "matched": 0, "scores": [], "high_quality": 0
    })

    for p in postings:
        kw = p.get("keyword", "unknown").strip()
        if not kw:
            kw = "unknown"
        kw_stats[kw]["total"] += 1
        url = p.get("url", "")
        if url in matched_urls:
            kw_stats[kw]["matched"] += 1
            score = url_scores.get(url, 0)
            kw_stats[kw]["scores"].append(score)
            if score >= 30:
                kw_stats[kw]["high_quality"] += 1

    results = []
    for kw, stats in kw_stats.items():
        total = stats["total"]
        matched_count = stats["matched"]
        scores = stats["scores"]
        avg_score = round(sum(scores) / max(len(scores), 1), 1)
        match_rate = round(matched_count / max(total, 1) * 100, 1)
        high_quality = stats["high_quality"]

        # Keyword effectiveness: match_rate * avg_score / 10
        effectiveness = round(match_rate * avg_score / 10, 1)

        results.append({
            "keyword": kw,
            "total_posted": total,
            "matched": matched_count,
            "match_rate": match_rate,
            "avg_score": avg_score,
            "high_quality": high_quality,
            "effectiveness": effectiveness,
        })

    results.sort(key=lambda x: x["effectiveness"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# g4: Salary Insights
# ---------------------------------------------------------------------------

def parse_salary_value(raw: str) -> float | None:
    """Parse a salary string into a numeric value (midpoint in thousands)."""
    raw = raw.strip()
    if not raw or raw.lower() in ("not specified", "n/a", "none", ""):
        return None

    # Remove currency symbols and whitespace
    cleaned = raw.replace("$", "").replace(",", "").replace("•", "").strip()

    # Try range: "$45k - $65k" or "45000 - 65000"
    range_match = re.search(
        r'([\d.]+)\s*k?\s*[-–]\s*([\d.]+)\s*k?', cleaned, re.IGNORECASE
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        # Detect if 'k' suffix was used
        if 'k' in cleaned.lower():
            low *= 1000
            high *= 1000
        if low == 0 and high == 0:
            return None
        return (low + high) / 2

    # Try single value: "$170k" or "$170,000"
    single_match = re.search(r'([\d.]+)\s*k?', cleaned, re.IGNORECASE)
    if single_match:
        val = float(single_match.group(1))
        if 'k' in cleaned.lower():
            val *= 1000
        if val == 0:
            return None
        return val

    return None


def extract_salary_insights(matched: list) -> dict:
    """Extract salary distribution and insights from matched jobs."""
    salaries = []
    source_salaries = defaultdict(list)

    for m in matched:
        raw = m.get("salary", "")
        val = parse_salary_value(raw)
        if val is not None and val > 0:
            salaries.append(val)
            source_salaries[m.get("source", "unknown")].append(val)

    if not salaries:
        return {"available": False, "message": "No salary data found"}

    salaries.sort()
    n = len(salaries)

    # Percentiles
    def percentile(data, p):
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (k - f) * (data[c] - data[f])

    p25 = round(percentile(salaries, 25))
    p50 = round(percentile(salaries, 50))
    p75 = round(percentile(salaries, 75))
    avg = round(sum(salaries) / n)

    # Buckets
    buckets = [
        ("< $50k", 0, 50000),
        ("$50k-$80k", 50000, 80000),
        ("$80k-$120k", 80000, 120000),
        ("$120k-$180k", 120000, 180000),
        ("$180k-$250k", 180000, 250000),
        ("$250k+", 250000, float("inf")),
    ]
    distribution = []
    for label, low, high in buckets:
        count = sum(1 for s in salaries if low <= s < high)
        distribution.append({"range": label, "count": count,
                             "pct": round(count / n * 100, 1)})

    # Per-source averages
    source_avgs = []
    for src, vals in source_salaries.items():
        if vals:
            source_avgs.append({
                "source": src,
                "avg_salary": round(sum(vals) / len(vals)),
                "count": len(vals),
                "min": round(min(vals)),
                "max": round(max(vals)),
            })
    source_avgs.sort(key=lambda x: x["avg_salary"], reverse=True)

    # Top 10 highest paying jobs
    top_paying = []
    for m in matched:
        val = parse_salary_value(m.get("salary", ""))
        if val is not None:
            top_paying.append({
                "title": m.get("title", "")[:50],
                "company": m.get("company", "")[:30],
                "salary": m.get("salary", "")[:40],
                "salary_value": val,
                "score": m.get("score", m.get("_score", "0")),
                "source": m.get("source", ""),
            })
    top_paying.sort(key=lambda x: x["salary_value"], reverse=True)

    return {
        "available": True,
        "total_with_salary": n,
        "total_matched": len(matched),
        "coverage_pct": round(n / max(len(matched), 1) * 100, 1),
        "min": round(min(salaries)),
        "max": round(max(salaries)),
        "avg": avg,
        "median": p50,
        "p25": p25,
        "p75": p75,
        "distribution": distribution,
        "by_source": source_avgs,
        "top_paying": top_paying[:10],
    }


# ---------------------------------------------------------------------------
# g5: Unified Metrics Report + API
# ---------------------------------------------------------------------------

def build_full_metrics() -> dict:
    """Build complete pipeline metrics report."""
    postings = load_csv(JOB_POSTINGS_CSV)
    matched = load_csv(MATCHED_CSV)
    tracker = load_csv(APPLY_TRACKER)
    descriptions = load_csv(JOB_DESC_CSV)

    funnel = compute_conversion_funnel(tracker)
    boards = score_board_effectiveness(postings, matched, tracker)
    keywords = analyze_keyword_performance(postings, matched)
    salary = extract_salary_insights(matched)

    # Pipeline overview
    now = datetime.now()
    recent_24h = 0
    recent_7d = 0
    for r in postings:
        try:
            scraped = datetime.strptime(r.get("scraped_at", ""), "%Y-%m-%d %H:%M:%S")
            if (now - scraped).days < 1:
                recent_24h += 1
            if (now - scraped).days <= 7:
                recent_7d += 1
        except (ValueError, TypeError):
            pass

    return {
        "generated_at": now.isoformat(),
        "overview": {
            "total_postings": len(postings),
            "total_matched": len(matched),
            "total_descriptions": len(descriptions),
            "total_applications": len(tracker),
            "match_rate": round(len(matched) / max(len(postings), 1) * 100, 1),
            "recent_24h": recent_24h,
            "recent_7d": recent_7d,
        },
        "conversion_funnel": funnel,
        "board_effectiveness": boards,
        "keyword_performance": keywords,
        "salary_insights": salary,
    }


def save_metrics(metrics: dict):
    """Save metrics to JSON file."""
    with open(METRICS_JSON, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"  ✓ Metrics saved: {METRICS_JSON}")


# ---------------------------------------------------------------------------
# HTTP API Server
# ---------------------------------------------------------------------------

class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for pipeline metrics API."""

    metrics_cache: dict = {}
    cache_time: float = 0

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        if path == "/api/metrics":
            self._serve_metrics(force_refresh="--refresh" in query)
        elif path == "/api/funnel":
            self._serve_section("conversion_funnel")
        elif path == "/api/boards":
            self._serve_section("board_effectiveness")
        elif path == "/api/keywords":
            self._serve_section("keyword_performance")
        elif path == "/api/salary":
            self._serve_section("salary_insights")
        elif path == "/api/overview":
            self._serve_section("overview")
        elif path == "/health":
            self.send_json({"status": "ok", "service": "pipeline-analytics"})
        else:
            self.send_json({
                "service": "Pipeline Analytics API",
                "endpoints": [
                    "/api/metrics", "/api/funnel", "/api/boards",
                    "/api/keywords", "/api/salary", "/api/overview", "/health"
                ]
            })

    def _get_metrics(self, force_refresh=False):
        now = datetime.now().timestamp()
        if force_refresh or not self.metrics_cache or (now - self.cache_time) > 300:
            self.metrics_cache = build_full_metrics()
            self.cache_time = now
            save_metrics(self.metrics_cache)
        return self.metrics_cache

    def _serve_metrics(self, force_refresh=False):
        metrics = self._get_metrics(force_refresh=force_refresh)
        self.send_json(metrics)

    def _serve_section(self, section: str):
        metrics = self._get_metrics()
        data = metrics.get(section, {})
        self.send_json({section: data, "generated_at": metrics.get("generated_at")})

    def send_json(self, data: dict):
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_report(metrics: dict):
    """Pretty-print the full analytics report."""
    print(f"\n{'='*80}")
    print(f"  PIPELINE ANALYTICS REPORT")
    print(f"  Generated: {metrics['generated_at']}")
    print(f"{'='*80}")

    # Overview
    ov = metrics["overview"]
    print(f"\n📊 OVERVIEW")
    print(f"  • Postings: {ov['total_postings']} ({ov['recent_24h']} today, {ov['recent_7d']} this week)")
    print(f"  • Matched:  {ov['total_matched']} ({ov['match_rate']}%)")
    print(f"  • Descriptions: {ov['total_descriptions']}")
    print(f"  • Applications: {ov['total_applications']}")

    # Funnel
    funnel = metrics["conversion_funnel"]
    print(f"\n📈 CONVERSION FUNNEL ({funnel['total_applications']} total)")
    for stage in funnel["funnel"]:
        bar = "█" * max(int(stage["pct"] / 5), 1)
        print(f"  {stage['stage']:>15}: {stage['count']:>3} ({stage['pct']:>5}%) {bar}")
    if funnel["terminal"]:
        for t in funnel["terminal"]:
            print(f"  {t['stage']:>15}: {t['count']:>3} ({t['pct']:>5}%)")
    if funnel["conversion_rates"]:
        print(f"  Conversion rates:")
        for rate_name, rate_val in funnel["conversion_rates"].items():
            print(f"    {rate_name}: {rate_val}%")
    if funnel["avg_days_in_stage"]:
        print(f"  Avg days in stage:")
        for stage, days in funnel["avg_days_in_stage"].items():
            print(f"    {stage}: {days} days")

    # Board effectiveness
    boards = metrics["board_effectiveness"]
    print(f"\n📡 BOARD EFFECTIVENESS")
    print(f"  {'Board':<20} {'Posted':>7} {'Matched':>8} {'Rate':>6} {'Avg Score':>10} {'HQ%':>6} {'Effect':>7}")
    print(f"  {'-'*70}")
    for b in boards:
        print(f"  {b['source']:<20} {b['total_posted']:>7} {b['matched']:>8} "
              f"{b['match_rate']:>5}% {b['avg_score']:>9} {b['high_quality_pct']:>5}% "
              f"{b['effectiveness']:>6}")

    # Keyword performance
    keywords = metrics["keyword_performance"]
    print(f"\n🔑 KEYWORD PERFORMANCE")
    print(f"  {'Keyword':<20} {'Posted':>7} {'Matched':>8} {'Rate':>6} {'Avg Score':>10} {'HQ':>4} {'Effect':>7}")
    print(f"  {'-'*70}")
    for k in keywords:
        print(f"  {k['keyword']:<20} {k['total_posted']:>7} {k['matched']:>8} "
              f"{k['match_rate']:>5}% {k['avg_score']:>9} {k['high_quality']:>4} "
              f"{k['effectiveness']:>6}")

    # Salary insights
    salary = metrics["salary_insights"]
    if salary.get("available"):
        print(f"\n💰 SALARY INSIGHTS ({salary['total_with_salary']} jobs with salary data, "
              f"{salary['coverage_pct']}% coverage)")
        print(f"  • Range: ${salary['min']:,} – ${salary['max']:,}")
        print(f"  • Average: ${salary['avg']:,}")
        print(f"  • Median: ${salary['median']:,}")
        print(f"  • P25: ${salary['p25']:,}  |  P75: ${salary['p75']:,}")
        print(f"  Distribution:")
        for bucket in salary["distribution"]:
            bar = "█" * max(int(bucket["pct"] / 2), 1)
            print(f"    {bucket['range']:>12}: {bucket['count']:>3} ({bucket['pct']:>5}%) {bar}")
        if salary.get("by_source"):
            print(f"  By source:")
            for s in salary["by_source"][:5]:
                print(f"    {s['source']:<20} avg: ${s['avg_salary']:,} "
                      f"(n={s['count']}, ${s['min']:,}–${s['max']:,})")
        if salary.get("top_paying"):
            print(f"  Top 5 highest paying:")
            for j in salary["top_paying"][:5]:
                print(f"    • {j['title'][:40]} @ {j['company'][:25]} — {j['salary'][:30]}")
    else:
        print(f"\n💰 SALARY INSIGHTS: {salary.get('message', 'No data')}")

    print(f"\n{'='*80}\n")


def generate_analytics_html(metrics: dict) -> str:
    """Generate a visual HTML analytics dashboard."""
    output_path = DATA_DIR / "pipeline_analytics.html"
    ov = metrics.get("overview", {})
    funnel = metrics.get("conversion_funnel", {})
    boards = metrics.get("board_effectiveness", [])
    keywords = metrics.get("keyword_performance", [])
    salary = metrics.get("salary_insights", {})

    # Build funnel bars
    funnel_html = ""
    max_count = max((s["count"] for s in funnel.get("funnel", [])), default=1)
    for stage in funnel.get("funnel", []):
        pct = max(stage["count"] / max(max_count, 1) * 100, 2)
        funnel_html += f"""
        <div class="funnel-row">
          <span class="funnel-label">{stage['stage']}</span>
          <div class="funnel-bar-wrap">
            <div class="funnel-bar" style="width:{pct}%">{stage['count']}</div>
          </div>
          <span class="funnel-pct">{stage['pct']}%</span>
        </div>"""

    # Build board table
    board_rows = ""
    for b in boards:
        eff_class = "high" if b["effectiveness"] >= 55 else "med" if b["effectiveness"] >= 40 else "low"
        board_rows += f"""
        <tr>
          <td>{b['source']}</td>
          <td>{b['total_posted']}</td>
          <td>{b['matched']}</td>
          <td>{b['match_rate']}%</td>
          <td>{b['avg_score']}</td>
          <td>{b['high_quality']}</td>
          <td class="eff-{eff_class}">{b['effectiveness']}</td>
        </tr>"""

    # Build keyword table
    kw_rows = ""
    for k in keywords:
        kw_rows += f"""
        <tr>
          <td>{k['keyword']}</td>
          <td>{k['total_posted']}</td>
          <td>{k['matched']}</td>
          <td>{k['match_rate']}%</td>
          <td>{k['avg_score']}</td>
          <td>{k['effectiveness']}</td>
        </tr>"""

    # Build salary distribution
    salary_dist_html = ""
    if salary.get("available"):
        max_bucket = max((b["count"] for b in salary.get("distribution", [])), default=1)
        for bucket in salary.get("distribution", []):
            pct = max(bucket["count"] / max(max_bucket, 1) * 100, 2)
            salary_dist_html += f"""
            <div class="funnel-row">
              <span class="funnel-label">{bucket['range']}</span>
              <div class="funnel-bar-wrap">
                <div class="funnel-bar salary-bar" style="width:{pct}%">{bucket['count']}</div>
              </div>
              <span class="funnel-pct">{bucket['pct']}%</span>
            </div>"""
    else:
        salary_dist_html = "<p>No salary data available</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Analytics</title>
<style>
  :root {{
    --bg: #0f172a; --card: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #3b82f6;
    --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --purple: #8b5cf6;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); margin-bottom: 24px; font-size: 0.9rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border-radius: 12px; padding: 20px; border: 1px solid var(--border); }}
  .card h2 {{ font-size: 1rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }}
  .stat-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-row .label {{ color: var(--muted); }}
  .stat-row .value {{ font-weight: 600; }}

  /* Funnel */
  .funnel-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .funnel-label {{ width: 100px; text-align: right; font-size: 0.85rem; color: var(--muted); }}
  .funnel-bar-wrap {{ flex: 1; background: rgba(255,255,255,0.05); border-radius: 6px; height: 28px; }}
  .funnel-bar {{ height: 100%; border-radius: 6px; background: linear-gradient(90deg, var(--accent), var(--purple)); display: flex; align-items: center; padding-left: 10px; font-size: 0.8rem; font-weight: 600; min-width: 30px; }}
  .salary-bar {{ background: linear-gradient(90deg, var(--green), var(--yellow)); }}
  .funnel-pct {{ width: 50px; font-size: 0.85rem; color: var(--muted); }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ text-align: left; padding: 10px 12px; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--border); }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(59,130,246,0.05); }}
  .eff-high {{ color: var(--green); font-weight: 700; }}
  .eff-med {{ color: var(--yellow); font-weight: 700; }}
  .eff-low {{ color: var(--red); font-weight: 700; }}

  .full-width {{ grid-column: 1 / -1; }}
  @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 Pipeline Analytics</h1>
  <p class="subtitle">Generated: {metrics.get('generated_at', 'N/A')}</p>

  <div class="grid">
    <div class="card">
      <h2>📈 Overview</h2>
      <div class="stat-row"><span class="label">Total Postings</span><span class="value">{ov.get('total_postings', 0)}</span></div>
      <div class="stat-row"><span class="label">Matched Jobs</span><span class="value">{ov.get('total_matched', 0)} ({ov.get('match_rate', 0)}%)</span></div>
      <div class="stat-row"><span class="label">Applications</span><span class="value">{ov.get('total_applications', 0)}</span></div>
      <div class="stat-row"><span class="label">New Today</span><span class="value">{ov.get('recent_24h', 0)}</span></div>
      <div class="stat-row"><span class="label">This Week</span><span class="value">{ov.get('recent_7d', 0)}</span></div>
    </div>

    <div class="card">
      <h2>💰 Salary Summary</h2>
      {"<div class='stat-row'><span class='label'>Median</span><span class='value'>$" + str(salary.get('median', 0)) + ",000</span></div>" if salary.get('available') else ""}
      {"<div class='stat-row'><span class='label'>Average</span><span class='value'>$" + str(salary.get('avg', 0)) + ",000</span></div>" if salary.get('available') else ""}
      {"<div class='stat-row'><span class='label'>P25 – P75</span><span class='value'>$" + str(salary.get('p25', 0)) + "k – $" + str(salary.get('p75', 0)) + "k</span></div>" if salary.get('available') else ""}
      {"<div class='stat-row'><span class='label'>Jobs with Salary</span><span class='value'>" + str(salary.get('total_with_salary', 0)) + " (" + str(salary.get('coverage_pct', 0)) + "%)</span></div>" if salary.get('available') else ""}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>📈 Conversion Funnel</h2>
      {funnel_html}
    </div>

    <div class="card">
      <h2>💵 Salary Distribution</h2>
      {salary_dist_html}
    </div>
  </div>

  <div class="grid">
    <div class="card full-width">
      <h2>📡 Board Effectiveness</h2>
      <table>
        <thead><tr><th>Board</th><th>Posted</th><th>Matched</th><th>Rate</th><th>Avg Score</th><th>HQ</th><th>Effectiveness</th></tr></thead>
        <tbody>{board_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="grid">
    <div class="card full-width">
      <h2>🔑 Keyword Performance</h2>
      <table>
        <thead><tr><th>Keyword</th><th>Posted</th><th>Matched</th><th>Rate</th><th>Avg Score</th><th>Effectiveness</th></tr></thead>
        <tbody>{kw_rows}</tbody>
      </table>
    </div>
  </div>
</div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Pipeline Analytics")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--serve", action="store_true", help="Start HTTP API server")
    parser.add_argument("--port", type=int, default=8788, help="API server port")
    args = parser.parse_args()

    if args.serve:
        print(f"\n🚀 Pipeline Analytics API on port {args.port}")
        print(f"   Endpoints: /api/metrics, /api/funnel, /api/boards,")
        print(f"              /api/keywords, /api/salary, /api/overview\n")
        # Pre-build cache
        MetricsHandler.metrics_cache = build_full_metrics()
        MetricsHandler.cache_time = datetime.now().timestamp()
        save_metrics(MetricsHandler.metrics_cache)
        server = HTTPServer(("0.0.0.0", args.port), MetricsHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n  ✓ Server stopped")
            server.server_close()
        return

    print("Building pipeline analytics...")
    metrics = build_full_metrics()
    save_metrics(metrics)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    elif args.html:
        path = generate_analytics_html(metrics)
        print(f"  ✓ HTML dashboard generated: {path}")
    else:
        print_report(metrics)


if __name__ == "__main__":
    main()
