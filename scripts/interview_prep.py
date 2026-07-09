#!/usr/bin/env python3
"""
Interview Prep Automation
Generates company briefings and technical prep based on job descriptions and company intel.
"""

import os
import sys
import json
import csv
import re
from datetime import datetime
from pathlib import Path

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
COMPANY_INTEL_DIR = DATA_DIR / "company_intel"
INTERVIEW_PREP_DIR = DATA_DIR / "interview_prep"
INTERVIEW_PREP_DIR.mkdir(parents=True, exist_ok=True)


def load_job(job_id=None):
    """Load job from matched_jobs.csv"""
    if not MATCHED_JOBS_CSV.exists():
        print("❌ matched_jobs.csv not found")
        return None
    
    with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        jobs = list(reader)
    
    if job_id:
        for job in jobs:
            if job.get("id") == job_id or job.get("job_id") == job_id:
                return job
        print(f"❌ Job {job_id} not found")
        return None
    
    # Return highest score job
    jobs.sort(key=lambda x: float(x.get("_score", x.get("score", 0))), reverse=True)
    return jobs[0] if jobs else None


def load_company_intel(company_name):
    """Load company intel JSON"""
    intel_file = COMPANY_INTEL_DIR / f"{company_name.lower().replace(' ', '_')}.json"
    if intel_file.exists():
        with open(intel_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def extract_technical_skills(job_desc):
    """Extract technical skills from job description"""
    skills = []
    
    # Programming languages
    languages = ["python", "javascript", "typescript", "java", "go", "rust", "c++", "c#", "ruby", "php", "swift", "kotlin"]
    for lang in languages:
        if re.search(rf"\b{re.escape(lang)}\b", job_desc, re.IGNORECASE):
            skills.append(lang.capitalize())
    
    # Frameworks
    frameworks = ["react", "next.js", "vue", "angular", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring", "rails", "laravel"]
    for fw in frameworks:
        if re.search(rf"\b{re.escape(fw)}\b", job_desc, re.IGNORECASE):
            skills.append(fw.title().replace(".", ".js"))
    
    # Databases
    dbs = ["postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "firebase", "supabase"]
    for db in dbs:
        if re.search(rf"\b{re.escape(db)}\b", job_desc, re.IGNORECASE):
            skills.append(db.capitalize())
    
    # Cloud
    clouds = ["aws", "gcp", "azure", "vercel", "netlify", "cloudflare"]
    for cloud in clouds:
        if re.search(rf"\b{re.escape(cloud)}\b", job_desc, re.IGNORECASE):
            skills.append(cloud.upper())
    
    # Tools
    tools = ["docker", "kubernetes", "git", "ci/cd", "graphql", "rest api", "microservices"]
    for tool in tools:
        if re.search(rf"\b{re.escape(tool)}\b", job_desc, re.IGNORECASE):
            skills.append(tool.title())
    
    return list(set(skills))


def generate_company_briefing(company_name, intel_data=None):
    """Generate company briefing using AI"""
    if not OPENROUTER_API_KEY:
        return "⚠️ OPENROUTER_API_KEY not set — AI briefing unavailable"
    
    prompt = f"""Generate a concise company briefing for {company_name} for interview preparation.
Include:
1. Company Overview (1-2 sentences)
2. Core Business & Products
3. Tech Stack (if known)
4. Recent News/Achievements (2024-2025)
5. Company Culture & Values
6. Key Interview Topics (what they typically ask)

Keep it under 500 words. Focus on actionable insights for interview prep."""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
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
        return f"⚠️ AI briefing failed: {e}"


def generate_technical_prep(skills, job_title):
    """Generate technical interview prep using AI"""
    if not OPENROUTER_API_KEY:
        return "⚠️ OPENROUTER_API_KEY not set — AI prep unavailable"
    
    skills_str = ", ".join(skills)
    prompt = f"""Generate technical interview preparation for a {job_title} role focusing on: {skills_str}

Include:
1. Top 10 likely technical questions (with brief answer hints)
2. 3 coding challenges to practice (with problem descriptions)
3. System design questions (if senior role)
4. Behavioral questions specific to this tech stack
5. Questions to ask the interviewer

Keep it practical and actionable. Under 800 words."""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ AI prep failed: {e}"


def generate_interview_prep(job_id=None, output_format="markdown"):
    """Generate complete interview prep package"""
    print(f"📋 Generating interview prep...")
    
    # Load job
    job = load_job(job_id)
    if not job:
        return None
    
    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown")
    desc = job.get("description", "")
    
    print(f"🏢 Company: {company}")
    print(f"💼 Role: {title}")
    
    # Load company intel
    intel = load_company_intel(company)
    
    # Extract skills
    skills = extract_technical_skills(desc)
    print(f"🛠️  Skills: {', '.join(skills[:10])}")
    
    # Generate briefing
    print("\n📊 Generating company briefing...")
    briefing = generate_company_briefing(company, intel)
    
    # Generate technical prep
    print("🔧 Generating technical prep...")
    tech_prep = generate_technical_prep(skills, title)
    
    # Combine
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prep_content = f"""# Interview Prep: {title} @ {company}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## Company Briefing

{briefing}

---

## Technical Preparation

{tech_prep}

---

## Job Details

**Title:** {title}
**Company:** {company}
**Location:** {job.get("location", "N/A")}
**Score:** {job.get("_score", job.get("score", "N/A"))}

**Key Skills:** {', '.join(skills)}

---

## Application Link

{job.get("url", job.get("apply_url", "N/A"))}

---

_Good luck! 🚀_
"""
    
    # Save
    output_file = INTERVIEW_PREP_DIR / f"prep_{company.lower().replace(' ', '_')}_{timestamp}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prep_content)
    
    print(f"\n✅ Interview prep saved: {output_file}")
    
    # Also save JSON for programmatic access
    prep_json = {
        "company": company,
        "title": title,
        "skills": skills,
        "briefing": briefing,
        "tech_prep": tech_prep,
        "job_url": job.get("url", ""),
        "generated": datetime.now().isoformat(),
    }
    json_file = INTERVIEW_PREP_DIR / f"prep_{company.lower().replace(' ', '_')}_{timestamp}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(prep_json, f, indent=2)
    
    return prep_content


def list_prep_files():
    """List all generated prep files"""
    prep_files = sorted(INTERVIEW_PREP_DIR.glob("prep_*.md"))
    if not prep_files:
        print("No interview prep files found")
        return []
    
    print(f"\n📁 Found {len(prep_files)} prep file(s):\n")
    for f in prep_files:
        size = f.stat().st_size
        date = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {f.name} ({size:,} bytes, {date})")
    
    return prep_files


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Interview Prep Automation")
    parser.add_argument("--job-id", help="Specific job ID to prep for")
    parser.add_argument("--list", action="store_true", help="List existing prep files")
    parser.add_argument("--company", help="Generate briefing for specific company")
    
    args = parser.parse_args()
    
    if args.list:
        list_prep_files()
    elif args.company:
        print(f"📊 Generating briefing for {args.company}...")
        intel = load_company_intel(args.company)
        briefing = generate_company_briefing(args.company, intel)
        print("\n" + briefing)
    else:
        generate_interview_prep(args.job_id)


if __name__ == "__main__":
    main()
