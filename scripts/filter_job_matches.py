#!/usr/bin/env python3
"""
Auto-match job postings against personal tech stack.
Scores and ranks jobs from job_postings.csv by relevance to your skills.
Outputs a filtered, ranked report for immediate bidding.

Outputs:
    - scripts (book-job-scraping)/data/matched_jobs.csv (ranked matches)
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
    from .job_target_policy import HUMAN_VERIFICATION_FIELDS, PASS, REJECT, VERIFY, qualify_job
    from .job_role_relevance import contains_term, evidence_tags, is_relevant_role
except ImportError:  # Direct script execution keeps scripts/ on sys.path.
    from job_target_policy import HUMAN_VERIFICATION_FIELDS, PASS, REJECT, VERIFY, qualify_job
    from job_role_relevance import contains_term, evidence_tags, is_relevant_role

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[1]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data"

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


def score_job(job: dict, custom_stack: list = None, description: str = "") -> tuple:
    """
    Score a job against the tech stack.
    Returns (total_score, matched_primary, matched_secondary, bonuses, negatives).
    """
    # Build search text from all relevant fields
    title = normalize(job.get("title", ""))
    tags = normalize(evidence_tags(job))
    description_text = normalize(description or job.get("description", ""))
    search_text = f"{title} {tags} {description_text}"
    bonus_text = f"{search_text} {normalize(job.get('location', ''))} {normalize(job.get('employment_type', ''))}"

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
        for alias in [skill_name, *skill_info["aliases"]]:
            if contains_term(search_text, alias):
                matched_primary.append(skill_name)
                total_score += skill_info["weight"]
                break

    # Check secondary skills
    for skill_name, skill_info in secondary_skills.items():
        for alias in [skill_name, *skill_info["aliases"]]:
            if contains_term(search_text, alias):
                matched_secondary.append(skill_name)
                total_score += skill_info["weight"]
                break

    # Check bonuses
    for kw, bonus in BONUS_KEYWORDS.items():
        if contains_term(bonus_text, kw):
            bonuses.append(kw)
            total_score += bonus

    # Check negatives
    for kw, penalty in NEGATIVE_KEYWORDS.items():
        if contains_term(search_text, kw):
            negatives.append(kw)
            total_score += penalty  # penalty is negative

    if is_relevant_role(job):
        total_score += 3
        bonuses.append("target-role")

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
        qualification = job.get("qualification_status", VERIFY)
        employment_type = job.get("employment_type", "Unknown")

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
        lines.append(f"  #{i} [{indicator}] Score: {score} | {qualification} | {employment_type}")
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


def parse_statuses(value) -> set[str]:
    """Normalize scheduler/CLI status lists and reject unknown values."""
    if value is None:
        return {PASS, VERIFY}
    parts = value.split(",") if isinstance(value, str) else value
    statuses = {str(item).strip().upper() for item in parts if str(item).strip()}
    allowed = {PASS, VERIFY, REJECT}
    invalid = statuses - allowed
    if invalid:
        raise ValueError(f"Unsupported qualification statuses: {sorted(invalid)}")
    return statuses or {PASS, VERIFY}


def load_descriptions(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    description_path = Path(path)
    if not description_path.exists():
        return {}
    with description_path.open(encoding="utf-8") as handle:
        return {
            row.get("url", ""): row.get("description", "")
            for row in csv.DictReader(handle)
            if row.get("url") and row.get("description")
        }


class JobMatchFilter:
    """Wrapper class for scheduler compatibility."""
    def __init__(
        self,
        min_score=5,
        top=15,
        input=None,
        output=None,
        descriptions=None,
        supplemental_input=None,
        include_statuses=None,
        seed_tracker=False,
        seed_min_score=5,
        **kwargs,
    ):
        self.min_score = min_score
        self.top = top
        self.include_statuses = include_statuses
        self.seed_tracker = bool(seed_tracker)
        self.seed_min_score = int(seed_min_score)
        # Resolve relative paths against project root
        inp = input or str(OUTPUT_DIR / "job_postings.csv")
        out = output or str(OUTPUT_DIR / "matched_jobs.csv")
        desc = descriptions or str(OUTPUT_DIR / "job_descriptions.csv")
        if not os.path.isabs(inp):
            inp = str(ROOT / inp)
        if not os.path.isabs(out):
            out = str(ROOT / out)
        if not os.path.isabs(desc):
            desc = str(ROOT / desc)
        self.input = inp
        self.output = out
        self.descriptions = desc
        self.supplemental_input = supplemental_input

    async def run(self, **kwargs):
        count = main(
            min_score=self.min_score,
            top=self.top,
            input=self.input,
            output=self.output,
            descriptions=self.descriptions,
            supplemental_input=self.supplemental_input,
            include_statuses=self.include_statuses,
        )
        if self.seed_tracker:
            try:
                from .auto_seed_tracker import auto_seed
            except ImportError:
                from auto_seed_tracker import auto_seed

            auto_seed(
                min_score=self.seed_min_score,
                send_telegram_flag=False,
                dry_run=False,
            )
        return [{"source": "job_matches"} for _ in range(count)]


def main(
    min_score=5,
    top=15,
    input=None,
    output=None,
    descriptions=None,
    stack=None,
    include_statuses=None,
    supplemental_input=None,
):
    input_path = input or str(OUTPUT_DIR / "job_postings.csv")
    output_path = output or str(OUTPUT_DIR / "matched_jobs.csv")
    description_path = descriptions or str(OUTPUT_DIR / "job_descriptions.csv")

    jobs = load_jobs(input_path)
    if supplemental_input:
        extra = Path(supplemental_input)
        if not extra.is_absolute():
            extra = ROOT / extra
        if extra.exists():
            # Explicit source capture only; keep verified tracker data separate.
            jobs = list({row.get("url"): row for row in
                         [*jobs, *load_jobs(str(extra))] if row.get("url")}.values())
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Job Match Filter")
    print(f"  Loaded {len(jobs)} jobs from {input_path}")

    custom_stack = None
    if stack:
        custom_stack = [s.strip().lower() for s in stack.split(",")]
        print(f"  Custom stack: {custom_stack}")
    else:
        all_skills = list(PRIMARY_SKILLS.keys()) + list(SECONDARY_SKILLS.keys())
        print(f"  Stack: {', '.join(all_skills)}")

    included = parse_statuses(include_statuses)
    description_by_url = load_descriptions(description_path)
    print(f"  Enriched descriptions: {len(description_by_url)} cached URLs")
    scored = []
    relevant_count = 0
    qualification_counts = {PASS: 0, VERIFY: 0, REJECT: 0}
    for job in jobs:
        description = job.get("description") or description_by_url.get(job.get("url", ""), "")
        qualification = qualify_job(job, description=description)
        status = qualification["qualification_status"]
        qualification_counts[status] += 1
        if status not in included:
            continue
        qualified_job = {**job, **qualification, "description": description}
        role_evidence = {**qualified_job, "description": description or job.get("description", "")}
        if not is_relevant_role(role_evidence):
            continue
        relevant_count += 1
        score, primary, secondary, bonuses, negatives = score_job(
            qualified_job,
            custom_stack,
            description=description,
        )
        if score >= min_score:
            scored.append({"job": qualified_job, "score": score, "primary": primary, "secondary": secondary, "bonuses": bonuses, "negatives": negatives})

    status_order = {PASS: 0, VERIFY: 1, REJECT: 2}
    scored.sort(
        key=lambda item: (
            status_order.get(item["job"].get("qualification_status", VERIFY), 9),
            -item["score"],
        )
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "description",
        "search_lane",
        "visa_sponsorship",
        "score",
        "qualification_status",
        "policy_version",
        "employment_type",
        "work_arrangement",
        "thailand_eligibility",
        "concurrent_employment",
        "engagement_boundary",
        "application_readiness",
        "qualification_reasons",
        *HUMAN_VERIFICATION_FIELDS,
        "title",
        "company",
        "location",
        "salary",
        "url",
        "source",
        "keyword",
        "primary_matches",
        "secondary_matches",
        "bonuses",
        "posted",
        "tags",
        "scraped_at",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, m in enumerate(scored, 1):
            job = m["job"]
            writer.writerow({
                "rank": i,
                "description": job.get("description", ""),
                "search_lane": job.get("search_lane", "remote_contract"),
                "visa_sponsorship": job.get("visa_sponsorship", "VERIFY"),
                "score": m["score"],
                "qualification_status": job.get("qualification_status", ""),
                "policy_version": job.get("policy_version", ""),
                "employment_type": job.get("employment_type", ""),
                "work_arrangement": job.get("work_arrangement", ""),
                "thailand_eligibility": job.get("thailand_eligibility", ""),
                "concurrent_employment": job.get("concurrent_employment", ""),
                "engagement_boundary": job.get("engagement_boundary", ""),
                "application_readiness": job.get("application_readiness", ""),
                "qualification_reasons": job.get("qualification_reasons", ""),
                **{field: job.get(field, "") for field in HUMAN_VERIFICATION_FIELDS},
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "salary": parse_salary(job.get("salary", "")),
                "url": job.get("url", ""),
                "source": job.get("source", ""),
                "keyword": job.get("keyword", ""),
                "primary_matches": ",".join(m["primary"]),
                "secondary_matches": ",".join(m["secondary"]),
                "bonuses": ",".join(m["bonuses"]),
                "posted": job.get("posted", ""),
                "tags": job.get("tags", ""),
                "scraped_at": job.get("scraped_at", ""),
            })

    print(f"  Saved {len(scored)} matched jobs to {output_path}")

    report = format_report(scored, top)
    print(report)

    hot = sum(1 for m in scored if m["score"] >= 20)
    strong = sum(1 for m in scored if 10 <= m["score"] < 20)
    match = sum(1 for m in scored if 5 <= m["score"] < 10)
    print(f"  🔥 Hot (20+): {hot} | ✅ Strong (10-19): {strong} | 👍 Match (5-9): {match}")
    print(
        "  Raw qualification: "
        f"PASS={qualification_counts[PASS]} | "
        f"VERIFY={qualification_counts[VERIFY]} | "
        f"REJECT={qualification_counts[REJECT]}"
    )
    matched_status_counts = {
        status: sum(1 for item in scored if item["job"].get("qualification_status") == status)
        for status in (PASS, VERIFY)
    }
    print(
        "  Matched output: "
        f"PASS={matched_status_counts[PASS]} | VERIFY={matched_status_counts[VERIFY]}"
    )
    print(f"  Role relevance: {relevant_count} PASS/VERIFY technical or commercial-tech listings")
    print("  Done.")
    return len(scored)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score and qualify contract-first job matches")
    parser.add_argument("--min-score", type=int, default=5)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--input", default=str(OUTPUT_DIR / "job_postings.csv"))
    parser.add_argument("--output", default=str(OUTPUT_DIR / "matched_jobs.csv"))
    parser.add_argument("--descriptions", default=str(OUTPUT_DIR / "job_descriptions.csv"))
    parser.add_argument("--stack", default=None)
    parser.add_argument("--supplemental-input", default=None)
    parser.add_argument("--include-statuses", default=f"{PASS},{VERIFY}")
    args = parser.parse_args()
    main(
        min_score=args.min_score,
        top=args.top,
        input=args.input,
        output=args.output,
        descriptions=args.descriptions,
        stack=args.stack,
        supplemental_input=args.supplemental_input,
        include_statuses=args.include_statuses,
    )
