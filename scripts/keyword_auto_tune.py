#!/usr/bin/env python3
"""
Smart Keyword Auto-Tuning — Automatically optimize search keywords based on conversion data.
Drops low-performing keywords and adds new ones based on match rates and application success.

Usage:
    python keyword_auto_tune.py --analyze
    python keyword_auto_tune.py --suggest
    python keyword_auto_tune.py --apply  # Update keywords in scrape config
    python keyword_auto_tune.py --report
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
KEYWORDS_FILE = DATA_DIR / "keyword_performance.json"
SCRAPE_CONFIG = SCRIPT_DIR / "scrape_job_postings.py"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# Minimum thresholds
MIN_MATCHES_FOR_SIGNAL = 3
MIN_CONVERSION_RATE = 0.05  # 5%
PERFORMANCE_WINDOW_DAYS = 30


def ai_call(messages, temperature=0.5):
    """Call OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature, max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  AI error: {e}")
        return None


def load_keyword_performance():
    """Load saved keyword performance data."""
    if KEYWORDS_FILE.exists():
        return json.loads(KEYWORDS_FILE.read_text())
    return {"keywords": {}, "last_analyzed": None}


def save_keyword_performance(data):
    """Save keyword performance data."""
    KEYWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_analyzed"] = datetime.now().isoformat()
    KEYWORDS_FILE.write_text(json.dumps(data, indent=2, default=str))


def extract_keywords_from_jobs():
    """Extract all keywords/skills from matched jobs."""
    keywords = Counter()
    if not MATCHED_JOBS_CSV.exists():
        return keywords

    with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Extract from title
            title = row.get("title", "").lower()
            for word in title.split():
                if len(word) > 3 and word.isalpha():
                    keywords[word] += 1

            # Extract from skills/description
            skills = row.get("skills", row.get("description", ""))[:500].lower()
            for word in skills.split():
                clean = "".join(c for c in word if c.isalpha())
                if len(clean) > 4:
                    keywords[clean] += 1

    return keywords


def analyze_keyword_performance():
    """Analyze which keywords produce the best results."""
    print("Analyzing keyword performance...\n")

    # Load data
    matched = []
    if MATCHED_JOBS_CSV.exists():
        with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
            matched = list(csv.DictReader(f))

    applications = []
    if APPLICATIONS_CSV.exists():
        with open(APPLICATIONS_CSV, "r", encoding="utf-8") as f:
            applications = list(csv.DictReader(f))

    postings = []
    if JOB_POSTINGS_CSV.exists():
        with open(JOB_POSTINGS_CSV, "r", encoding="utf-8") as f:
            postings = list(csv.DictReader(f))

    print(f"Data loaded: {len(matched)} matched, {len(applications)} applied, {len(postings)} postings")

    # Analyze keyword frequency in matched jobs
    keyword_matches = Counter()
    keyword_scores = {}

    for job in matched:
        title = job.get("title", "").lower()
        description = (job.get("description", "") + " " + job.get("skills", ""))[:500].lower()
        score = float(job.get("_score", job.get("score", 0)))

        # Extract meaningful words
        words = set()
        for text in [title, description]:
            for word in text.split():
                clean = "".join(c for c in word if c.isalpha())
                if len(clean) > 4:
                    words.add(clean)

        for word in words:
            keyword_matches[word] += 1
            if word not in keyword_scores:
                keyword_scores[word] = []
            keyword_scores[word].append(score)

    # Calculate metrics per keyword
    keyword_metrics = {}
    for kw, count in keyword_matches.most_common(100):
        scores = keyword_scores.get(kw, [])
        avg_score = sum(scores) / len(scores) if scores else 0

        # Check if keyword appears in applications
        app_count = sum(1 for a in applications if kw in str(a).lower())

        # Conversion rate
        conversion = app_count / count if count > 0 else 0

        keyword_metrics[kw] = {
            "match_count": count,
            "avg_match_score": round(avg_score, 2),
            "application_count": app_count,
            "conversion_rate": round(conversion, 3),
            "performance": "high" if avg_score > 70 else "medium" if avg_score > 50 else "low",
        }

    # Save analysis
    analysis = {
        "keywords": keyword_metrics,
        "total_analyzed": len(keyword_metrics),
        "analyzed_at": datetime.now().isoformat(),
        "data_summary": {
            "matched_jobs": len(matched),
            "applications": len(applications),
            "postings": len(postings),
        }
    }
    save_keyword_performance(analysis)

    # Print results
    top_performers = sorted(keyword_metrics.items(), key=lambda x: x[1]["avg_match_score"], reverse=True)[:20]
    low_performers = sorted(
        [(k, v) for k, v in keyword_metrics.items() if v["match_count"] >= MIN_MATCHES_FOR_SIGNAL],
        key=lambda x: x[1]["avg_match_score"]
    )[:10]

    print(f"\n🏆 TOP PERFORMING KEYWORDS (by avg match score):")
    print(f"  {'Keyword':<25} {'Matches':<10} {'Avg Score':<10} {'Apps':<8} {'Conv%'}")
    print(f"  {'-'*65}")
    for kw, m in top_performers:
        print(f"  {kw:<25} {m['match_count']:<10} {m['avg_match_score']:<10} {m['application_count']:<8} {m['conversion_rate']*100:.1f}%")

    if low_performers:
        print(f"\n⚠️  LOW PERFORMING KEYWORDS (candidates for removal):")
        print(f"  {'Keyword':<25} {'Matches':<10} {'Avg Score':<10} {'Conv%'}")
        print(f"  {'-'*55}")
        for kw, m in low_performers:
            print(f"  {kw:<25} {m['match_count']:<10} {m['avg_match_score']:<10} {m['conversion_rate']*100:.1f}%")

    return analysis


def suggest_new_keywords(analysis=None):
    """Use AI to suggest new keywords based on performance data."""
    if not analysis:
        analysis = load_keyword_performance()

    existing_keywords = list(analysis.get("keywords", {}).keys())[:50]
    top_keywords = sorted(
        analysis.get("keywords", {}).items(),
        key=lambda x: x[1]["avg_match_score"], reverse=True
    )[:20]

    print("Generating keyword suggestions...\n")

    # AI-powered suggestions
    if OPENROUTER_API_KEY:
        prompt = f"""Based on this job search keyword performance data, suggest 10 NEW keywords to add.

Current top performing keywords:
{chr(10).join(f'- {kw}: {m["match_count"]} matches, score {m["avg_match_score"]}' for kw, m in top_keywords)}

Current keywords (don't suggest these):
{', '.join(existing_keywords[:30])}

Profile: Senior Full-Stack Developer (Python, React, Next.js, TypeScript, Node.js, AI/ML)
Location: Bangkok, Thailand (open to remote)

Suggest 10 keywords that:
1. Are trending in the current job market
2. Match the profile's skills
3. Are NOT already in the current list
4. Would likely produce high-quality matches

Return as JSON: {{"keywords": ["kw1", "kw2", ...], "reasoning": "..."}}"""

        result = ai_call([
            {"role": "system", "content": "You are a job search optimization expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ], temperature=0.7)

        if result:
            try:
                result = result.strip()
                if "```" in result:
                    result = result.split("```")[1]
                    if result.startswith("json"):
                        result = result[4:]
                data = json.loads(result)
                suggestions = data.get("keywords", [])
                reasoning = data.get("reasoning", "")
                print(f"🤖 AI Suggested Keywords:\n{reasoning}\n")
                for kw in suggestions:
                    print(f"  + {kw}")
                return suggestions
            except:
                pass

    # Fallback: suggest based on common tech trends
    trending = [
        "langchain", "rag", "vector database", "llm", "prompt engineering",
        "system design", "microservices", "kubernetes", "terraform",
        "graphql", "webassembly", "edge computing", "rust", "go",
        "computer vision", "nlp", "mlops", "data pipeline",
    ]
    existing_set = set(k.lower() for k in existing_keywords)
    suggestions = [kw for kw in trending if kw.lower() not in existing_set][:10]

    print("📈 Trending keyword suggestions:")
    for kw in suggestions:
        print(f"  + {kw}")

    return suggestions


def apply_keywords(new_keywords=None, remove_keywords=None):
    """Update the keyword configuration."""
    print("Keyword update summary:")

    if remove_keywords:
        print(f"\n  Keywords to REMOVE: {', '.join(remove_keywords)}")
    if new_keywords:
        print(f"\n  Keywords to ADD: {', '.join(new_keywords)}")

    print(f"\n  Current keywords are in: scrape_job_postings.py (DEFAULT_KEYWORDS)")
    print(f"  Update the DEFAULT_KEYWORDS list manually or use --report for full analysis.")


def generate_report():
    """Generate comprehensive keyword optimization report."""
    analysis = load_keyword_performance()
    keywords = analysis.get("keywords", {})

    if not keywords:
        print("No keyword data yet. Run --analyze first.")
        return

    report = f"""# Keyword Optimization Report
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Data:** {analysis.get('data_summary', {})}

## Performance Summary
- Keywords analyzed: {len(keywords)}
- High performers (score > 70): {sum(1 for v in keywords.values() if v['performance'] == 'high')}
- Medium performers (score 50-70): {sum(1 for v in keywords.values() if v['performance'] == 'medium')}
- Low performers (score < 50): {sum(1 for v in keywords.values() if v['performance'] == 'low')}

## Top 20 Keywords
| Keyword | Matches | Avg Score | Applications | Conversion |
|---------|---------|-----------|-------------|------------|
"""
    top = sorted(keywords.items(), key=lambda x: x[1]["avg_match_score"], reverse=True)[:20]
    for kw, m in top:
        report += f"| {kw} | {m['match_count']} | {m['avg_match_score']} | {m['application_count']} | {m['conversion_rate']*100:.1f}% |\n"

    # Suggestions
    suggestions = suggest_new_keywords(analysis)
    if suggestions:
        report += f"\n## Suggested New Keywords\n"
        for kw in suggestions:
            report += f"- {kw}\n"

    # Save report
    report_dir = DATA_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"keyword_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_file.write_text(report)
    print(f"\nReport saved: {report_file}")
    print(report)


def main():
    parser = argparse.ArgumentParser(description="Smart Keyword Auto-Tuning")
    parser.add_argument("--analyze", action="store_true", help="Analyze keyword performance")
    parser.add_argument("--suggest", action="store_true", help="Suggest new keywords")
    parser.add_argument("--apply", action="store_true", help="Apply keyword changes")
    parser.add_argument("--report", action="store_true", help="Generate full report")
    args = parser.parse_args()

    if args.analyze:
        analyze_keyword_performance()
    elif args.suggest:
        analysis = analyze_keyword_performance() if not KEYWORDS_FILE.exists() else load_keyword_performance()
        suggest_new_keywords(analysis)
    elif args.apply:
        apply_keywords()
    elif args.report:
        generate_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
