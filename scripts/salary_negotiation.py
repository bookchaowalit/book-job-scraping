#!/usr/bin/env python3
"""
Salary Negotiation Data Playbook
Generates salary negotiation strategies from pipeline benchmark data.
"""

import os
import sys
import json
import csv
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR.parent.parent / ".env")
except:
    pass

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DATA_DIR = Path(os.getenv("PIPELINE_DATA_DIR", SCRIPT_DIR.parent / "data"))
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"
SALARY_BENCHMARKS_CSV = DATA_DIR / "salary_benchmarks.csv"
SALARY_PLAYBOOK_DIR = DATA_DIR / "salary_playbook"
SALARY_PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)


def load_salary_benchmarks():
    """Load salary benchmark data"""
    if not SALARY_BENCHMARKS_CSV.exists():
        print("⚠️  salary_benchmarks.csv not found")
        return []
    
    with open(SALARY_BENCHMARKS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_matched_jobs():
    """Load matched jobs"""
    if not MATCHED_JOBS_CSV.exists():
        print("⚠️  matched_jobs.csv not found")
        return []
    
    with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def analyze_salary_data(jobs, benchmarks):
    """Analyze salary data from jobs and benchmarks"""
    salaries = []
    
    # Extract from benchmarks
    for b in benchmarks:
        min_sal = float(b.get("min_salary", 0))
        max_sal = float(b.get("max_salary", 0))
        avg_sal = float(b.get("avg_salary", (min_sal + max_sal) / 2 if min_sal and max_sal else 0))
        
        if avg_sal > 0:
            salaries.append({
                "role": b.get("role", b.get("title", "Unknown")),
                "location": b.get("location", "Unknown"),
                "min": min_sal,
                "max": max_sal,
                "avg": avg_sal,
                "source": b.get("source", "benchmark"),
            })
    
    # Extract from jobs
    for job in jobs:
        salary_str = job.get("salary", "")
        if salary_str:
            # Parse salary ranges like "$80k-$120k" or "80000-120000"
            numbers = re.findall(r'\$?(\d+[kK]?)', salary_str)
            if len(numbers) >= 2:
                try:
                    min_val = int(numbers[0].replace('k', '000').replace('K', '000'))
                    max_val = int(numbers[1].replace('k', '000').replace('K', '000'))
                    avg_val = (min_val + max_val) / 2
                    
                    salaries.append({
                        "role": job.get("title", "Unknown"),
                        "company": job.get("company", "Unknown"),
                        "location": job.get("location", "Unknown"),
                        "min": min_val,
                        "max": max_val,
                        "avg": avg_val,
                        "source": "job_posting",
                    })
                except:
                    pass
    
    return salaries


def calculate_percentiles(salaries, role_filter=None):
    """Calculate salary percentiles"""
    if role_filter:
        filtered = [s for s in salaries if role_filter.lower() in s.get("role", "").lower()]
    else:
        filtered = salaries
    
    if not filtered:
        return None
    
    avgs = sorted([s["avg"] for s in filtered])
    n = len(avgs)
    
    return {
        "count": n,
        "min": avgs[0],
        "max": avgs[-1],
        "p25": avgs[int(n * 0.25)] if n >= 4 else avgs[0],
        "p50": avgs[int(n * 0.50)] if n >= 2 else avgs[0],
        "p75": avgs[int(n * 0.75)] if n >= 4 else avgs[-1],
        "p90": avgs[int(n * 0.90)] if n >= 10 else avgs[-1],
        "avg": sum(avgs) / n,
    }


def generate_negotiation_strategy(role, location, target_salary, benchmarks_data):
    """Generate negotiation strategy using AI"""
    if not OPENROUTER_API_KEY:
        return "⚠️ OPENROUTER_API_KEY not set — AI strategy unavailable"
    
    prompt = f"""Generate a salary negotiation strategy for:
- Role: {role}
- Location: {location}
- Target Salary: ${target_salary:,.0f}

Market data:
{json.dumps(benchmarks_data, indent=2)}

Provide:
1. Market Position Analysis (am I above/below/at market?)
2. Negotiation Leverage Points (3-5 specific arguments)
3. Counter-Offer Strategy (what to ask for, what to accept)
4. Benefits & Perks to Negotiate (if salary is fixed)
5. Script Templates (exact phrases to use in negotiation)
6. Red Flags to Watch For

Be specific, actionable, and data-driven. Under 600 words."""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ AI strategy failed: {e}"


def generate_playbook(role=None, location=None, target_salary=None):
    """Generate complete salary negotiation playbook"""
    print("💰 Generating Salary Negotiation Playbook...\n")
    
    # Load data
    benchmarks = load_salary_benchmarks()
    jobs = load_matched_jobs()
    
    print(f"📊 Loaded {len(benchmarks)} benchmarks, {len(jobs)} jobs")
    
    # Analyze salaries
    salaries = analyze_salary_data(jobs, benchmarks)
    print(f"💵 Found {len(salaries)} salary data points")
    
    if not salaries:
        print("⚠️  No salary data available. Run pipeline salary_benchmark step first.")
        return None
    
    # Calculate percentiles
    all_percentiles = calculate_percentiles(salaries)
    role_percentiles = calculate_percentiles(salaries, role) if role else None
    
    print(f"\n📈 Overall Salary Stats:")
    if all_percentiles:
        print(f"  Min: ${all_percentiles['min']:,.0f}")
        print(f"  P25: ${all_percentiles['p25']:,.0f}")
        print(f"  P50: ${all_percentiles['p50']:,.0f}")
        print(f"  P75: ${all_percentiles['p75']:,.0f}")
        print(f"  P90: ${all_percentiles['p90']:,.0f}")
        print(f"  Max: ${all_percentiles['max']:,.0f}")
        print(f"  Avg: ${all_percentiles['avg']:,.0f}")
    
    if role_percentiles:
        print(f"\n📈 {role} Salary Stats:")
        print(f"  Count: {role_percentiles['count']}")
        print(f"  P50: ${role_percentiles['p50']:,.0f}")
        print(f"  P75: ${role_percentiles['p75']:,.0f}")
        print(f"  P90: ${role_percentiles['p90']:,.0f}")
    
    # Generate strategy
    benchmarks_data = {
        "all_roles": all_percentiles,
        role: role_percentiles if role_percentiles else None,
        "sample_salaries": salaries[:10],
    }
    
    if target_salary:
        print(f"\n🎯 Generating negotiation strategy for ${target_salary:,.0f}...")
        strategy = generate_negotiation_strategy(role, location, target_salary, benchmarks_data)
    else:
        strategy = "No target salary specified. Use --target-salary to generate personalized strategy."
    
    # Build playbook
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    playbook_content = f"""# Salary Negotiation Playbook
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## Market Analysis

### Overall Salary Distribution
"""
    
    if all_percentiles:
        playbook_content += f"""
- **Minimum:** ${all_percentiles['min']:,.0f}
- **25th Percentile:** ${all_percentiles['p25']:,.0f}
- **Median (50th):** ${all_percentiles['p50']:,.0f}
- **75th Percentile:** ${all_percentiles['p75']:,.0f}
- **90th Percentile:** ${all_percentiles['p90']:,.0f}
- **Maximum:** ${all_percentiles['max']:,.0f}
- **Average:** ${all_percentiles['avg']:,.0f}
- **Sample Size:** {all_percentiles['count']} positions
"""
    
    if role_percentiles:
        playbook_content += f"""

### {role} Specific Data
- **Sample Size:** {role_percentiles['count']} positions
- **Median:** ${role_percentiles['p50']:,.0f}
- **75th Percentile:** ${role_percentiles['p75']:,.0f}
- **90th Percentile:** ${role_percentiles['p90']:,.0f}
"""
    
    playbook_content += f"""

---

## Negotiation Strategy

{strategy}

---

## Sample Salary Data

"""
    
    for i, sal in enumerate(salaries[:10], 1):
        playbook_content += f"{i}. **{sal['role']}** @ {sal.get('company', sal.get('location', 'N/A'))}\n"
        playbook_content += f"   ${sal['min']:,.0f} - ${sal['max']:,.0f} (avg: ${sal['avg']:,.0f})\n"
        playbook_content += f"   Source: {sal['source']}\n\n"
    
    playbook_content += f"""

---

## Key Takeaways

1. **Know Your Market:** Research shows median compensation for similar roles
2. **Anchor High:** Start negotiations above your target to leave room for compromise
3. **Total Compensation:** Consider benefits, equity, bonuses, and perks
4. **Practice:** Rehearse your negotiation script before the conversation
5. **Be Prepared to Walk Away:** Know your minimum acceptable offer

---

_Good luck with your negotiation! 💪_
"""
    
    # Save playbook
    playbook_file = SALARY_PLAYBOOK_DIR / f"salary_playbook_{timestamp}.md"
    with open(playbook_file, "w", encoding="utf-8") as f:
        f.write(playbook_content)
    
    print(f"\n✅ Playbook saved: {playbook_file}")
    
    # Save JSON
    playbook_json = {
        "generated": datetime.now().isoformat(),
        "role": role,
        "location": location,
        "target_salary": target_salary,
        "percentiles": {
            "all": all_percentiles,
            "role": role_percentiles,
        },
        "salaries": salaries,
        "strategy": strategy,
    }
    json_file = SALARY_PLAYBOOK_DIR / f"salary_playbook_{timestamp}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(playbook_json, f, indent=2)
    
    return playbook_content


def list_playbooks():
    """List existing playbooks"""
    playbooks = sorted(SALARY_PLAYBOOK_DIR.glob("salary_playbook_*.md"))
    if not playbooks:
        print("No playbooks found")
        return []
    
    print(f"\n📁 Found {len(playbooks)} playbook(s):\n")
    for f in playbooks:
        size = f.stat().st_size
        date = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {f.name} ({size:,} bytes, {date})")
    
    return playbooks


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Salary Negotiation Data Playbook")
    parser.add_argument("--role", help="Target role (e.g., 'Senior Developer')")
    parser.add_argument("--location", help="Target location (e.g., 'Remote', 'San Francisco')")
    parser.add_argument("--target-salary", type=float, help="Target salary in USD")
    parser.add_argument("--list", action="store_true", help="List existing playbooks")
    
    args = parser.parse_args()
    
    if args.list:
        list_playbooks()
    else:
        generate_playbook(
            role=args.role,
            location=args.location,
            target_salary=args.target_salary,
        )


if __name__ == "__main__":
    main()
