#!/usr/bin/env python3
"""
Company Intelligence — Enrich matched jobs with employer information.

Uses free httpx+BS4 scraping to extract company information:
  - Company size, industry, tech stack
  - Funding stage, culture, benefits
  - Engineering team info, remote policy

Usage:
    python3 company_intel.py                     # Enrich top matched jobs
    python3 company_intel.py --top 30            # Enrich top 30
    python3 company_intel.py --min-score 10      # Lower score threshold
    python3 company_intel.py --dry-run           # Preview only
    python3 company_intel.py --send-telegram     # Notify via Telegram
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

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
COMPANY_INTEL_CSV = DATA_DIR / "company_intel.csv"
COMPANY_INTEL_LOG = DATA_DIR / "company_intel_log.json"

# ── API Keys ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Company domain extraction ────────────────────────────────────────────────
COMPANY_DOMAIN_MAP = {
    "google": "google.com",
    "meta": "meta.com",
    "facebook": "meta.com",
    "amazon": "amazon.com",
    "apple": "apple.com",
    "microsoft": "microsoft.com",
    "netflix": "netflix.com",
    "spotify": "spotify.com",
    "stripe": "stripe.com",
    "shopify": "shopify.com",
    "airbnb": "airbnb.com",
    "uber": "uber.com",
    "lyft": "lyft.com",
    "twitter": "twitter.com",
    "linkedin": "linkedin.com",
    "salesforce": "salesforce.com",
    "adobe": "adobe.com",
    "oracle": "oracle.com",
    "sap": "sap.com",
    "github": "github.com",
    "gitlab": "gitlab.com",
    "atlassian": "atlassian.com",
    "slack": "slack.com",
    "zoom": "zoom.us",
    "twilio": "twilio.com",
    "datadog": "datadog.com",
    "cloudflare": "cloudflare.com",
    "hashicorp": "hashicorp.com",
    "elastic": "elastic.co",
    "mongodb": "mongodb.com",
    "redis": "redis.com",
    "confluent": "confluent.io",
    "snowflake": "snowflake.com",
    "databricks": "databricks.com",
    "palantir": "palantir.com",
    "plaid": "plaid.com",
    "brex": "brex.com",
    "ramp": "ramp.com",
    "rippling": "rippling.com",
    "gusto": "gusto.com",
    "hubspot": "hubspot.com",
    "zendesk": "zendesk.com",
    "intercom": "intercom.com",
    "notion": "notion.so",
    "figma": "figma.com",
    "canva": "canva.com",
    "vercel": "vercel.com",
    "netlify": "netlify.com",
    "supabase": "supabase.com",
    "planetscale": "planetscale.com",
    "prisma": "prisma.io",
    "sentry": "sentry.io",
    "launchdarkly": "launchdarkly.com",
    "split": "split.io",
    "optimizely": "optimizely.com",
    "segment": "segment.com",
    "mixpanel": "mixpanel.com",
    "amplitude": "amplitude.com",
}


def get_candidate_jobs(min_score=8):
    """Get matched jobs above score threshold."""
    if not MATCHED_CSV.exists():
        print(f"[WARN] No matched_jobs.csv found at {MATCHED_CSV}")
        return []
    jobs = []
    with open(MATCHED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                score = float(row.get("_score", row.get("score", 0)))
            except (ValueError, TypeError):
                score = 0
            if score >= min_score:
                jobs.append(row)
    jobs.sort(key=lambda x: float(x.get("_score", x.get("score", 0))), reverse=True)
    print(f"[INFO] {len(jobs)} matched jobs with score >= {min_score}")
    return jobs


def get_already_enriched():
    """Get set of companies already enriched."""
    enriched = set()
    if COMPANY_INTEL_CSV.exists():
        with open(COMPANY_INTEL_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("company", "").lower().strip()
                if key:
                    enriched.add(key)
    if COMPANY_INTEL_LOG.exists():
        try:
            log = json.loads(COMPANY_INTEL_LOG.read_text())
            for entry in log.get("enriched", []):
                enriched.add(entry.get("company", "").lower().strip())
        except Exception:
            pass
    print(f"[INFO] {len(enriched)} companies already enriched")
    return enriched


def extract_company_domain(company_name):
    """Try to find company website domain from known map."""
    name_lower = company_name.lower().strip()
    # Direct match
    if name_lower in COMPANY_DOMAIN_MAP:
        return COMPANY_DOMAIN_MAP[name_lower]
    # Partial match
    for key, domain in COMPANY_DOMAIN_MAP.items():
        if key in name_lower or name_lower in key:
            return domain
    # Guess: company.com
    slug = re.sub(r"[^a-z0-9]", "", name_lower)
    if slug and len(slug) > 2:
        return f"{slug}.com"
    return None


def extract_company_from_job(job):
    """Extract company name from job row."""
    return job.get("company", "").strip()


def free_scrape_url(url):
    """Scrape a URL with free httpx+BS4 and return markdown-like content."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
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
        print(f"[WARN] Scrape error for {url}: {e}")
        return None


def extract_company_intel(markdown, company_name):
    """Extract structured company intelligence from scraped content."""
    intel = {
        "company": company_name,
        "description": "",
        "industry": "",
        "size": "",
        "funding": "",
        "tech_stack": "",
        "remote_policy": "",
        "culture": "",
        "benefits": "",
        "engineering_blog": "",
        "careers_page": "",
        "linkedin_url": "",
    }
    if not markdown:
        return intel

    text = markdown[:15000]  # Limit processing size
    lines = text.split("\n")

    # Description — first meaningful paragraph
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 80 and not stripped.startswith(("#", "[", "!", "```")):
            intel["description"] = stripped[:300]
            break

    # Industry keywords
    industry_keywords = {
        "fintech": ["fintech", "financial technology", "payments", "banking"],
        "saas": ["saas", "software as a service", "cloud platform"],
        "healthcare": ["healthcare", "health tech", "medical", "healthtech"],
        "ecommerce": ["ecommerce", "e-commerce", "online shopping", "marketplace"],
        "ai/ml": ["artificial intelligence", "machine learning", "deep learning", "ai platform"],
        "cybersecurity": ["cybersecurity", "security", "infosec", "zero trust"],
        "devtools": ["developer tools", "devtools", "developer platform"],
        "edtech": ["edtech", "education technology", "learning platform"],
        "proptech": ["proptech", "real estate technology"],
        "logistics": ["logistics", "supply chain", "freight"],
        "gaming": ["gaming", "game development", "game engine"],
        "social media": ["social media", "social network", "community platform"],
        "streaming": ["streaming", "video platform", "content delivery"],
        "insurance": ["insurtech", "insurance technology"],
        "crypto/web3": ["blockchain", "crypto", "web3", "defi"],
    }
    text_lower = text.lower()
    for industry, keywords in industry_keywords.items():
        if any(kw in text_lower for kw in keywords):
            intel["industry"] = industry
            break

    # Company size indicators
    size_patterns = [
        (r"(\d+)[\s,]*employees", "employees"),
        (r"team of (\d+)", "employees"),
        (r"(\d+)[\s,]*people", "people"),
        (r"over (\d+)", "over"),
        (r"more than (\d+)", "more_than"),
    ]
    for pattern, ptype in size_patterns:
        m = re.search(pattern, text_lower)
        if m:
            num = int(m.group(1))
            if num > 10000:
                intel["size"] = "10000+"
            elif num > 1000:
                intel["size"] = "1000-10000"
            elif num > 100:
                intel["size"] = "100-1000"
            elif num > 50:
                intel["size"] = "50-100"
            else:
                intel["size"] = f"<{max(num, 50)}"
            break

    # Funding
    funding_patterns = [
        r"(series [a-f])",
        r"(\$\d+[\d.]*\s*(?:million|billion|m|b))",
        r"(seed\s+(?:round|funding))",
        r"(ipo|public)",
        r"(pre-[a-z]+\s+round)",
    ]
    for pattern in funding_patterns:
        m = re.search(pattern, text_lower)
        if m:
            intel["funding"] = m.group(1).strip().title()
            break

    # Tech stack detection
    tech_keywords = [
        "python", "javascript", "typescript", "react", "vue", "angular", "next.js", "nextjs",
        "node.js", "nodejs", "django", "flask", "fastapi", "spring", "rails", "ruby",
        "golang", "go ", "rust", "kotlin", "swift", "java", "c++", "c#", ".net", "dotnet",
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "graphql", "rest api", "microservices", "serverless",
        "tensorflow", "pytorch", "openai", "llm",
    ]
    found_tech = []
    for tech in tech_keywords:
        if tech.strip() in text_lower:
            found_tech.append(tech.strip().title())
    if found_tech:
        intel["tech_stack"] = ", ".join(found_tech[:15])

    # Remote policy
    remote_patterns = [
        r"remote[\s-]*(?:first|friendly|culture)",
        r"work from anywhere",
        r"fully remote",
        r"100%\s*remote",
        r"remote\s*work",
        r"distributed\s*team",
        r"hybrid",
    ]
    for pattern in remote_patterns:
        if re.search(pattern, text_lower):
            if "fully" in pattern or "100%" in pattern or "anywhere" in pattern:
                intel["remote_policy"] = "Fully Remote"
            elif "hybrid" in pattern:
                intel["remote_policy"] = "Hybrid"
            else:
                intel["remote_policy"] = "Remote Friendly"
            break

    # Culture keywords
    culture_signals = []
    culture_map = {
        "fast-paced": ["fast-paced", "fast paced", "rapid growth"],
        "startup": ["startup", "start-up", "early-stage"],
        "enterprise": ["enterprise", "fortune 500", "large-scale"],
        "open-source": ["open source", "open-source", "oss"],
        "diversity": ["diversity", "inclusion", "dei", "equal opportunity"],
        "innovation": ["innovation", "innovative", "cutting-edge"],
        "autonomy": ["autonomy", "ownership", "self-directed"],
    }
    for culture, keywords in culture_map.items():
        if any(kw in text_lower for kw in keywords):
            culture_signals.append(culture.title())
    if culture_signals:
        intel["culture"] = ", ".join(culture_signals)

    # Benefits
    benefit_keywords = [
        "unlimited pto", "unlimited vacation", "401k", "health insurance",
        "stock options", "equity", "remote stipend", "learning budget",
        "parental leave", "wellness", "gym", "free food",
    ]
    found_benefits = []
    for b in benefit_keywords:
        if b in text_lower:
            found_benefits.append(b.title())
    if found_benefits:
        intel["benefits"] = ", ".join(found_benefits[:8])

    # LinkedIn
    linkedin_match = re.search(r"(https?://(?:www\.)?linkedin\.com/company/[^\s\)\"\']+)", text)
    if linkedin_match:
        intel["linkedin_url"] = linkedin_match.group(1)

    # Engineering blog
    eng_blog = re.search(r"(https?://[^\s]*engineering[^\s]*)", text)
    if eng_blog:
        intel["engineering_blog"] = eng_blog.group(1)

    # Careers page
    careers = re.search(r"(https?://[^\s]*(?:careers|jobs)[^\s]*)", text)
    if careers:
        intel["careers_page"] = careers.group(1)

    return intel


def save_intel_results(results):
    """Save company intel to CSV."""
    COMPANY_INTEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company", "description", "industry", "size", "funding",
        "tech_stack", "remote_policy", "culture", "benefits",
        "engineering_blog", "careers_page", "linkedin_url", "enriched_at",
    ]
    file_exists = COMPANY_INTEL_CSV.exists()
    with open(COMPANY_INTEL_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for r in results:
            writer.writerow(r)
    print(f"[OK] Saved {len(results)} company intel records to {COMPANY_INTEL_CSV}")


def log_enrichment(results):
    """Append to enrichment log."""
    log = {}
    if COMPANY_INTEL_LOG.exists():
        try:
            log = json.loads(COMPANY_INTEL_LOG.read_text())
        except Exception:
            log = {}
    if "enriched" not in log:
        log["enriched"] = []
    for r in results:
        log["enriched"].append({
            "company": r.get("company", ""),
            "industry": r.get("industry", ""),
            "size": r.get("size", ""),
            "enriched_at": r.get("enriched_at", ""),
        })
    log["last_run"] = datetime.now().isoformat()
    COMPANY_INTEL_LOG.write_text(json.dumps(log, indent=2))


def build_telegram_message(results, total_candidates):
    """Build Telegram summary message."""
    lines = [
        "<b>🏢 Company Intelligence Report</b>",
        f"Enriched: {len(results)} / {total_candidates} candidates",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    for r in results[:10]:
        company = r.get("company", "Unknown")
        industry = r.get("industry", "—")
        size = r.get("size", "—")
        remote = r.get("remote_policy", "—")
        tech = r.get("tech_stack", "—")
        funding = r.get("funding", "—")
        lines.append(f"<b>{company}</b>")
        parts = []
        if industry != "—":
            parts.append(f"Industry: {industry}")
        if size != "—":
            parts.append(f"Size: {size}")
        if remote != "—":
            parts.append(f"Remote: {remote}")
        if funding != "—":
            parts.append(f"Funding: {funding}")
        if tech != "—":
            parts.append(f"Tech: {tech[:80]}")
        lines.append(" | ".join(parts) if parts else "No data found")
        lines.append("")

    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3900] + "\n\n... (truncated)"
    return msg


def send_telegram(message):
    """Send message to Telegram."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print("[OK] Telegram notification sent")
        else:
            print(f"[WARN] Telegram returned {resp.status_code}")
    except Exception as e:
        print(f"[WARN] Telegram error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Company Intelligence Enrichment")
    parser.add_argument("--top", type=int, default=20, help="Max companies to enrich")
    parser.add_argument("--min-score", type=float, default=8, help="Minimum job score")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram summary")
    args = parser.parse_args()

    print("=" * 60)
    print("  Company Intelligence Enrichment")
    print("=" * 60)

    # Get candidate jobs
    jobs = get_candidate_jobs(args.min_score)
    if not jobs:
        print("[INFO] No candidate jobs found. Exiting.")
        return

    # Get already enriched companies
    enriched = get_already_enriched()

    # Extract unique companies
    companies = {}
    for job in jobs:
        company = extract_company_from_job(job)
        if company and company.lower() not in enriched:
            if company not in companies:
                companies[company] = job

    company_list = list(companies.items())[:args.top]
    print(f"[INFO] {len(company_list)} new companies to enrich")

    if not company_list:
        print("[INFO] All companies already enriched. Exiting.")
        return

    results = []
    for i, (company_name, job) in enumerate(company_list, 1):
        print(f"\n[{i}/{len(company_list)}] Enriching: {company_name}")

        domain = extract_company_domain(company_name)
        if not domain:
            print(f"  [SKIP] Cannot determine domain for {company_name}")
            continue

        url = f"https://{domain}"
        print(f"  Scraping: {url}")

        if args.dry_run:
            print(f"  [DRY-RUN] Would scrape {url}")
            results.append({
                "company": company_name,
                "description": f"[DRY-RUN] Would scrape {url}",
                "industry": "", "size": "", "funding": "",
                "tech_stack": "", "remote_policy": "", "culture": "",
                "benefits": "", "engineering_blog": "", "careers_page": "",
                "linkedin_url": "", "enriched_at": datetime.now().isoformat(),
            })
            continue

        # Scrape company website
        markdown = free_scrape_url(url)

        # Also try careers page
        if not markdown or len(markdown) < 200:
            careers_url = f"https://{domain}/careers"
            print(f"  Trying careers: {careers_url}")
            markdown = free_scrape_url(careers_url)

        # Also try about page
        if not markdown or len(markdown) < 200:
            about_url = f"https://{domain}/about"
            print(f"  Trying about: {about_url}")
            markdown = free_scrape_url(about_url)

        intel = extract_company_intel(markdown or "", company_name)
        intel["enriched_at"] = datetime.now().isoformat()
        results.append(intel)

        status = "OK" if intel.get("industry") or intel.get("tech_stack") else "MINIMAL"
        print(f"  [{status}] {intel.get('industry', '—')} | {intel.get('size', '—')} | {intel.get('remote_policy', '—')}")

    # Save results
    if results and not args.dry_run:
        save_intel_results(results)
        log_enrichment(results)
    elif args.dry_run:
        print(f"\n[DRY-RUN] Would save {len(results)} company intel records")

    # Telegram
    if args.send_telegram and results:
        msg = build_telegram_message(results, len(company_list))
        send_telegram(msg)

    print(f"\n[DONE] Enriched {len(results)} companies")


if __name__ == "__main__":
    main()
