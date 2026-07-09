#!/usr/bin/env python3
"""
Scrape freelance job boards (Upwork & Fastwork) via free httpx+BS4.
Deduplicates against existing pipeline.csv and auto-appends new leads.

Usage:
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py --platform upwork
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py --platform fastwork
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py --queries "next.js react" "python AI"
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py --dry-run
    python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_freelance_jobs.py --pages 3
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

# ── Bootstrap ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

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

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# ── Paths ──────────────────────────────────────────────────────────────
PIPELINE_CSV = PROJECT_ROOT / "domains" / "book-dev" / "book-scraping" / "data" / "pipeline.csv"

# ── Defaults ───────────────────────────────────────────────────────────
DEFAULT_UPWORK_QUERIES = [
    "next.js react typescript",
    "web scraping python",
    "openai chatgpt integration",
    "python AI agent",
    "react frontend developer",
]

FASTWORK_URL = (
    "https://jobboard.fastwork.co/jobs"
    "?order_by[]=inserted_at&order_directions[]=desc&page=1&page_size=20"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ── Value estimation (THB) ────────────────────────────────────────────
def estimate_value(title, notes):
    """Estimate lead value in THB based on rate/title signals."""
    text = f"{title} {notes}".lower()

    # Hourly rate signals (USD -> THB ~35x)
    hr_match = re.search(r"\$(\d+)-?\$?(\d+)?\s*/hr", text)
    if hr_match:
        hi = int(hr_match.group(2) or hr_match.group(1))
        return int(hi * 35 * 40)  # assume ~40hr engagement

    # Fixed price signals - only match explicit $Xk or $X,K patterns
    fixed_k_match = re.search(r"\$([\d,]+)\s*k\b", text)
    if fixed_k_match:
        k_val = int(fixed_k_match.group(1).replace(",", ""))
        return int(k_val * 1000 * 35)  # $K -> THB

    # Fixed price without k (e.g., $5,000)
    fixed_match = re.search(r"\$([\d,]+)\b", text)
    if fixed_match:
        val_str = fixed_match.group(1).replace(",", "")
        try:
            val = int(val_str)
            if val >= 100:  # reasonable fixed price
                return int(val * 35)  # USD -> THB
        except ValueError:
            pass

    # Seniority / AI signals
    if any(w in text for w in ["senior", "architect", "principal"]):
        return 150_000
    if any(w in text for w in ["ai", "rag", "llm", "openai", "agent"]):
        return 120_000
    if any(w in text for w in ["full-stack", "fullstack", "full stack"]):
        return 100_000
    return 80_000


# ── Free scraper helper ─────────────────────────────────────────────────
def free_scrape_url(url):
    """Scrape a URL via free httpx+BS4. Returns markdown-like content."""
    print(f"  -> Scraping: {url[:100]}...")
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Remove noise
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'header']):
            tag.decompose()
        # Find main content
        main = soup.find('main') or soup.find('article') or soup.find(id=re.compile(r'content|main', re.I)) or soup.body
        if not main:
            return resp.text[:10000]
        # Convert to markdown-like text
        for heading in main.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(heading.name[1])
            heading.string = f"\n{'#' * level} {heading.get_text(strip=True)}\n"
        for bold in main.find_all(['strong', 'b']):
            bold.string = f"**{bold.get_text(strip=True)}**"
        for link in main.find_all('a', href=True):
            link.string = f"[{link.get_text(strip=True)}]({link['href']})"
        text = main.get_text(separator='\n', strip=True)
        return text[:15000]
    except Exception as e:
        print(f"  X Scrape failed: {e}")
        return ""


# ── Upwork scraper ────────────────────────────────────────────────────
def scrape_upwork(queries, pages=1):
    """Scrape Upwork job listings for given search queries."""
    jobs = []
    for query in queries:
        for page in range(1, pages + 1):
            encoded_q = query.replace(" ", "+")
            url = (
                f"https://www.upwork.com/nx/search/jobs/"
                f"?q={encoded_q}&page={page}&per_page=10"
            )
            md = free_scrape_url(url)
            if not md:
                continue

            jobs.extend(parse_upwork_markdown(md, query))
            time.sleep(1)  # rate limit
    return jobs


# ── Upwork UI filter blocklist ─────────────────────────────────────────
UPWORK_UI_NOISE = {
    "experience level", "client history", "client location",
    "client time zones", "project length", "hours per week",
    "job duration", "jobs per page", "job type", "budget",
    "english level", "location", "category", "skills",
}

def parse_upwork_markdown(md, query):
    """Extract job entries from Upwork markdown content."""
    jobs = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Job titles often appear as bold links or headers
        title = None
        job_url = ""
        if re.match(r"^\*\*(.+)\*\*$", line):
            title = re.match(r"^\*\*(.+)\*\*$", line).group(1)
        elif re.match(r"^#{1,4}\s+(.+)", line):
            title = re.match(r"^#{1,4}\s+(.+)", line).group(1)
        elif re.match(r"^\[(.+)\]\(https://www\.upwork\.com/jobs/", line):
            m = re.match(r"^\[(.+)\]\((https://www\.upwork\.com/jobs/[^\)]+)\)", line)
            if m:
                title = m.group(1)
                job_url = m.group(2)
            else:
                title = re.match(r"^\[(.+)\]\(", line).group(1)

        # Clean markdown artifacts from title
        if title:
            # Strip trailing markdown link artifacts
            title = re.sub(r"\]\(https?://[^\)]*\)", "", title)
            title = title.strip().strip("[").strip().rstrip(":")
            # Unescape markdown chars
            title = title.replace("\\+", "+").replace("\\&", "&")
            # Fix merged words from highlight removal (e.g., AIAgent -> AI Agent)
            title = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", title)
            title = re.sub(r"([a-z])([A-Z][a-z])", r"\1 \2", title)
            # Skip Upwork UI filter labels
            if re.sub(r"[^a-z]", "", title.lower()) in {
                re.sub(r"[^a-z]", "", n) for n in UPWORK_UI_NOISE
            }:
                i += 1
                continue

        if title and len(title) > 10:
            # Gather surrounding context for rate/tech extraction
            context = " ".join(lines[max(0, i - 1):min(len(lines), i + 8)])

            # Try to find job URL in context if not already captured
            if not job_url:
                url_match = re.search(r"(https://www\.upwork\.com/jobs/[^\s\)\"]+)", context)
                if url_match:
                    job_url = url_match.group(1).rstrip(")")

            # Clean Upwork URL (remove HTML highlight artifacts from search)
            if job_url:
                job_url = re.sub(r"-?span-class-highlight-?", "-", job_url)
                job_url = re.sub(r"-span(?!-class)", "-", job_url)  # remaining -span fragments
                job_url = re.sub(r"--", "-", job_url)  # collapse double dashes

            # Extract rate
            rate = ""
            rate_match = re.search(r"\$[\d,]+-?\$?[\d,]*\s*/hr", context)
            if rate_match:
                rate = rate_match.group(0)
            else:
                fixed_match = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?", context)
                if fixed_match:
                    rate = fixed_match.group(0)

            # Extract tech keywords from context
            tech_patterns = [
                r"React(?:\.js)?", r"Next\.js", r"TypeScript", r"Python",
                r"Node\.js", r"OpenAI", r"AI", r"RAG", r"Django", r"Supabase",
                r"GraphQL", r"Tailwind", r"Vite", r"PostgreSQL", r"Vercel",
            ]
            tech_found = []
            for tp in tech_patterns:
                if re.search(tp, context, re.IGNORECASE):
                    tech_found.append(tp.replace("\\", ""))

            notes_parts = [f"Query: {query}"]
            if rate:
                notes_parts.insert(0, rate)
            if tech_found:
                notes_parts.append(", ".join(tech_found))
            if job_url:
                notes_parts.append(f"URL: {job_url}")

            jobs.append({
                "company": title,
                "value": estimate_value(title, " ".join(notes_parts)),
                "source": "scraping-upwork",
                "notes": "; ".join(notes_parts),
                "url": job_url,
            })

        i += 1

    return jobs


# ── Fastwork UI filter blocklist ───────────────────────────────────────
FASTWORK_UI_NOISE = {
    "ลักษณะการจ้าง", "หมวดหมู่", "งบประมาณ", "ทักษะที่ต้องการ",
    "ระยะเวลาทำงาน", "ตำแหน่งงาน", "ประเภทงาน",
}

# ── Fastwork scraper ──────────────────────────────────────────────────
def scrape_fastwork():
    """Scrape Fastwork job board listings."""
    jobs = []
    md = free_scrape_url(FASTWORK_URL)
    if not md:
        return jobs

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        title = None
        if re.match(r"^\*\*(.+)\*\*$", line):
            title = re.match(r"^\*\*(.+)\*\*$", line).group(1)
        elif re.match(r"^#{1,4}\s+(.+)", line):
            title = re.match(r"^#{1,4}\s+(.+)", line).group(1)
        elif re.match(r"^\[(.+)\]\(", line) and len(line) > 15:
            title = re.match(r"^\[(.+)\]\(", line).group(1)

        # Clean and filter Fastwork UI labels
        if title:
            title = title.strip()
            if title in FASTWORK_UI_NOISE:
                i += 1
                continue

        if title and len(title) > 5:
            context = " ".join(lines[max(0, i - 1):min(len(lines), i + 6)])

            # Try to find job URL in context
            job_url = ""
            url_match = re.search(r"(https://jobboard\.fastwork\.co/jobs/[^\s\)\"]+)", context)
            if url_match:
                job_url = url_match.group(1).rstrip(")")
            else:
                # Try relative link pattern [/jobs/slug]
                rel_match = re.search(r"\[(/jobs/[^\]]+)\]", context)
                if rel_match:
                    job_url = f"https://jobboard.fastwork.co{rel_match.group(1)}"

            # Extract Thai Baht price
            price = ""
            thb_match = re.search(r"฿([\d,]+)", context)
            if thb_match:
                price = thb_match.group(0)

            # Check if IT-related (basic filter)
            it_keywords = [
                "it", "software", "web", "app", "api", "ai", "data",
                "ระบบ", "เว็บไซต์", "แอป", "ไอที", "โปรแกรม", "พัฒนา",
                "database", "server", "cloud", "bot", "automation",
            ]
            is_it = any(kw in context.lower() for kw in it_keywords)

            if is_it:
                value = 0
                if thb_match:
                    value = int(thb_match.group(1).replace(",", ""))
                else:
                    value = 30_000

                notes_text = f"{price or 'Price TBD'}; {context[:120]}"
                if job_url:
                    notes_text += f"; URL: {job_url}"

                jobs.append({
                    "company": title,
                    "value": value,
                    "source": "scraping-fastwork",
                    "notes": notes_text,
                    "url": job_url,
                })

        i += 1

    return jobs


# ── PeoplePerHour scraper ────────────────────────────────────────────
def scrape_peopleperhour(queries):
    """Scrape PeoplePerHour job listings via free scraper."""
    jobs = []
    seen_titles = set()
    for query in queries[:3]:  # limit to 3 queries to avoid rate limits
        encoded_q = query.replace(" ", "+")
        url = f"https://www.peopleperhour.com/freelance-jobs/{encoded_q.split('+')[0]}"
        md = free_scrape_url(url)
        if not md:
            continue

        lines = md.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            title = None
            job_url = ""

            # Job titles as links or headers
            if re.match(r"^\[(.+)\]\(https://www\.peopleperhour\.com/freelance-jobs/[^\)]+\)", line):
                m = re.match(r"^\[(.+)\]\((https://www\.peopleperhour\.com/freelance-jobs/[^\)]+)\)", line)
                if m:
                    title = m.group(1)
                    job_url = m.group(2)
            elif re.match(r"^#{1,4}\s+(.+)", line):
                title = re.match(r"^#{1,4}\s+(.+)", line).group(1)
            elif re.match(r"^\*\*(.+)\*\*$", line):
                title = re.match(r"^\*\*(.+)\*\*$", line).group(1)

            if title and len(title) > 10 and title not in seen_titles:
                seen_titles.add(title)
                context = " ".join(lines[max(0, i - 1):min(len(lines), i + 6)])

                # Extract price
                price = ""
                gbp_match = re.search(r"\$(\d[\d,]*)", context)
                if gbp_match:
                    price = f"${gbp_match.group(1)}"

                # Extract tech
                tech_patterns = [
                    r"React", r"Next\.js", r"TypeScript", r"Python",
                    r"Node\.js", r"OpenAI", r"AI", r"Django", r"API",
                ]
                tech_found = [tp for tp in tech_patterns if re.search(tp, context, re.IGNORECASE)]

                notes_parts = [f"Query: {query}"]
                if price:
                    notes_parts.insert(0, price)
                if tech_found:
                    notes_parts.append(", ".join(tech_found))
                if job_url:
                    notes_parts.append(f"URL: {job_url}")

                jobs.append({
                    "company": title,
                    "value": estimate_value(title, " ".join(notes_parts)),
                    "source": "scraping-peopleperhour",
                    "notes": "; ".join(notes_parts),
                    "url": job_url,
                })

            i += 1
        time.sleep(1)
    return jobs


# ── Pipeline CSV helpers ──────────────────────────────────────────────
def load_existing_titles():
    """Load existing lead company/title from pipeline.csv for dedup."""
    titles = set()
    if not PIPELINE_CSV.exists():
        return titles
    with open(PIPELINE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("company", "").strip().lower()
            if company:
                titles.add(company)
    return titles


def get_next_lead_id():
    """Get the next sequential lead ID number."""
    if not PIPELINE_CSV.exists():
        return 1
    last_id = 0
    with open(PIPELINE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = row.get("lead_id", "")
            if lid.startswith("L"):
                try:
                    num = int(lid[1:])
                    if num > last_id:
                        last_id = num
                except ValueError:
                    pass
    return last_id + 1


def append_leads(leads):
    """Append new leads to pipeline.csv. Returns count of leads added."""
    existing = load_existing_titles()
    new_lead_num = get_next_lead_id()
    today = date.today().isoformat()
    added = 0

    # Ensure file exists with header
    if not PIPELINE_CSV.exists():
        PIPELINE_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(PIPELINE_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "lead_id", "company", "contact", "email", "status",
                "value", "source", "created_date", "next_action", "notes"
            ])

    rows_to_append = []
    for lead in leads:
        title_key = lead["company"].strip().lower()
        if title_key in existing:
            print(f"  (dup) Skipped: {lead['company'][:60]}")
            continue

        lead_id = f"L{new_lead_num:03d}"
        new_lead_num += 1
        existing.add(title_key)

        platform = "Upwork" if "upwork" in lead["source"] else "Fastwork" if "fastwork" in lead["source"] else "PeoplePerHour" if "peopleperhour" in lead["source"] else lead.get("source", "unknown")
        job_url = lead.get("url", "")
        if job_url:
            next_action = f"Apply: {job_url}"
        else:
            next_action = f"Apply on {platform}"

        rows_to_append.append([
            lead_id,
            lead["company"],
            "",  # contact
            "",  # email
            "lead",
            lead["value"],
            lead["source"],
            today,
            next_action,
            lead["notes"],
        ])
        added += 1

    if rows_to_append:
        with open(PIPELINE_CSV, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_append)

    return added


# ── Telegram Digest ───────────────────────────────────────────────────
def send_telegram_digest(jobs: list, new_count: int):
    """Send top freelance leads to Telegram.
    
    Uses TELEGRAM_TRADING_BOT_TOKEN + TELEGRAM_CHAT_ID.
    """
    bot_token = os.environ.get("TELEGRAM_TRADING_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("  Warning: Telegram credentials not set, skipping digest")
        return 0
    
    # Take top 5 jobs by value
    top_jobs = sorted(jobs, key=lambda x: x.get("value", 0), reverse=True)[:5]
    
    if not top_jobs:
        print("  No jobs for Telegram digest")
        return 0
    
    lines = [
        f"💼 <b>Freelance Leads Digest</b>",
        f"📊 New leads: {new_count} | Showing top {len(top_jobs)}",
        ""
    ]
    
    for j in top_jobs:
        title = j.get("company", "?")[:50]
        value = j.get("value", 0)
        source = j.get("source", "?")
        url = j.get("url", "")
        
        line = f"• <b>{title}</b>"
        if value:
            line += f" — ฿{value:,}"
        line += f" ({source})"
        if url:
            line += f"\n  {url}"
        lines.append(line)
    
    message = "\n".join(lines)
    
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"  Telegram digest sent: {len(top_jobs)} leads")
            return 1
        else:
            print(f"  Warning: Telegram send failed: {resp.status_code}")
            return 0
    except Exception as e:
        print(f"  Warning: Telegram error: {e}")
        return 0


# ── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Scrape freelance job boards (Upwork & Fastwork) -> pipeline.csv"
    )
    parser.add_argument(
        "--platform",
        choices=["upwork", "fastwork", "peopleperhour", "both"],
        default="both",
        help="Which platform to scrape (default: both)",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=None,
        help="Custom Upwork search queries (default: built-in list)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of pages to scrape per Upwork query (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be added without writing to CSV",
    )
    parser.add_argument(
        "--send-digest",
        action="store_true",
        help="Send top leads to Telegram digest",
    )
    args = parser.parse_args()

    queries = args.queries or DEFAULT_UPWORK_QUERIES
    all_jobs = []

    print(f"\n{'='*60}")
    print(f"  Freelance Job Scraper")
    print(f"  Platform: {args.platform}")
    print(f"  Pipeline: {PIPELINE_CSV}")
    print(f"{'='*60}\n")

    # ── Scrape ─────────────────────────────────────────────────────
    if args.platform in ("upwork", "both"):
        print(f"[Upwork] Scraping {len(queries)} queries x {args.pages} page(s)...")
        upwork_jobs = scrape_upwork(queries, args.pages)
        print(f"  Found {len(upwork_jobs)} Upwork jobs\n")
        all_jobs.extend(upwork_jobs)

    if args.platform in ("fastwork", "both"):
        print("[Fastwork] Scraping job board...")
        fastwork_jobs = scrape_fastwork()
        print(f"  Found {len(fastwork_jobs)} Fastwork jobs\n")
        all_jobs.extend(fastwork_jobs)

    if args.platform in ("peopleperhour", "both"):
        print("[PeoplePerHour] Scraping job listings...")
        pph_jobs = scrape_peopleperhour(queries)
        print(f"  Found {len(pph_jobs)} PeoplePerHour jobs\n")
        all_jobs.extend(pph_jobs)

    if not all_jobs:
        print("No jobs found. Try again later or check network connectivity.")
        return

    # ── Dedup & append ─────────────────────────────────────────────
    print(f"{'~'*60}")
    print(f"Total raw jobs: {len(all_jobs)}")

    if args.dry_run:
        existing = load_existing_titles()
        new_jobs = [
            j for j in all_jobs if j["company"].strip().lower() not in existing
        ]
        print(f"New (not in pipeline): {len(new_jobs)}")
        for j in new_jobs:
            url_str = f"  {j['url']}" if j.get('url') else ""
            print(f"  + {j['company'][:60]}  ({j['source']})  THB{j['value']:,}{url_str}")
        print(f"\n  [DRY RUN] No changes written to pipeline.csv")
    else:
        added = append_leads(all_jobs)
        print(f"  Appended {added} new leads to pipeline.csv")
        print(f"  Skipped {len(all_jobs) - added} duplicates")
        
        # Send Telegram digest
        if args.send_digest and added > 0:
            print(f"\n  Sending Telegram digest...")
            send_telegram_digest(all_jobs, added)

    print(f"{'~'*60}\n")


if __name__ == "__main__":
    main()
