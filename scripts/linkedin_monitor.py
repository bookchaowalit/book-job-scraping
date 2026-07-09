#!/usr/bin/env python3
"""
LinkedIn Activity Monitor
Monitors LinkedIn for HR posts, hiring signals, and company updates.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing beautifulsoup4...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR.parent.parent / ".env")
except:
    pass

FIRECRAWL_REMOVED = True  # No longer needed — using free httpx+BS4
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TRADING_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DATA_DIR = Path(os.getenv("PIPELINE_DATA_DIR", SCRIPT_DIR.parent / "data"))
LINKEDIN_MONITOR_DIR = DATA_DIR / "linkedin_monitor"
LINKEDIN_MONITOR_DIR.mkdir(parents=True, exist_ok=True)


def free_scrape_url(url):
    """Scrape URL using free httpx+BS4 (Firecrawl replacement)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Remove non-content elements
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()
        # Get main content
        main = soup.find('main') or soup.find('article') or soup.find(id=re.compile(r'content|main', re.I))
        if main:
            text = main.get_text(separator='\n', strip=True)
        else:
            body = soup.find('body')
            text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
    except Exception as e:
        print(f"⚠️  Scrape failed for {url}: {e}")
        return None


def search_linkedin_posts(query, limit=20):
    """Search LinkedIn posts via free httpx+BS4"""
    # LinkedIn public search
    search_url = f"https://www.linkedin.com/search/results/content/?keywords={query.replace(' ', '%20')}"
    
    print(f"🔍 Searching LinkedIn for: {query}")
    content = free_scrape_url(search_url)
    
    if not content:
        print("⚠️  No content retrieved")
        return []
    
    # Parse posts (simplified - LinkedIn structure varies)
    posts = []
    
    # Look for post patterns
    lines = content.split("\n")
    current_post = {}
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Detect post start (usually starts with name/title)
        if len(line) < 100 and not line.startswith("http"):
            if current_post and "content" in current_post:
                posts.append(current_post)
                if len(posts) >= limit:
                    break
            current_post = {"author": line, "date": ""}
        elif current_post and "content" not in current_post:
            current_post["content"] = line
        elif current_post and "content" in current_post:
            # Append to content
            current_post["content"] += " " + line
    
    if current_post and "content" in current_post:
        posts.append(current_post)
    
    print(f"✅ Found {len(posts)} posts")
    return posts


def analyze_post_for_hiring_signals(post):
    """Analyze post for hiring signals using AI"""
    if not OPENROUTER_API_KEY:
        return {"score": 0, "signals": []}
    
    content = post.get("content", "")
    
    prompt = f"""Analyze this LinkedIn post for hiring signals and job opportunities.
Rate the hiring signal strength (0-10) and extract key information.

Post content:
{content[:1000]}

Return JSON:
{{
  "score": 0-10,
  "signals": ["hiring", "job_opening", "team_growth", etc],
  "company": "company name if mentioned",
  "role": "job title if mentioned",
  "location": "location if mentioned",
  "summary": "brief summary"
}}"""

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
            },
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"]
        
        # Parse JSON from response
        import re
        json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"score": 0, "signals": []}
    except Exception as e:
        return {"score": 0, "signals": [], "error": str(e)}


def monitor_companies(company_list, days=7):
    """Monitor specific companies for LinkedIn activity"""
    print(f"📊 Monitoring {len(company_list)} companies...")
    
    results = []
    
    for company in company_list:
        print(f"\n🏢 Checking {company}...")
        
        # Search for company posts
        query = f'"{company}" (hiring OR jobs OR "we are hiring" OR "join our team" OR "open role")'
        posts = search_linkedin_posts(query, limit=10)
        
        company_results = {
            "company": company,
            "posts": [],
            "high_signal_posts": [],
            "checked": datetime.now().isoformat(),
        }
        
        for post in posts[:10]:
            analysis = analyze_post_for_hiring_signals(post)
            post_data = {**post, "analysis": analysis}
            company_results["posts"].append(post_data)
            
            if analysis.get("score", 0) >= 7:
                company_results["high_signal_posts"].append(post_data)
        
        results.append(company_results)
        print(f"  Found {len(posts)} posts, {len(company_results['high_signal_posts'])} high-signal")
    
    return results


def generate_daily_digest(monitor_results):
    """Generate daily digest of LinkedIn activity"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    digest = f"""# LinkedIn Activity Digest
Generated: {timestamp}

## Summary

"""
    
    total_posts = sum(len(r["posts"]) for r in monitor_results)
    total_high_signal = sum(len(r["high_signal_posts"]) for r in monitor_results)
    
    digest += f"- **Total Posts Monitored:** {total_posts}\n"
    digest += f"- **High-Signal Posts:** {total_high_signal}\n"
    digest += f"- **Companies Tracked:** {len(monitor_results)}\n\n"
    
    # High-signal posts
    if total_high_signal > 0:
        digest += "## 🔥 High-Signal Opportunities\n\n"
        
        for result in monitor_results:
            for post in result["high_signal_posts"]:
                analysis = post.get("analysis", {})
                digest += f"### {result['company']}\n"
                digest += f"- **Signal Score:** {analysis.get('score', 0)}/10\n"
                digest += f"- **Signals:** {', '.join(analysis.get('signals', []))}\n"
                if analysis.get("role"):
                    digest += f"- **Role:** {analysis['role']}\n"
                if analysis.get("location"):
                    digest += f"- **Location:** {analysis['location']}\n"
                digest += f"- **Summary:** {analysis.get('summary', 'N/A')}\n\n"
    
    # All companies
    digest += "## 📊 Company Activity\n\n"
    for result in monitor_results:
        digest += f"**{result['company']}**: {len(result['posts'])} posts, {len(result['high_signal_posts'])} high-signal\n"
    
    return digest


def send_telegram_alert(message):
    """Send alert via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram credentials not configured")
        return False
    
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️  Telegram alert failed: {e}")
        return False


def run_monitor(companies=None, keywords=None, notify=True):
    """Run LinkedIn monitor"""
    print("🔍 Starting LinkedIn Activity Monitor...\n")
    
    # Default companies to monitor
    if not companies:
        companies = [
            "Google", "Meta", "Amazon", "Microsoft", "Apple",
            "Netflix", "Stripe", "Airbnb", "Uber", "Spotify",
        ]
    
    # Default keywords
    if not keywords:
        keywords = [
            "hiring developer", "software engineer job", "full stack developer",
            "remote developer", "tech hiring",
        ]
    
    # Monitor companies
    results = monitor_companies(companies, days=7)
    
    # Generate digest
    digest = generate_daily_digest(results)
    
    # Save digest
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    digest_file = LINKEDIN_MONITOR_DIR / f"linkedin_digest_{timestamp}.md"
    with open(digest_file, "w", encoding="utf-8") as f:
        f.write(digest)
    
    print(f"\n✅ Digest saved: {digest_file}")
    
    # Save JSON
    json_file = LINKEDIN_MONITOR_DIR / f"linkedin_data_{timestamp}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    # Send Telegram alert
    if notify:
        high_signal_count = sum(len(r["high_signal_posts"]) for r in results)
        if high_signal_count > 0:
            alert_msg = f"🔥 LinkedIn Alert: {high_signal_count} high-signal hiring posts detected!\n\n"
            alert_msg += digest[:500]  # First 500 chars
            send_telegram_alert(alert_msg)
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LinkedIn Activity Monitor")
    parser.add_argument("--companies", help="Comma-separated company list")
    parser.add_argument("--keywords", help="Comma-separated keywords")
    parser.add_argument("--no-notify", action="store_true", help="Skip Telegram notifications")
    parser.add_argument("--list-digests", action="store_true", help="List existing digests")
    
    args = parser.parse_args()
    
    if args.list_digests:
        digests = sorted(LINKEDIN_MONITOR_DIR.glob("linkedin_digest_*.md"))
        if not digests:
            print("No digests found")
            return
        
        print(f"\n📁 Found {len(digests)} digest(s):\n")
        for f in digests:
            size = f.stat().st_size
            date = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {f.name} ({size:,} bytes, {date})")
        return
    
    companies = args.companies.split(",") if args.companies else None
    keywords = args.keywords.split(",") if args.keywords else None
    
    run_monitor(companies=companies, keywords=keywords, notify=not args.no_notify)


if __name__ == "__main__":
    main()
