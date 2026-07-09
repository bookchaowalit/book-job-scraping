#!/usr/bin/env python3
"""
Match scraped jobs against your skills and generate an apply-ready report.

Usage:
    python3 scripts/match_jobs.py
    python3 scripts/match_jobs.py --top 30
    python3 scripts/match_jobs.py --source himalayas --min-score 3
    python3 scripts/match_jobs.py --ai-match  # Use AI to analyze job fit
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
INPUT_CSV = DATA_DIR / "job_postings.csv"
OUTPUT_CSV = DATA_DIR / "matched_jobs.csv"
DESCRIPTION_CSV = DATA_DIR / "job_descriptions.csv"

FIRECRAWL_REMOVED = True  # No longer needed — using free httpx+BS4

# ── Your skills profile ──────────────────────────────────────────────────────
SKILLS = {
    # Core dev skills (weighted high)
    "python": 3, "react": 3, "next.js": 3, "typescript": 3,
    "node.js": 3, "fastapi": 3, "django": 3, "full-stack": 3,
    "javascript": 2, "api": 2, "rest": 2, "graphql": 2,
    # Frontend
    "vue": 2, "tailwind": 2, "css": 1, "html": 1, "redux": 2,
    # Backend / Infra
    "postgresql": 2, "mysql": 2, "redis": 2, "docker": 2,
    "aws": 2, "gcp": 1, "linux": 1, "git": 1,
    # AI / Data
    "ai": 2, "machine learning": 2, "llm": 2, "openai": 2,
    "data": 1, "analytics": 1,
    # General
    "remote": 1, "agile": 1, "scrum": 1,
}

# Target locations (you want: abroad or 100% remote)
PREFERRED_LOCATIONS = [
    "remote", "australia", "au", "nz", "new zealand", "usa", "united states",
    "japan", "tokyo", "singapore", "europe", "uk", "germany", "canada",
    "thailand", "bangkok",
]

# ── Relocation / Visa sponsorship signals ─────────────────────────────────────
RELOCATION_KEYWORDS = [
    "relocation", "relocate", "relocation assistance", "relocation support",
    "visa sponsorship", "visa support", "sponsorship", "work visa",
    "work permit", "immigration", "relocation package", "moving allowance",
    "sign-on bonus", "sign on bonus", "signing bonus",
    "relocation bonus", "relocation grant",
]
RELOCATION_BONUS = 5  # extra points for jobs mentioning relocation/visa

# ── Freelance platform bonus ──────────────────────────────────────────────────
FREELANCE_PLATFORMS = ["upwork", "fastwork", "fiverr", "toptal"]
FREELANCE_BONUS = 3  # extra points for freelance gigs (freelance-first revenue)

# Job title keywords that match your profile
TITLE_KEYWORDS = [
    "developer", "engineer", "fullstack", "full-stack", "full stack",
    "backend", "back-end", "frontend", "front-end", "python", "react",
    "next", "node", "typescript", "software", "web", "api",
    "data engineer", "devops", "ai", "ml",
    # Freelance-specific
    "freelance", "freelancer", "gig", "contract", "project",
    # Thai keywords
    "โปรแกรมเมอร์", "นักพัฒนา", "เว็บ", "ระบบ", "ไอที", "ซอฟต์แวร์",
    "fullstack developer", "senior developer", "lead developer",
]


def parse_salary_value(salary_str: str) -> int:
    """Extract numeric salary value from string (annualized)."""
    import re
    if not salary_str:
        return 0
    # Remove currency symbols and clean up
    clean = salary_str.replace('$', '').replace('฿', '').replace(',', '').strip()
    # Find all numbers
    nums = re.findall(r'[\d]+', clean)
    if not nums:
        return 0
    # Take the highest number
    try:
        val = max(int(n) for n in nums)
        # Detect if hourly/daily/monthly/annual
        lower = salary_str.lower()
        if 'hour' in lower or '/hr' in lower or 'hourly' in lower:
            val = val * 2080  # Annualize (40h * 52w)
        elif 'day' in lower or '/day' in lower or 'daily' in lower:
            val = val * 260  # Annualize (5d * 52w)
        elif 'month' in lower or '/mo' in lower or 'monthly' in lower:
            val = val * 12
        elif 'k' in lower or val < 1000:
            val = val * 1000  # Convert K to full amount
        return val
    except ValueError:
        return 0


def score_job(job: dict, description: str = "") -> tuple:
    """Score a job based on multiple factors. Returns (score, matched_skills, relocation)."""
    text = f"{job.get('title', '')} {job.get('tags', '')} {job.get('keyword', '')} {job.get('location', '')} {description}".lower()
    title = job.get('title', '').lower()
    score = 0
    matched = []
    
    # 1. Skill matching (base score)
    for skill, weight in SKILLS.items():
        if skill in text:
            score += weight
            matched.append(skill)
    
    # 2. Title keyword bonus (exact title matches are more relevant)
    title_bonus = 0
    for kw in TITLE_KEYWORDS:
        if kw in title:
            title_bonus += 2
    score += title_bonus
    
    # 3. Salary-based scoring (higher salary = higher score)
    salary_val = parse_salary_value(job.get('salary', ''))
    if salary_val > 0:
        if salary_val >= 150000:  # $150K+
            score += 5
        elif salary_val >= 100000:  # $100K+
            score += 3
        elif salary_val >= 70000:  # $70K+
            score += 2
        elif salary_val >= 50000:  # $50K+
            score += 1
    
    # 4. Location preference scoring
    location = job.get('location', '').lower()
    if 'remote' in location or location == '':
        score += 3  # Fully remote is preferred
    elif any(loc in location for loc in ['australia', 'au', 'nz', 'new zealand', 'usa', 'singapore', 'japan']):
        score += 2  # Target countries
    
    # 5. Relocation / visa sponsorship bonus
    relocation = False
    for kw in RELOCATION_KEYWORDS:
        if kw in text:
            score += RELOCATION_BONUS
            relocation = True
            break
    
    # 6. Freelance platform bonus (freelance-first revenue strategy)
    source = job.get('source', '').lower()
    tags = job.get('tags', '').lower()
    if any(platform in source.lower() for platform in FREELANCE_PLATFORMS) or 'freelance' in tags:
        score += FREELANCE_BONUS
    
    # 7. Recency bonus (jobs posted within last 7 days)
    posted = job.get('posted', '') or job.get('posted_date', '')
    if posted:
        from datetime import datetime, timedelta
        try:
            # Try to parse common date formats
            if 'ago' in posted.lower():
                if 'hour' in posted or 'minute' in posted or 'second' in posted:
                    score += 3  # Very recent
                elif 'day' in posted:
                    days = int(''.join(filter(str.isdigit, posted)) or 0)
                    if days <= 3:
                        score += 3
                    elif days <= 7:
                        score += 2
            elif 'today' in posted.lower() or 'yesterday' in posted.lower():
                score += 3
        except (ValueError, TypeError):
            pass
    
    return score, matched, relocation


# ── AI Resume Matching (via free scraper + OpenRouter AI) ─────────────────────
def ai_match_job(job_url: str) -> dict:
    """Use free scraper + OpenRouter AI to analyze job fit against resume.
    Returns dict with: fit_score (0-100), missing_skills, required_experience, notes."""
    try:
        import httpx
        from bs4 import BeautifulSoup
        # User's resume summary for AI comparison
        user_profile = """
        Full-stack developer with expertise in:
        - Frontend: React, Next.js, TypeScript, Vue, Tailwind CSS
        - Backend: Python, Node.js, FastAPI, Django, REST APIs, GraphQL
        - Database: PostgreSQL, MySQL, Redis
        - Cloud: AWS, GCP, Docker
        - AI/ML: OpenAI, LLMs, data analytics
        - Experience: Remote work, agile/scrum
        """

        # Step 1: Scrape job page with free httpx+BS4
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = httpx.get(job_url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()
        main = soup.find('main') or soup.find('article') or soup.find(id=re.compile(r'content|main|job', re.I))
        if main:
            job_text = main.get_text(separator='\n', strip=True)
        else:
            body = soup.find('body')
            job_text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)
        job_text = job_text[:3000]  # Limit for AI context

        if not job_text.strip():
            return {"fit_score": 0, "error": "No job content scraped"}

        # Step 2: Use OpenRouter AI to analyze fit
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not openrouter_key:
            # Fallback: simple keyword-based scoring
            return {"fit_score": 50, "notes": "No AI key — keyword-based estimate", "missing_skills": [], "key_requirements": []}

        prompt = f"""Analyze this job posting against the candidate profile.
Return JSON with: fit_score (0-100), missing_skills (list), required_experience (string), key_requirements (list), notes (string).

CANDIDATE PROFILE:
{user_profile}

JOB POSTING:
{job_text}

Return ONLY valid JSON."""

        ai_resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            },
            timeout=30,
        )
        ai_resp.raise_for_status()
        result_text = ai_resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from response
        json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
        if json_match:
            import json
            return json.loads(json_match.group())
        return {"fit_score": 0, "error": "Could not parse AI response"}
    except Exception as e:
        return {"fit_score": 0, "error": str(e)}


def is_relevant_title(title: str) -> bool:
    """Check if job title matches your profile."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in TITLE_KEYWORDS)


def is_preferred_location(location: str) -> bool:
    """Check if location is in your preferred list."""
    loc_lower = location.lower()
    return any(loc in loc_lower for loc in PREFERRED_LOCATIONS) or loc_lower == ""


def main():
    parser = argparse.ArgumentParser(description="Match jobs to your skills")
    parser.add_argument("--top", type=int, default=50, help="Show top N jobs")
    parser.add_argument("--min-score", type=int, default=2, help="Minimum score to include")
    parser.add_argument("--source", default="", help="Filter by source (comma-separated)")
    parser.add_argument("--location", default="", help="Filter by location keyword (comma-separated, e.g. 'remote,australia')")
    parser.add_argument("--min-salary", type=int, default=0, help="Minimum annual salary filter (e.g. 50000)")
    parser.add_argument("--ai-match", action="store_true", help="Use AI to analyze job fit (slower, uses OpenRouter)")
    parser.add_argument("--ai-limit", type=int, default=5, help="Limit AI analysis to top N jobs")
    parser.add_argument("--title-filter", action="store_true", default=True,
                        help="Filter by relevant job titles")
    args = parser.parse_args()

    if not INPUT_CSV.exists():
        print(f"ERROR: {INPUT_CSV} not found. Run scrape_job_postings.py first.")
        sys.exit(1)

    # Read jobs
    jobs = []
    with open(INPUT_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)

    print(f"Loaded {len(jobs)} jobs from {INPUT_CSV}")

    # Load job descriptions for richer scoring
    descriptions = {}
    if DESCRIPTION_CSV.exists():
        with open(DESCRIPTION_CSV, "r") as f:
            for row in csv.DictReader(f):
                url = row.get("url", "")
                desc = row.get("description", "")
                skills = row.get("skills", "")
                if url and (desc or skills):
                    descriptions[url] = f"{desc} {skills}"
        print(f"Loaded {len(descriptions)} job descriptions from {DESCRIPTION_CSV}")
    else:
        print(f"No descriptions found at {DESCRIPTION_CSV} (scoring with metadata only)")

    # Score and filter
    scored_jobs = []
    for job in jobs:
        url = job.get("url", "")
        desc_text = descriptions.get(url, "")
        score, matched, relocation = score_job(job, description=desc_text)
        if score < args.min_score:
            continue
        if args.title_filter and not is_relevant_title(job.get("title", "")):
            continue
        if not is_preferred_location(job.get("location", "")):
            continue
        # Location filter
        if args.location:
            loc_kw = [l.strip().lower() for l in args.location.split(",")]
            job_loc = job.get("location", "").lower()
            if not any(kw in job_loc for kw in loc_kw):
                continue
        # Salary filter
        if args.min_salary > 0:
            sal_val = parse_salary_value(job.get("salary", ""))
            if sal_val > 0 and sal_val < args.min_salary:
                continue
        job["_score"] = score
        job["_matched"] = ", ".join(matched)
        job["_relocation"] = "YES" if relocation else ""
        scored_jobs.append(job)

    # Sort by score descending
    scored_jobs.sort(key=lambda x: x["_score"], reverse=True)

    # Filter by source if specified
    if args.source:
        sources = [s.strip().lower() for s in args.source.split(",")]
        scored_jobs = [j for j in scored_jobs if j.get("source", "").lower() in sources]

    # AI matching for top jobs (optional, slower)
    if args.ai_match and scored_jobs:
        print(f"\n🤖 Running AI resume matching on top {args.ai_limit} jobs...")
        ai_count = 0
        for job in scored_jobs[:args.ai_limit]:
            url = job.get("url", "")
            if not url:
                continue
            print(f"  Analyzing: {job.get('title', '')[:40]}...")
            ai_result = ai_match_job(url)
            job["_ai_fit"] = ai_result.get("fit_score", 0)
            job["_ai_missing"] = ", ".join(ai_result.get("missing_skills", []))
            job["_ai_notes"] = ai_result.get("notes", "")[:100]
            ai_count += 1
            print(f"    AI fit: {job['_ai_fit']}% | Missing: {job['_ai_missing'] or 'none'}")
        print(f"  ✓ AI analysis complete ({ai_count} jobs)")
        # Re-sort by combined score (original + AI fit bonus)
        for job in scored_jobs[:args.ai_limit]:
            ai_fit = job.get("_ai_fit", 0)
            if ai_fit > 0:
                job["_score"] = job["_score"] + (ai_fit // 10)  # AI fit adds up to +10 points

    # Take top N
    top_jobs = scored_jobs[:args.top]

    # Save to CSV
    if top_jobs:
        fieldnames = ["title", "company", "location", "salary", "url", "source",
                      "keyword", "posted", "_score", "_matched", "_relocation"]
        # Add AI fields if AI matching was used
        if args.ai_match:
            fieldnames.extend(["_ai_fit", "_ai_missing", "_ai_notes"])
        with open(OUTPUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for job in top_jobs:
                writer.writerow(job)
        print(f"Saved {len(top_jobs)} matched jobs to {OUTPUT_CSV}")

    # Print report
    print(f"\n{'='*80}")
    print(f"  TOP {len(top_jobs)} MATCHED JOBS (from {len(jobs)} total)")
    print(f"{'='*80}")

    for i, job in enumerate(top_jobs, 1):
        score = job["_score"]
        stars = "★" * min(score // 2, 5) + ("☆" if score % 2 else "")
        reloc = " [RELOCATION/VISA]" if job.get("_relocation") else ""
        ai_fit_str = ""
        if job.get("_ai_fit"):
            ai_fit_str = f" [AI: {job['_ai_fit']}%]"
        print(f"\n  [{i:2d}] {stars} (score: {score}){reloc}{ai_fit_str}")
        print(f"      Title:    {job.get('title', '')[:60]}")
        print(f"      Company:  {job.get('company', '')[:40]}")
        print(f"      Location: {job.get('location', '')}")
        if job.get("salary"):
            print(f"      Salary:   {job['salary']}")
        print(f"      Source:   {job.get('source', '')}")
        print(f"      Skills:   {job['_matched']}")
        if job.get("_ai_missing"):
            print(f"      AI Missing: {job['_ai_missing']}")
        if job.get("_ai_notes"):
            print(f"      AI Notes: {job['_ai_notes'][:80]}")
        url = job.get("url", "")
        if url:
            print(f"      Apply:    {url[:80]}")

    # Summary by source
    print(f"\n{'='*80}")
    print(f"  SUMMARY BY SOURCE")
    print(f"{'='*80}")
    source_counts = {}
    for job in scored_jobs:
        src = job.get("source", "Unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"    {src:25s}: {count} jobs")

    print(f"\n  Total matched: {len(scored_jobs)} jobs (score >= {args.min_score})")
    print(f"  Showing top:   {len(top_jobs)} jobs")
    print(f"  Saved to:      {OUTPUT_CSV}")
    print(f"  Done.")


if __name__ == "__main__":
    main()
