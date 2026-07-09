#!/usr/bin/env python3
"""
Salary Benchmarking Aggregator - Analyzes salary data from job postings.
Shows market rates per role, skill, and location.

Usage:
    python3 salary_benchmark.py
    python3 salary_benchmark.py --role "Senior Python Developer"
    python3 salary_benchmark.py --skill python --skill react
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")


def parse_salary(salary_str: str) -> tuple:
    """Parse salary string and return (min, max, currency) tuple."""
    if not salary_str or salary_str.strip() == "":
        return None, None, None
    
    salary_str = salary_str.strip()
    
    # Detect currency
    currency = "USD"
    if "฿" in salary_str or "THB" in salary_str or "บาท" in salary_str:
        currency = "THB"
    elif "¥" in salary_str or "JPY" in salary_str or "円" in salary_str:
        currency = "JPY"
    elif "€" in salary_str or "EUR" in salary_str:
        currency = "EUR"
    elif "£" in salary_str or "GBP" in salary_str:
        currency = "GBP"
    elif "AUD" in salary_str or "A$" in salary_str:
        currency = "AUD"
    elif "NZD" in salary_str or "NZ$" in salary_str:
        currency = "NZD"
    elif "SGD" in salary_str or "S$" in salary_str:
        currency = "SGD"
    elif "$" in salary_str:
        currency = "USD"
    
    # Remove currency symbols and text
    clean = re.sub(r'[฿¥€£$A-Z\s]', '', salary_str)
    
    # Find numbers (with K/M suffix)
    numbers = re.findall(r'(\d+(?:\.\d+)?)[KkMm]?', clean)
    
    if not numbers:
        return None, None, None
    
    # Check for K/M suffix
    multipliers = re.findall(r'[KkMm]', salary_str)
    
    values = []
    for i, num in enumerate(numbers):
        val = float(num)
        if i < len(multipliers):
            if multipliers[i].upper() == 'K':
                val *= 1000
            elif multipliers[i].upper() == 'M':
                val *= 1000000
        values.append(val)
    
    if len(values) == 1:
        return values[0], values[0], currency
    elif len(values) >= 2:
        return min(values), max(values), currency
    
    return None, None, None


def analyze_salaries() -> dict:
    """Analyze salaries from all job postings."""
    if not JOB_POSTINGS_CSV.exists():
        print(f"ERROR: {JOB_POSTINGS_CSV} not found")
        return {}
    
    salary_data = []
    
    with open(JOB_POSTINGS_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            salary_str = row.get("salary", "")
            min_sal, max_sal, currency = parse_salary(salary_str)
            
            if min_sal is not None:
                salary_data.append({
                    "title": row.get("title", ""),
                    "company": row.get("company", ""),
                    "location": row.get("location", ""),
                    "source": row.get("source", ""),
                    "keyword": row.get("keyword", ""),
                    "salary_min": min_sal,
                    "salary_max": max_sal,
                    "salary_avg": (min_sal + max_sal) / 2,
                    "currency": currency,
                })
    
    return salary_data


def benchmark_by_role(salary_data: list) -> dict:
    """Benchmark salaries by job role/title."""
    role_salaries = defaultdict(list)
    
    for entry in salary_data:
        title = entry["title"].lower()
        
        # Categorize by seniority and role
        if "senior" in title:
            role = "Senior"
        elif "junior" in title or "entry" in title:
            role = "Junior"
        elif "lead" in title or "principal" in title:
            role = "Lead/Principal"
        elif "manager" in title or "director" in title:
            role = "Manager/Director"
        else:
            role = "Mid-level"
        
        # Add specific role
        if "python" in title:
            role += " Python Developer"
        elif "react" in title or "frontend" in title:
            role += " Frontend Developer"
        elif "backend" in title:
            role += " Backend Developer"
        elif "full" in title and "stack" in title:
            role += " Full-Stack Developer"
        elif "devops" in title:
            role += " DevOps Engineer"
        elif "data" in title:
            role += " Data Engineer"
        elif "ai" in title or "ml" in title or "machine learning" in title:
            role += " AI/ML Engineer"
        else:
            role += " Developer"
        
        role_salaries[role].append(entry["salary_avg"])
    
    # Calculate stats
    benchmarks = {}
    for role, salaries in role_salaries.items():
        if salaries:
            benchmarks[role] = {
                "count": len(salaries),
                "min": min(salaries),
                "max": max(salaries),
                "avg": sum(salaries) / len(salaries),
                "median": sorted(salaries)[len(salaries) // 2],
            }
    
    return benchmarks


def benchmark_by_skill(salary_data: list, target_skills: list = None) -> dict:
    """Benchmark salaries by required skills."""
    skill_salaries = defaultdict(list)
    
    skill_patterns = {
        "python": r'\bpython\b',
        "react": r'\breact\b',
        "typescript": r'\btypescript\b',
        "node.js": r'\bnode\.?js\b',
        "django": r'\bdjango\b',
        "fastapi": r'\bfastapi\b',
        "aws": r'\baws\b',
        "docker": r'\bdocker\b',
        "kubernetes": r'\bkubernetes\b',
        "ai/ml": r'\b(ai|machine learning|deep learning)\b',
        "postgresql": r'\bpostgresql\b',
        "mongodb": r'\bmongodb\b',
        "redis": r'\bredis\b',
        "graphql": r'\bgraphql\b',
    }
    
    for entry in salary_data:
        title_lower = entry["title"].lower()
        
        for skill, pattern in skill_patterns.items():
            if target_skills and skill not in target_skills:
                continue
            if re.search(pattern, title_lower):
                skill_salaries[skill].append(entry["salary_avg"])
    
    # Calculate stats
    benchmarks = {}
    for skill, salaries in skill_salaries.items():
        if salaries:
            benchmarks[skill] = {
                "count": len(salaries),
                "min": min(salaries),
                "max": max(salaries),
                "avg": sum(salaries) / len(salaries),
                "median": sorted(salaries)[len(salaries) // 2],
            }
    
    return benchmarks


def benchmark_by_location(salary_data: list) -> dict:
    """Benchmark salaries by location."""
    location_salaries = defaultdict(list)
    
    for entry in salary_data:
        location = entry["location"].lower()
        
        # Categorize location
        if "remote" in location:
            loc = "Remote"
        elif "bangkok" in location or "thailand" in location or "thai" in location:
            loc = "Bangkok, Thailand"
        elif "tokyo" in location or "japan" in location:
            loc = "Tokyo, Japan"
        elif "singapore" in location:
            loc = "Singapore"
        elif "sydney" in location or "melbourne" in location or "australia" in location:
            loc = "Australia"
        elif "auckland" in location or "new zealand" in location:
            loc = "New Zealand"
        elif "london" in location or "uk" in location:
            loc = "London, UK"
        elif "new york" in location or "san francisco" in location or "us" in location or "usa" in location:
            loc = "USA"
        else:
            loc = "Other"
        
        location_salaries[loc].append(entry["salary_avg"])
    
    # Calculate stats
    benchmarks = {}
    for loc, salaries in location_salaries.items():
        if salaries:
            benchmarks[loc] = {
                "count": len(salaries),
                "min": min(salaries),
                "max": max(salaries),
                "avg": sum(salaries) / len(salaries),
                "median": sorted(salaries)[len(salaries) // 2],
            }
    
    return benchmarks


def format_salary(amount: float, currency: str = "USD") -> str:
    """Format salary amount with currency."""
    symbols = {
        "USD": "$", "THB": "฿", "JPY": "¥", "EUR": "€",
        "GBP": "£", "AUD": "A$", "NZD": "NZ$", "SGD": "S$",
    }
    symbol = symbols.get(currency, "$")
    
    if amount >= 1000000:
        return f"{symbol}{amount/1000000:.1f}M"
    elif amount >= 1000:
        return f"{symbol}{amount/1000:.0f}K"
    else:
        return f"{symbol}{amount:.0f}"


def main():
    parser = argparse.ArgumentParser(description="Salary Benchmarking Aggregator")
    parser.add_argument("--role", default="", help="Benchmark specific role")
    parser.add_argument("--skill", action="append", help="Benchmark specific skill(s)")
    parser.add_argument("--currency", default="USD", help="Display currency (default: USD)")
    parser.add_argument("--send-telegram", action="store_true", help="Send report via Telegram")
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"  SALARY BENCHMARKING REPORT")
    print(f"{'='*80}\n")
    
    # Analyze salaries
    print("Analyzing salary data...")
    salary_data = analyze_salaries()
    
    if not salary_data:
        print("ERROR: No salary data found in job postings")
        print("  Tip: Run scrape_job_postings.py first to collect data")
        return
    
    print(f"  Found {len(salary_data)} jobs with salary information\n")
    
    # Overall stats
    all_salaries = [e["salary_avg"] for e in salary_data]
    overall_avg = sum(all_salaries) / len(all_salaries)
    overall_min = min(all_salaries)
    overall_max = max(all_salaries)
    
    print(f"{'='*80}")
    print(f"  OVERALL SALARY STATS")
    print(f"{'='*80}\n")
    print(f"  Jobs with salary data: {len(salary_data)}")
    print(f"  Average salary: {format_salary(overall_avg)}")
    print(f"  Min salary: {format_salary(overall_min)}")
    print(f"  Max salary: {format_salary(overall_max)}")
    print(f"  Median salary: {format_salary(sorted(all_salaries)[len(all_salaries)//2])}\n")
    
    # Benchmark by role
    if not args.skill:
        print(f"{'='*80}")
        print(f"  SALARY BY ROLE")
        print(f"{'='*80}\n")
        
        role_benchmarks = benchmark_by_role(salary_data)
        
        for role, stats in sorted(role_benchmarks.items(), key=lambda x: x[1]["avg"], reverse=True):
            if args.role and args.role.lower() not in role.lower():
                continue
            
            print(f"  {role}")
            print(f"    Count: {stats['count']} jobs")
            print(f"    Average: {format_salary(stats['avg'])}")
            print(f"    Range: {format_salary(stats['min'])} - {format_salary(stats['max'])}")
            print(f"    Median: {format_salary(stats['median'])}")
            print()
    
    # Benchmark by skill
    print(f"{'='*80}")
    print(f"  SALARY BY SKILL")
    print(f"{'='*80}\n")
    
    skill_benchmarks = benchmark_by_skill(salary_data, args.skill)
    
    for skill, stats in sorted(skill_benchmarks.items(), key=lambda x: x[1]["avg"], reverse=True):
        print(f"  {skill.upper()}")
        print(f"    Count: {stats['count']} jobs")
        print(f"    Average: {format_salary(stats['avg'])}")
        print(f"    Range: {format_salary(stats['min'])} - {format_salary(stats['max'])}")
        print(f"    Median: {format_salary(stats['median'])}")
        print()
    
    # Benchmark by location
    print(f"{'='*80}")
    print(f"  SALARY BY LOCATION")
    print(f"{'='*80}\n")
    
    location_benchmarks = benchmark_by_location(salary_data)
    
    for loc, stats in sorted(location_benchmarks.items(), key=lambda x: x[1]["avg"], reverse=True):
        print(f"  {loc}")
        print(f"    Count: {stats['count']} jobs")
        print(f"    Average: {format_salary(stats['avg'])}")
        print(f"    Range: {format_salary(stats['min'])} - {format_salary(stats['max'])}")
        print(f"    Median: {format_salary(stats['median'])}")
        print()
    
    # Your market value estimate
    print(f"{'='*80}")
    print(f"  YOUR ESTIMATED MARKET VALUE")
    print(f"{'='*80}\n")
    
    # Based on your skills (Python, React, TypeScript, etc.)
    your_skills = ["python", "react", "typescript", "node.js", "django", "fastapi"]
    matching_salaries = []
    
    for entry in salary_data:
        title_lower = entry["title"].lower()
        for skill in your_skills:
            if skill in title_lower:
                matching_salaries.append(entry["salary_avg"])
                break
    
    if matching_salaries:
        your_avg = sum(matching_salaries) / len(matching_salaries)
        your_min = min(matching_salaries)
        your_max = max(matching_salaries)
        
        print(f"  Based on your skills: {', '.join(your_skills)}")
        print(f"  Estimated range: {format_salary(your_min)} - {format_salary(your_max)}")
        print(f"  Estimated average: {format_salary(your_avg)}")
        print(f"  (Based on {len(matching_salaries)} matching jobs)\n")
    else:
        print(f"  Not enough data to estimate your market value")
        print(f"  Try collecting more job postings with salary data\n")
    
    print(f"{'='*80}")
    print(f"  TIPS")
    print(f"{'='*80}\n")
    print(f"  • Remote positions typically pay 10-20% more than local roles")
    print(f"  • Senior roles (5+ years) command 30-50% higher salaries")
    print(f"  • AI/ML skills add 15-25% premium to base salary")
    print(f"  • Negotiate based on market data, not your current salary")
    print(f"  • Consider total compensation: equity, benefits, remote work\n")

    # Send Telegram notification
    if args.send_telegram:
        send_telegram_salary_report(salary_data, role_benchmarks if not args.skill else {}, location_benchmarks)


def send_telegram_salary_report(salary_data: list, role_benchmarks: dict, location_benchmarks: dict):
    """Send salary benchmark report via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    all_salaries = [e["salary_avg"] for e in salary_data]
    overall_avg = sum(all_salaries) / len(all_salaries)
    overall_max = max(all_salaries)

    lines = [
        "💰 <b>SALARY BENCHMARK REPORT</b>",
        "",
        f"📊 Analyzed <b>{len(salary_data)}</b> jobs with salary data",
        "",
        f"💵 Average salary: <b>{format_salary(overall_avg)}</b>",
        f"📈 Max salary: <b>{format_salary(overall_max)}</b>",
        f"📉 Min salary: <b>{format_salary(min(all_salaries))}</b>",
        "",
    ]

    if role_benchmarks:
        lines.append("🏢 <b>TOP ROLES BY SALARY:</b>")
        sorted_roles = sorted(role_benchmarks.items(), key=lambda x: x[1]["avg"], reverse=True)[:5]
        for role, stats in sorted_roles:
            lines.append(f"  • {role}: {format_salary(stats['avg'])} avg ({stats['count']} jobs)")
        lines.append("")

    if location_benchmarks:
        lines.append("🌍 <b>BY LOCATION:</b>")
        sorted_locs = sorted(location_benchmarks.items(), key=lambda x: x[1]["avg"], reverse=True)[:5]
        for loc, stats in sorted_locs:
            lines.append(f"  • {loc}: {format_salary(stats['avg'])} avg ({stats['count']} jobs)")
        lines.append("")

    your_skills = ["python", "react", "typescript", "node.js", "django", "fastapi"]
    matching = []
    for entry in salary_data:
        title_lower = entry["title"].lower()
        for skill in your_skills:
            if skill in title_lower:
                matching.append(entry["salary_avg"])
                break

    if matching:
        your_avg = sum(matching) / len(matching)
        lines.append(f"🎯 <b>YOUR ESTIMATED VALUE:</b>")
        lines.append(f"  Average: <b>{format_salary(your_avg)}</b> ({len(matching)} matching jobs)")
        lines.append(f"  Range: {format_salary(min(matching))} - {format_salary(max(matching))}")
        lines.append("")

    lines.append("💡 AI/ML skills add 15-25% premium")

    message = "\n".join(lines)

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
        print("✓ Telegram salary report sent")
        return True
    except Exception as e:
        print(f"ERROR: Telegram send failed: {e}")
        return False


if __name__ == "__main__":
    main()
