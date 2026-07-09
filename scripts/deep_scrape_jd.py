#!/usr/bin/env python3
"""
Deep Scrape Job Descriptions — Enrich matched jobs with full JD text.

Reads matched_jobs.csv, scrapes full job description pages using free libraries
(httpx + BeautifulSoup), extracts structured data (requirements, benefits, tech
stack), and saves to job_descriptions_deep.csv.

Usage:
    python3 deep_scrape_jd.py                    # Deep-scrape top 20 matches
    python3 deep_scrape_jd.py --top 10           # Only top 10
    python3 deep_scrape_jd.py --min-score 50     # Minimum score filter
    python3 deep_scrape_jd.py --dry-run          # Preview only
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"

MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
DEEP_DESC_CSV = DATA_DIR / "job_descriptions_deep.csv"

# Free scraper headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def get_already_scraped() -> set:
    """Get URLs already deep-scraped."""
    rows = load_csv(DEEP_DESC_CSV)
    return {row.get("url", "").lower() for row in rows
            if row.get("status") == "success"}


def get_candidate_jobs(min_score: int = 0) -> list:
    """Get matched jobs sorted by score, excluding already-scraped."""
    matched = load_csv(MATCHED_CSV)
    if not matched:
        return []

    scraped = get_already_scraped()

    candidates = []
    for job in matched:
        url = job.get("url", "").lower()
        if url in scraped or not url:
            continue
        try:
            score = int(job.get("_score", job.get("score", 0)))
        except (ValueError, TypeError):
            score = 0
        if score < min_score:
            continue
        candidates.append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "score": score,
            "location": job.get("location", ""),
            "salary": job.get("salary", ""),
            "tags": job.get("tags", job.get("_matched", "")),
            "source": job.get("source", ""),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def extract_from_json_ld(soup: BeautifulSoup) -> str:
    """Extract job description from JSON-LD structured data."""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                desc = item.get('description', '')
                if desc and len(desc) > 100:
                    clean = re.sub(r'<[^>]+>', '\n', desc)
                    clean = re.sub(r'\n{2,}', '\n', clean).strip()
                    if len(clean) > 100:
                        return clean
        except (json.JSONDecodeError, TypeError):
            continue
    return ""


def extract_from_next_data(soup: BeautifulSoup) -> str:
    """Extract job description from Next.js __NEXT_DATA__."""
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return ""
    try:
        data = json.loads(next_data.string)
        props = data.get('props', {}).get('pageProps', {})
        for key in ['job', 'position', 'posting', 'jobPosting']:
            job = props.get(key, {})
            if job and isinstance(job, dict):
                desc = job.get('description', '')
                if desc:
                    clean = re.sub(r'<[^>]+>', '\n', desc)
                    clean = re.sub(r'\n{2,}', '\n', clean).strip()
                    if len(clean) > 100:
                        return clean
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def free_scrape(url: str) -> str:
    """Scrape a URL using free httpx + BeautifulSoup. Returns markdown-like text."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy 1: JSON-LD structured data (most reliable)
        text = extract_from_json_ld(soup)
        if text:
            return text

        # Strategy 2: Next.js __NEXT_DATA__
        text = extract_from_next_data(soup)
        if text:
            return text

        # Strategy 3: Job description containers
        import re as _re
        content_selectors = [
            {'class_': _re.compile(r'job[_-]?description', _re.I)},
            {'class_': _re.compile(r'job[_-]?detail', _re.I)},
            {'class_': _re.compile(r'job[_-]?content', _re.I)},
            {'class_': _re.compile(r'job[_-]?posting', _re.I)},
            {'class_': _re.compile(r'description', _re.I)},
            {'class_': _re.compile(r'content[_-]?body', _re.I)},
            {'id': _re.compile(r'job[_-]?description', _re.I)},
        ]
        for selector in content_selectors:
            el = soup.find(**selector)
            if el:
                t = el.get_text(separator='\n', strip=True)
                if len(t) > 100:
                    return t

        # Strategy 4: Semantic HTML tags
        for tag_name in ['article', 'main']:
            tag = soup.find(tag_name)
            if tag:
                t = tag.get_text(separator='\n', strip=True)
                if len(t) > 100:
                    return t

        # Strategy 5: Largest text block
        all_divs = soup.find_all('div')
        best_text = ""
        for div in all_divs:
            t = div.get_text(separator='\n', strip=True)
            if len(t) > len(best_text) and len(t) > 200:
                child_tags = div.find_all(['nav', 'header', 'footer', 'aside'])
                nav_len = sum(len(ct.get_text()) for ct in child_tags)
                if nav_len < len(t) * 0.3:
                    best_text = t
        if best_text:
            return best_text

        # Fallback: meta description
        meta = soup.find('meta', attrs={'name': _re.compile(r'description', _re.I)})
        if meta:
            return meta.get('content', '').strip()

        return ""
    except Exception as e:
        print(f"    Scrape failed: {e}")
        return ""


def extract_structured_data(markdown: str, job: dict) -> dict:
    """Extract structured info from raw JD markdown."""
    text = markdown.lower()

    # Extract tech stack
    tech_keywords = [
        "python", "javascript", "typescript", "react", "next.js", "node.js",
        "django", "fastapi", "flask", "express", "vue", "angular", "svelte",
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "graphql", "rest", "grpc", "microservices", "ci/cd", "git",
        "openai", "langchain", "llm", "rag", "machine learning",
        "tailwind", "redux", "webpack", "vite", "supabase", "firebase",
    ]
    tech_found = [t for t in tech_keywords if t in text]

    # Extract experience requirements
    import re
    exp_match = re.search(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?experience", text)
    min_experience = exp_match.group(1) if exp_match else ""

    # Extract salary if present
    salary_patterns = [
        r"\$([\d,]+)\s*-\s*\$([\d,]+)",
        r"salary[:\s]+\$?([\d,]+)\s*-\s*\$?([\d,]+)",
        r"([\d,]+)\s*-\s*([\d,]+)\s*(?:thb|baht|usd|year|yr)",
    ]
    salary_range = ""
    for pat in salary_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            salary_range = f"{m.group(1)} - {m.group(2)}"
            break

    # Extract key requirements (bullet points)
    requirements = []
    for line in markdown.split("\n"):
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            clean = line.lstrip("-*• ").strip()
            if len(clean) > 20 and len(clean) < 200:
                requirements.append(clean)
    requirements = requirements[:15]

    # Extract benefits
    benefits_keywords = ["benefit", "perks", "we offer", "what we provide"]
    benefits = []
    for kw in benefits_keywords:
        idx = text.find(kw)
        if idx >= 0:
            section = markdown[idx:idx+500]
            for line in section.split("\n"):
                line = line.strip()
                if line.startswith(("- ", "* ", "• ")):
                    benefits.append(line.lstrip("-*• ").strip())
            break
    benefits = benefits[:10]

    return {
        "tech_stack": ", ".join(tech_found),
        "min_experience": min_experience,
        "salary_range": salary_range,
        "requirements": " | ".join(requirements[:10]),
        "benefits": " | ".join(benefits[:5]),
        "jd_length": len(markdown),
    }


def save_descriptions(results: list):
    """Save deep-scraped descriptions to CSV."""
    fieldnames = [
        "url", "title", "company", "score", "source", "location",
        "tech_stack", "min_experience", "salary_range",
        "requirements", "benefits", "jd_length",
        "status", "scraped_at",
    ]
    DEEP_DESC_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    existing = load_csv(DEEP_DESC_CSV)
    existing_urls = {r.get("url", "").lower() for r in existing}

    # Add new, skip duplicates
    for r in results:
        if r["url"].lower() not in existing_urls:
            existing.append(r)
            existing_urls.add(r["url"].lower())

    with open(DEEP_DESC_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in existing:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Deep Scrape Job Descriptions (free scraper)")
    parser.add_argument("--top", type=int, default=20, help="Scrape top N jobs (default: 20)")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum match score")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--send-telegram", action="store_true", help="Notify when done")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  DEEP SCRAPE JOB DESCRIPTIONS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    candidates = get_candidate_jobs(min_score=args.min_score)
    print(f"  Found {len(candidates)} jobs to deep-scrape")

    if not candidates:
        print("  All matched jobs already scraped. Nothing to do!")
        return

    to_process = candidates[:args.top]

    if args.dry_run:
        print(f"\n  DRY RUN — Would scrape:")
        for job in to_process:
            print(f"    • [{job['score']}] {job['title'][:40]} @ {job['company'][:30]}")
            print(f"      {job['url'][:80]}")
        return

    # Scrape each job
    results = []
    success_count = 0
    for i, job in enumerate(to_process, 1):
        print(f"\n  [{i}/{len(to_process)}] {job['title'][:40]}...")
        markdown = free_scrape(job["url"])

        if markdown:
            structured = extract_structured_data(markdown, job)
            result = {
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "score": job["score"],
                "source": job["source"],
                "location": job["location"],
                "tech_stack": structured["tech_stack"],
                "min_experience": structured["min_experience"],
                "salary_range": structured["salary_range"],
                "requirements": structured["requirements"],
                "benefits": structured["benefits"],
                "jd_length": structured["jd_length"],
                "status": "success",
                "scraped_at": datetime.now().isoformat(),
            }
            success_count += 1
            print(f"    ✓ {structured['jd_length']:,} chars | Tech: {structured['tech_stack'][:60]}")
        else:
            result = {
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "score": job["score"],
                "source": job["source"],
                "location": job["location"],
                "status": "failed",
                "scraped_at": datetime.now().isoformat(),
            }
            print(f"    ✗ Failed to scrape")

        results.append(result)

    # Save
    save_descriptions(results)

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {success_count}/{len(results)} scraped successfully")
    print(f"  Saved to: {DEEP_DESC_CSV}")
    print(f"{'='*60}\n")

    if args.send_telegram and success_count > 0:
        from auto_apply import send_telegram  # reuse
        lines = [
            f"<b>🔍 DEEP SCRAPE COMPLETE</b>",
            f"<b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>",
            "",
            f"Scraped {success_count} job descriptions",
        ]
        for r in results[:5]:
            if r["status"] == "success":
                lines.append(f"  • <b>{r['title'][:40]}</b> — {r['tech_stack'][:50]}")
        send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
