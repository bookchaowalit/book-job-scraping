#!/usr/bin/env python3
"""
Auto-match job postings against personal tech stack.
Scores and ranks jobs from job_postings.csv by relevance to your skills.
Outputs a filtered, ranked report for immediate bidding.

Outputs:
    - domains/product/engineering/book-dev/book-scraping/data/matched_jobs.csv (ranked matches)
    - Console report with top matches and bid-ready links

Usage:
    python3 filter_job_matches.py
    python3 filter_job_matches.py --min-score 3
    python3 filter_job_matches.py --top 10
    python3 filter_job_matches.py --stack "python,next.js,react,scraping"
"""

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"

# ─── Tech Stack Profile ───────────────────────────────────────────────
# Primary skills (high weight) — core competencies to bid on
PRIMARY_SKILLS = {
    "python":       {"weight": 10, "aliases": ["python3", "python2", "django", "flask", "fastapi", "py"]},
    "next.js":      {"weight": 10, "aliases": ["nextjs", "next.js", "next-js", "next13", "next14", "next15"]},
    "scraping":     {"weight": 10, "aliases": ["scraping", "scraper", "web scraping", "crawling", "crawler", "spider", "puppeteer", "playwright", "selenium", "firecrawl"]},
    "automation":   {"weight": 10, "aliases": ["automation", "automated", "automate", "workflow", "workflows", "n8n", "zapier", "make.com"]},
}

# Secondary skills (medium weight) — supporting technologies
SECONDARY_SKILLS = {
    "javascript":   {"weight": 5, "aliases": ["javascript", "js", "es6", "es2020"]},
    "typescript":   {"weight": 5, "aliases": ["typescript", "ts"]},
    "react":        {"weight": 5, "aliases": ["react", "react.js", "reactjs", "react native"]},
    "node.js":      {"weight": 5, "aliases": ["node.js", "nodejs", "node", "express", "expressjs"]},
    "api":          {"weight": 5, "aliases": ["api", "rest", "restful", "graphql", "endpoints"]},
    "data pipeline": {"weight": 5, "aliases": ["etl", "data pipeline", "data engineering", "airflow", "spark"]},
    "docker":       {"weight": 4, "aliases": ["docker", "container", "kubernetes", "k8s"]},
    "database":     {"weight": 4, "aliases": ["postgresql", "postgres", "mysql", "mongodb", "redis", "database", "sql", "sqlite"]},
    "ai/ml":        {"weight": 4, "aliases": ["ai/ml", "machine learning", "deep learning", "llm", "gpt", "openai", "nlp", "langchain"]},
    "fullstack":    {"weight": 5, "aliases": ["fullstack", "full-stack", "full stack", "fullstack developer"]},
}

# Bonus modifiers
BONUS_KEYWORDS = {
    "remote":       3,
    "freelance":    3,
    "contract":     2,
    "startup":      2,
    "saas":         2,
    "mvp":          2,
    "greenfield":   2,
}

# Negative signals — reduce score for these
NEGATIVE_KEYWORDS = {
    "junior":       -3,
    "entry level":  -3,
    "intern":       -5,
    "unpaid":       -10,
    "volunteer":    -5,
}


def load_jobs(csv_path: str) -> list:
    """Load job postings from CSV."""
    jobs = []
    if not os.path.exists(csv_path):
        print(f"ERROR: {csv_path} not found. Run scrape_job_postings.py first.")
        return jobs
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    return jobs


def normalize(text: str) -> str:
    """Lowercase and strip for matching."""
    return text.lower().strip()


def score_job(job: dict, custom_stack: list = None) -> tuple:
    """
    Score a job against the tech stack.
    Returns (total_score, matched_primary, matched_secondary, bonuses, negatives).
    """
    # Build search text from all relevant fields
    title = normalize(job.get("title", ""))
    tags = normalize(job.get("tags", ""))
    keyword = normalize(job.get("keyword", ""))
    search_text = f"{title} {tags} {keyword}"

    matched_primary = []
    matched_secondary = []
    bonuses = []
    negatives = []
    total_score = 0

    # Use custom stack if provided, otherwise use defaults
    if custom_stack:
        custom_primary = {s: {"weight": 10, "aliases": [s]} for s in custom_stack}
        primary_skills = custom_primary
        secondary_skills = {}
    else:
        primary_skills = PRIMARY_SKILLS
        secondary_skills = SECONDARY_SKILLS

    # Check primary skills
    for skill_name, skill_info in primary_skills.items():
        for alias in skill_info["aliases"]:
            if alias in search_text:
                matched_primary.append(skill_name)
                total_score += skill_info["weight"]
                break

    # Check secondary skills
    for skill_name, skill_info in secondary_skills.items():
        for alias in skill_info["aliases"]:
            if alias in search_text:
                matched_secondary.append(skill_name)
                total_score += skill_info["weight"]
                break

    # Check bonuses
    for kw, bonus in BONUS_KEYWORDS.items():
        if kw in search_text:
            bonuses.append(kw)
            total_score += bonus

    # Check negatives
    for kw, penalty in NEGATIVE_KEYWORDS.items():
        if kw in search_text:
            negatives.append(kw)
            total_score += penalty  # penalty is negative

    return total_score, matched_primary, matched_secondary, bonuses, negatives


def parse_salary(salary_str: str) -> str:
    """Clean up salary display."""
    if not salary_str or salary_str.strip() == "":
        return "Not specified"
    return salary_str.strip()


def format_report(matches: list, top_n: int) -> str:
    """Format the console report."""
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  JOB MATCH REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  {len(matches)} matches found | Showing top {min(top_n, len(matches))}")
    lines.append(f"{'='*70}\n")

    for i, m in enumerate(matches[:top_n], 1):
        job = m["job"]
        score = m["score"]
        primary = m["primary"]
        secondary = m["secondary"]
        bonuses = m["bonuses"]

        # Score indicator
        if score >= 20:
            indicator = "🔥 HOT"
        elif score >= 10:
            indicator = "✅ STRONG"
        elif score >= 5:
            indicator = "👍 MATCH"
        else:
            indicator = "📋 POSSIBLE"

        salary = parse_salary(job.get("salary", ""))
        lines.append(f"  #{i} [{indicator}] Score: {score}")
        lines.append(f"     {job.get('title', 'N/A')[:60]}")
        lines.append(f"     {job.get('company', 'N/A')} | {job.get('location', 'N/A')} | {salary}")
        if primary:
            lines.append(f"     Primary:  {', '.join(primary)}")
        if secondary:
            lines.append(f"     Secondary: {', '.join(secondary)}")
        if bonuses:
            lines.append(f"     Bonuses:  {', '.join(bonuses)}")
        lines.append(f"     🔗 {job.get('url', 'N/A')}")
        lines.append("")

    lines.append(f"{'='*70}")
    return "\n".join(lines)


class JobMatchFilter:
    """Wrapper class for scheduler compatibility."""
    def __init__(self, min_score=5, top=15, input=None, output=None, **kwargs):
        self.min_score = min_score
        self.top = top
        # Resolve relative paths against project root
        inp = input or str(OUTPUT_DIR / "job_postings.csv")
        out = output or str(OUTPUT_DIR / "matched_jobs.csv")
        if not os.path.isabs(inp):
            inp = str(ROOT / inp)
        if not os.path.isabs(out):
            out = str(ROOT / out)
        self.input = inp
        self.output = out

    async def run(self, **kwargs):
        main(min_score=self.min_score, top=self.top, input=self.input, output=self.output)
        return [{"source": "job_matches", "count": 0}]


def main(min_score=5, top=15, input=None, output=None, stack=None):
    input_path = input or str(OUTPUT_DIR / "job_postings.csv")
    output_path = output or str(OUTPUT_DIR / "matched_jobs.csv")

    jobs = load_jobs(input_path)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Job Match Filter")
    print(f"  Loaded {len(jobs)} jobs from {input_path}")

    custom_stack = None
    if stack:
        custom_stack = [s.strip().lower() for s in stack.split(",")]
        print(f"  Custom stack: {custom_stack}")
    else:
        all_skills = list(PRIMARY_SKILLS.keys()) + list(SECONDARY_SKILLS.keys())
        print(f"  Stack: {', '.join(all_skills)}")

    scored = []
    for job in jobs:
        score, primary, secondary, bonuses, negatives = score_job(job, custom_stack)
        if score >= min_score:
            scored.append({"job": job, "score": score, "primary": primary, "secondary": secondary, "bonuses": bonuses, "negatives": negatives})

    scored.sort(key=lambda x: x["score"], reverse=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rank", "score", "title", "company", "location", "salary", "url", "source", "primary_matches", "secondary_matches", "bonuses", "posted", "tags"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, m in enumerate(scored, 1):
            job = m["job"]
            writer.writerow({"rank": i, "score": m["score"], "title": job.get("title", ""), "company": job.get("company", ""), "location": job.get("location", ""), "salary": parse_salary(job.get("salary", "")), "url": job.get("url", ""), "source": job.get("source", ""), "primary_matches": ",".join(m["primary"]), "secondary_matches": ",".join(m["secondary"]), "bonuses": ",".join(m["bonuses"]), "posted": job.get("posted", ""), "tags": job.get("tags", "")})

    print(f"  Saved {len(scored)} matched jobs to {output_path}")

    report = format_report(scored, top)
    print(report)

    hot = sum(1 for m in scored if m["score"] >= 20)
    strong = sum(1 for m in scored if 10 <= m["score"] < 20)
    match = sum(1 for m in scored if 5 <= m["score"] < 10)
    print(f"  🔥 Hot (20+): {hot} | ✅ Strong (10-19): {strong} | 👍 Match (5-9): {match}")
    print("  Done.")


if __name__ == "__main__":
    main()
