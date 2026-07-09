#!/usr/bin/env python3
"""
Smart Keyword Rotation — Analyze keyword performance and suggest rotations.

Uses pipeline_metrics.json keyword_performance data to:
  1. Identify low-performing keywords (candidates for removal)
  2. Identify high-performing keywords (candidates for expansion)
  3. Suggest new keyword variations based on top-performing tags
  4. Output recommendations via Telegram + console

Usage:
    python3 keyword_rotation.py                 # Analyze and print
    python3 keyword_rotation.py --send-telegram  # Also send to Telegram
    python3 keyword_rotation.py --json           # Output JSON report
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
SCRIPTS_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "scripts"

PIPELINE_METRICS = DATA_DIR / "pipeline_metrics.json"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
REPORT_FILE = DATA_DIR / "keyword_rotation.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# Suggested keyword expansions based on common tech patterns
KEYWORD_EXPANSIONS = {
    "python": ["django", "fastapi", "flask", "celery"],
    "react": ["next.js", "redux", "react native", "remix"],
    "typescript": ["angular", "nestjs", "express"],
    "node.js": ["express", "nestjs", "graphql"],
    "full-stack": ["mern", "mean", "jamstack"],
    "AI": ["machine learning", "LLM", "langchain", "RAG", "prompt engineering"],
    "backend": ["microservices", "REST API", "gRPC"],
    "frontend": ["tailwind", "vue", "svelte"],
    "developer": ["software engineer", "fullstack developer"],
    "API": ["REST", "GraphQL", "webhook"],
}


def load_pipeline_metrics() -> dict:
    """Load pipeline metrics if available."""
    if not PIPELINE_METRICS.exists():
        return {}
    with open(PIPELINE_METRICS, "r") as f:
        return json.load(f)


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def analyze_keywords() -> dict:
    """Analyze keyword performance from data files."""
    postings = load_csv(JOB_POSTINGS_CSV)
    matched = load_csv(MATCHED_CSV)

    if not postings:
        return {"error": "No job_postings.csv found"}

    matched_urls = {m.get("url", "") for m in matched}

    # Build score lookup
    url_scores = {}
    for m in matched:
        url = m.get("url", "")
        try:
            score = int(m.get("_score", m.get("score", 0)))
        except (ValueError, TypeError):
            score = 0
        url_scores[url] = score

    # Per-keyword stats
    kw_stats = defaultdict(lambda: {
        "total": 0, "matched": 0, "scores": [], "high_quality": 0,
        "sources": set(), "tags": Counter()
    })

    for p in postings:
        kw = p.get("keyword", "unknown").strip().lower()
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
        # Track sources per keyword
        kw_stats[kw]["sources"].add(p.get("source", ""))
        # Track tags for expansion suggestions
        tags = p.get("tags", "").split(",")
        for tag in tags:
            tag = tag.strip().lower()
            if tag and tag != kw:
                kw_stats[kw]["tags"][tag] += 1

    # Build results
    results = []
    for kw, stats in kw_stats.items():
        total = stats["total"]
        matched_count = stats["matched"]
        scores = stats["scores"]
        avg_score = round(sum(scores) / max(len(scores), 1), 1)
        match_rate = round(matched_count / max(total, 1) * 100, 1)
        high_quality = stats["high_quality"]
        effectiveness = round(match_rate * avg_score / 10, 1)

        results.append({
            "keyword": kw,
            "total_posted": total,
            "matched": matched_count,
            "match_rate": match_rate,
            "avg_score": avg_score,
            "high_quality": high_quality,
            "effectiveness": effectiveness,
            "source_count": len(stats["sources"]),
            "top_tags": dict(stats["tags"].most_common(5)),
        })

    results.sort(key=lambda x: x["effectiveness"], reverse=True)
    return {"keywords": results, "total_postings": len(postings), "total_matched": len(matched)}


def generate_recommendations(analysis: dict) -> dict:
    """Generate keyword rotation recommendations."""
    keywords = analysis.get("keywords", [])
    if not keywords:
        return {"keep": [], "remove": [], "expand": []}

    # Top performers: effectiveness > median and high_quality > 0
    scores = [k["effectiveness"] for k in keywords]
    median_eff = sorted(scores)[len(scores) // 2] if scores else 0

    top_performers = [k for k in keywords if k["effectiveness"] >= median_eff and k["high_quality"] > 0]
    bottom_performers = [k for k in keywords if k["effectiveness"] < median_eff * 0.5 or (k["matched"] == 0 and k["total_posted"] > 5)]

    # Suggest expansions from top performers' tags
    expansion_suggestions = []
    seen_kws = {k["keyword"] for k in keywords}
    for k in top_performers[:3]:
        kw = k["keyword"]
        # From KEYWORD_EXPANSIONS
        if kw in KEYWORD_EXPANSIONS:
            for suggestion in KEYWORD_EXPANSIONS[kw]:
                if suggestion.lower() not in seen_kws:
                    expansion_suggestions.append({
                        "suggested": suggestion,
                        "based_on": kw,
                        "reason": f"Expansion of top performer '{kw}' (eff={k['effectiveness']})"
                    })
        # From actual tags seen in postings
        for tag, count in k.get("top_tags", {}).items():
            if tag not in seen_kws and count >= 3 and len(tag) > 2:
                expansion_suggestions.append({
                    "suggested": tag,
                    "based_on": kw,
                    "reason": f"Seen {count}x in '{kw}' postings"
                })

    # Deduplicate suggestions
    seen_suggestions = set()
    unique_suggestions = []
    for s in expansion_suggestions:
        if s["suggested"].lower() not in seen_suggestions:
            seen_suggestions.add(s["suggested"].lower())
            unique_suggestions.append(s)

    return {
        "keep": [{"keyword": k["keyword"], "effectiveness": k["effectiveness"],
                   "match_rate": k["match_rate"], "high_quality": k["high_quality"]}
                  for k in top_performers[:5]],
        "remove": [{"keyword": k["keyword"], "effectiveness": k["effectiveness"],
                     "total_posted": k["total_posted"], "matched": k["matched"]}
                    for k in bottom_performers[:5]],
        "expand": unique_suggestions[:8],
    }


def build_telegram_message(analysis: dict, recommendations: dict) -> str:
    """Build Telegram message with keyword rotation suggestions."""
    lines = []
    lines.append(f"<b>🔄 KEYWORD ROTATION REPORT</b>")
    lines.append(f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>")
    lines.append("")

    total = analysis.get("total_postings", 0)
    matched = analysis.get("total_matched", 0)
    lines.append(f"📊 Postings: {total} | Matched: {matched}")
    lines.append("")

    # Top performers
    keep = recommendations.get("keep", [])
    if keep:
        lines.append("<b>✅ KEEP (Top Performers):</b>")
        for k in keep:
            lines.append(f"  • <b>{k['keyword']}</b> — eff={k['effectiveness']}, match={k['match_rate']}%, HQ={k['high_quality']}")
        lines.append("")

    # Remove suggestions
    remove = recommendations.get("remove", [])
    if remove:
        lines.append("<b>⚠️ CONSIDER REMOVING:</b>")
        for k in remove:
            lines.append(f"  • <b>{k['keyword']}</b> — eff={k['effectiveness']}, posted={k['total_posted']}, matched={k['matched']}")
        lines.append("")

    # Expansion suggestions
    expand = recommendations.get("expand", [])
    if expand:
        lines.append("<b>💡 SUGGESTED ADDITIONS:</b>")
        for s in expand[:6]:
            lines.append(f"  • <b>{s['suggested']}</b> — {s['reason']}")
        lines.append("")

    lines.append("─────────────────")
    lines.append(f"<i>Run: python3 keyword_rotation.py --json</i>")

    return "\n".join(lines)


def send_telegram(message: str):
    """Send message to Telegram."""
    import httpx
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
        print("✓ Telegram notification sent")
        return True
    except Exception as e:
        print(f"✗ Telegram failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Smart Keyword Rotation")
    parser.add_argument("--send-telegram", action="store_true", help="Send report to Telegram")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  KEYWORD ROTATION ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    analysis = analyze_keywords()
    if "error" in analysis:
        print(f"  ✗ {analysis['error']}")
        sys.exit(1)

    recommendations = generate_recommendations(analysis)

    if args.json:
        report = {
            "generated_at": datetime.now().isoformat(),
            "analysis": analysis,
            "recommendations": recommendations,
        }
        with open(REPORT_FILE, "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        print(f"\n  ✓ Report saved: {REPORT_FILE}")
        return

    # Console output
    keywords = analysis["keywords"]
    print(f"  Total keywords analyzed: {len(keywords)}")
    print(f"  Total postings: {analysis['total_postings']}")
    print(f"  Total matched: {analysis['total_matched']}")

    print(f"\n  KEYWORD PERFORMANCE RANKING:")
    print(f"  {'Keyword':<20} {'Posted':>7} {'Matched':>8} {'Match%':>7} {'AvgScore':>9} {'HQ':>4} {'Effect':>7}")
    print(f"  {'-'*70}")
    for k in keywords:
        print(f"  {k['keyword']:<20} {k['total_posted']:>7} {k['matched']:>8} {k['match_rate']:>6.1f}% {k['avg_score']:>9.1f} {k['high_quality']:>4} {k['effectiveness']:>7.1f}")

    print(f"\n  RECOMMENDATIONS:")
    print(f"\n  ✅ KEEP (Top Performers):")
    for k in recommendations["keep"]:
        print(f"    • {k['keyword']} (effectiveness={k['effectiveness']})")

    print(f"\n  ⚠️  CONSIDER REMOVING:")
    for k in recommendations["remove"]:
        print(f"    • {k['keyword']} (effectiveness={k['effectiveness']}, matched={k['matched']}/{k['total_posted']})")

    print(f"\n  💡 SUGGESTED ADDITIONS:")
    for s in recommendations["expand"]:
        print(f"    • {s['suggested']} — {s['reason']}")

    if args.send_telegram:
        msg = build_telegram_message(analysis, recommendations)
        send_telegram(msg)

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
