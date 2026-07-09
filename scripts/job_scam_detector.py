#!/usr/bin/env python3
"""
Job Scam Detector
AI-powered scam detection — flags suspicious jobs based on patterns, salary anomalies, and known scam indicators.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_DIR = DATA_DIR / "scam_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# AI setup
try:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1"
    )
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False

# Scam patterns
SCAM_PATTERNS = {
    "salary_too_high": {
        "description": "Salary significantly above market rate",
        "severity": "high",
        "check": lambda job: _check_salary_too_high(job),
    },
    "vague_description": {
        "description": "Job description is too vague or generic",
        "severity": "medium",
        "check": lambda job: _check_vague_description(job),
    },
    "no_company_info": {
        "description": "Missing company information",
        "severity": "medium",
        "check": lambda job: not job.get("company") or len(job.get("company", "")) < 2,
    },
    "generic_email": {
        "description": "Contact uses generic email (gmail, yahoo, etc.)",
        "severity": "high",
        "check": lambda job: _check_generic_email(job),
    },
    "urgency_language": {
        "description": "Uses urgency/hiring immediately language",
        "severity": "medium",
        "check": lambda job: _check_urgency(job),
    },
    "no_experience_required": {
        "description": "High salary with no experience required",
        "severity": "high",
        "check": lambda job: _check_no_exp_high_salary(job),
    },
    "suspicious_keywords": {
        "description": "Contains suspicious keywords",
        "severity": "high",
        "check": lambda job: _check_suspicious_keywords(job),
    },
    "copy_paste_description": {
        "description": "Description looks copy-pasted or templated",
        "severity": "medium",
        "check": lambda job: _check_copy_paste(job),
    },
    "crypto_payment_only": {
        "description": "Only accepts cryptocurrency payment",
        "severity": "critical",
        "check": lambda job: _check_crypto_only(job),
    },
    "upfront_payment": {
        "description": "Requests upfront payment or deposit",
        "severity": "critical",
        "check": lambda job: _check_upfront_payment(job),
    },
    "too_good_benefits": {
        "description": "Unrealistic benefits package",
        "severity": "medium",
        "check": lambda job: _check_too_good_benefits(job),
    },
    "suspicious_url": {
        "description": "URL doesn't match company domain",
        "severity": "high",
        "check": lambda job: _check_suspicious_url(job),
    },
}

# Known scam companies (placeholder — expand as found)
KNOWN_SCAM_COMPANIES = set()

# Suspicious keywords
SUSPICIOUS_KEYWORDS = [
    "nigerian prince", "wire transfer", "western union", "bitcoin only",
    "crypto payment", "guaranteed income", "no interview", "instant hire",
    "work from home earn", "make money fast", "unlimited income",
    "pyramid", "mlm", "multi-level", "downline",
    "pay for training", "buy starter kit", "investment required",
    "data entry no experience $5000", "typing job no experience",
]

# Generic email domains
GENERIC_EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "protonmail.com", "mail.com", "yandex.com",
]


def _parse_salary_num(salary_str):
    """Parse salary to number."""
    if not salary_str:
        return 0
    salary_str = str(salary_str).replace(",", "").replace("$", "").lower()
    match = re.search(r'(\d+)', salary_str)
    if match:
        val = int(match.group(1))
        if "k" in salary_str or val < 10000:
            val *= 1000
        return val
    return 0


def _check_salary_too_high(job):
    """Check if salary is suspiciously high."""
    salary = _parse_salary_num(job.get("salary_min", "") or job.get("salary", ""))
    title = job.get("title", "").lower()
    if salary > 300000:  # >$300K
        if "senior" not in title and "lead" not in title and "staff" not in title and "director" not in title:
            return True
    if salary > 500000:  # >$500K for any role
        return True
    return False


def _check_vague_description(job):
    """Check if description is too vague."""
    desc = job.get("description", "")
    if not desc:
        return True
    if len(desc) < 50:
        return True
    # Count unique words
    words = set(re.findall(r'\w+', desc.lower()))
    if len(words) < 20:
        return True
    return False


def _check_generic_email(job):
    """Check if contact email is generic."""
    email = job.get("contact_email", job.get("email", "")).lower()
    if not email:
        return False
    for domain in GENERIC_EMAIL_DOMAINS:
        if f"@{domain}" in email:
            return True
    return False


def _check_urgency(job):
    """Check for urgency language."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    urgency_phrases = [
        "hiring immediately", "start today", "urgent need",
        "apply now or miss out", "limited positions", "last chance",
        "don't miss this opportunity", "act now",
    ]
    return any(phrase in text for phrase in urgency_phrases)


def _check_no_exp_high_salary(job):
    """Check for high salary with no experience required."""
    salary = _parse_salary_num(job.get("salary_min", "") or job.get("salary", ""))
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    no_exp = any(p in text for p in ["no experience", "entry level", "fresh graduate", "no prior"])
    return no_exp and salary > 100000


def _check_suspicious_keywords(job):
    """Check for suspicious keywords."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(kw in text for kw in SUSPICIOUS_KEYWORDS)


def _check_copy_paste(job):
    """Check for copy-pasted description patterns."""
    desc = job.get("description", "")
    if not desc:
        return False
    # Check for excessive repetition
    sentences = re.split(r'[.!?]+', desc)
    if len(sentences) > 3:
        unique = set(s.strip().lower() for s in sentences if s.strip())
        if len(unique) < len(sentences) * 0.5:
            return True
    return False


def _check_crypto_only(job):
    """Check if only crypto payment."""
    text = f"{job.get('description', '')} {job.get('salary_min', '')}".lower()
    crypto = any(kw in text for kw in ["bitcoin", "ethereum", "crypto", "usdt", "btc"])
    fiat = any(kw in text for kw in ["usd", "thb", "bank transfer", "salary", "monthly"])
    return crypto and not fiat


def _check_upfront_payment(job):
    """Check for upfront payment requests."""
    text = f"{job.get('description', '')} {job.get('title', '')}".lower()
    return any(kw in text for kw in [
        "pay for training", "buy starter kit", "registration fee",
        "deposit required", "investment needed", "purchase package",
    ])


def _check_too_good_benefits(job):
    """Check for unrealistic benefits."""
    desc = job.get("description", "").lower()
    too_good = [
        "unlimited vacation", "unlimited pto", "unlimited bonus",
        "free housing", "company car", "stock options guaranteed",
        "guaranteed promotion", "work 2 hours",
    ]
    count = sum(1 for p in too_good if p in desc)
    return count >= 3


def _check_suspicious_url(job):
    """Check if URL doesn't match company."""
    url = job.get("url", job.get("job_url", "")).lower()
    company = job.get("company", "").lower()
    if not url or not company:
        return False
    # Check if company name appears in URL domain
    url_domain = re.search(r'https?://([^/]+)', url)
    if url_domain:
        domain = url_domain.group(1)
        if company.split()[0] not in domain and domain not in company:
            # Check if it's a known job board (not suspicious)
            known_boards = ["linkedin", "indeed", "glassdoor", "stackoverflow", "github", "wellfound"]
            if not any(b in domain for b in known_boards):
                return True
    return False


def analyze_job(job):
    """Run all scam checks on a job."""
    flags = []
    risk_score = 0

    for check_name, check_info in SCAM_PATTERNS.items():
        try:
            result = check_info["check"](job)
            if result:
                severity = check_info["severity"]
                score_map = {"low": 10, "medium": 25, "high": 40, "critical": 60}
                risk_score += score_map.get(severity, 15)
                flags.append({
                    "check": check_name,
                    "description": check_info["description"],
                    "severity": severity,
                })
        except Exception:
            pass

    # Known scam company
    company = job.get("company", "")
    if company in KNOWN_SCAM_COMPANIES:
        risk_score += 50
        flags.append({
            "check": "known_scam_company",
            "description": f"Company '{company}' is a known scam",
            "severity": "critical",
        })

    # Determine overall risk
    if risk_score >= 60:
        risk_level = "CRITICAL"
    elif risk_score >= 40:
        risk_level = "HIGH"
    elif risk_score >= 20:
        risk_level = "MEDIUM"
    elif risk_score > 0:
        risk_level = "LOW"
    else:
        risk_level = "CLEAN"

    return {
        "job_id": job.get("id", job.get("job_id", "unknown")),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "risk_score": min(risk_score, 100),
        "risk_level": risk_level,
        "flags": flags,
        "flag_count": len(flags),
    }


def ai_analyze_job(job):
    """Use AI to assess if job is suspicious."""
    if not AI_AVAILABLE:
        return None

    prompt = f"""Analyze this job posting for potential scam indicators:

Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Salary: {job.get('salary_min', 'N/A')} - {job.get('salary_max', 'N/A')}
Description: {job.get('description', 'N/A')[:500]}
URL: {job.get('url', 'N/A')}

Rate the legitimacy on a scale of 1-10 (10 = definitely legit, 1 = definitely scam).
List specific red flags if any.
Respond in JSON: {{"legitimacy_score": N, "red_flags": ["..."], "verdict": "legit/suspicious/scam"}}"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        # Try to parse JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️  AI analysis error: {e}")

    return None


def scan_all_jobs(limit=500):
    """Scan all jobs for scams."""
    jobs = []
    for fname in ["matched_jobs.csv", "job_postings.csv"]:
        csv_path = DATA_DIR / fname
        if not csv_path.exists():
            continue
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    jobs.append(row)
        except Exception:
            pass

    print(f"\n🔍 Scanning {len(jobs)} jobs for scam indicators...")
    results = []
    flagged = []

    for job in jobs:
        result = analyze_job(job)
        results.append(result)
        if result["risk_level"] != "CLEAN":
            flagged.append(result)

    return results, flagged


def print_report(results, flagged):
    """Print scam detection report."""
    print(f"\n🚨 Job Scam Detection Report")
    print(f"{'=' * 70}")
    print(f"  Total jobs scanned: {len(results)}")
    print(f"  Flagged as suspicious: {len(flagged)}")

    # Count by risk level
    levels = {}
    for r in results:
        level = r["risk_level"]
        levels[level] = levels.get(level, 0) + 1

    print(f"\n  Risk Distribution:")
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAN"]:
        count = levels.get(level, 0)
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "CLEAN": "✅"}
        print(f"    {icon.get(level, '?')} {level}: {count}")

    if flagged:
        print(f"\n  ⚠️  Flagged Jobs:")
        print(f"  {'─' * 50}")
        for r in sorted(flagged, key=lambda x: -x["risk_score"]):
            print(f"\n  [{r['risk_level']}] {r['title'][:40]} @ {r['company'][:25]}")
            print(f"    Risk Score: {r['risk_score']}/100")
            for flag in r["flags"]:
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
                print(f"    {severity_icon.get(flag['severity'], '?')} {flag['description']}")

    print(f"\n{'=' * 70}")


def save_report(results, flagged):
    """Save report to JSON."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_scanned": len(results),
        "total_flagged": len(flagged),
        "flagged_jobs": flagged,
    }
    filepath = OUTPUT_DIR / f"scam_report_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n💾 Report saved: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Job Scam Detector")
    parser.add_argument("--scan", action="store_true", help="Scan all jobs")
    parser.add_argument("--job-id", type=str, help="Analyze specific job")
    parser.add_argument("--ai", action="store_true", help="Use AI for analysis")
    parser.add_argument("--save", action="store_true", help="Save report")
    parser.add_argument("--limit", type=int, default=500, help="Max jobs to scan")
    parser.add_argument("--patterns", action="store_true", help="List scam patterns")
    args = parser.parse_args()

    if args.patterns:
        print(f"\n🔍 Scam Detection Patterns ({len(SCAM_PATTERNS)} checks)")
        print("=" * 60)
        for name, info in SCAM_PATTERNS.items():
            severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            print(f"  {severity_icon.get(info['severity'], '?')} {name}")
            print(f"    {info['description']}")
        return

    if args.scan:
        results, flagged = scan_all_jobs(args.limit)
        print_report(results, flagged)
        if args.save:
            save_report(results, flagged)
        return

    if args.job_id:
        # Find specific job
        for fname in ["matched_jobs.csv", "job_postings.csv"]:
            csv_path = DATA_DIR / fname
            if not csv_path.exists():
                continue
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    jid = row.get("id", row.get("job_id", ""))
                    if jid == args.job_id:
                        result = analyze_job(row)
                        print(f"\n🔍 Analysis for: {row.get('title', '')} @ {row.get('company', '')}")
                        print(f"   Risk: {result['risk_level']} ({result['risk_score']}/100)")
                        for flag in result["flags"]:
                            print(f"   ⚠️  {flag['description']}")
                        if args.ai:
                            ai_result = ai_analyze_job(row)
                            if ai_result:
                                print(f"\n   🤖 AI Assessment:")
                                print(f"      Legitimacy: {ai_result.get('legitimacy_score', 'N/A')}/10")
                                print(f"      Verdict: {ai_result.get('verdict', 'N/A')}")
                                for rf in ai_result.get("red_flags", []):
                                    print(f"      🔴 {rf}")
                        return
        print(f"❌ Job {args.job_id} not found")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
