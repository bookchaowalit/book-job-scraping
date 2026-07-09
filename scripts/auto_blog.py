#!/usr/bin/env python3
"""
Portfolio Auto-Blog — Auto-generate weekly blog posts from pipeline statistics.
Creates engaging content about the job search journey, pipeline stats, and insights.

Usage:
    python auto_blog.py --generate
    python auto_blog.py --generate --topic weekly-stats
    python auto_blog.py --generate --topic insights
    python auto_blog.py --list
    python auto_blog.py --publish --post <file>
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
BLOG_DIR = DATA_DIR / "blog_posts"
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
TRACKER_FILE = DATA_DIR / "application_tracker.json"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# Portfolio blog path
PORTFOLIO_BLOG_DIR = Path(__file__).parent.parent.parent / "book-apps" / "portfolio" / "bookchaowalit-portfolio-frontend" / "src" / "content" / "blog"


def ai_call(messages, temperature=0.7):
    """Call OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature, max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  AI error: {e}")
        return None


def load_pipeline_stats():
    """Load current pipeline statistics."""
    stats = {
        "total_postings": 0,
        "matched_jobs": 0,
        "applications": 0,
        "interviews": 0,
        "offers": 0,
        "top_boards": [],
        "top_skills": [],
        "avg_salary": 0,
        "week_jobs": 0,
    }

    # Count postings
    if JOB_POSTINGS_CSV.exists():
        with open(JOB_POSTINGS_CSV, "r", encoding="utf-8") as f:
            postings = list(csv.DictReader(f))
            stats["total_postings"] = len(postings)
            # Count this week
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            stats["week_jobs"] = sum(1 for p in postings if p.get("scraped_at", "") > week_ago)

    # Count matched
    if MATCHED_JOBS_CSV.exists():
        with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
            matched = list(csv.DictReader(f))
            stats["matched_jobs"] = len(matched)

            # Top boards
            boards = {}
            for job in matched:
                board = job.get("board", "unknown")
                boards[board] = boards.get(board, 0) + 1
            stats["top_boards"] = sorted(boards.items(), key=lambda x: x[1], reverse=True)[:5]

            # Extract skills
            skills = {}
            for job in matched:
                for skill in (job.get("skills", "") or "")[:200].split(","):
                    s = skill.strip().lower()
                    if len(s) > 2:
                        skills[s] = skills.get(s, 0) + 1
            stats["top_skills"] = sorted(skills.items(), key=lambda x: x[1], reverse=True)[:10]

            # Average salary
            salaries = []
            for job in matched:
                try:
                    smin = float(job.get("salary_min", 0) or 0)
                    smax = float(job.get("salary_max", 0) or 0)
                    if smin > 0:
                        salaries.append((smin + smax) / 2)
                except:
                    pass
            stats["avg_salary"] = int(sum(salaries) / len(salaries)) if salaries else 0

    # Count applications
    if APPLICATIONS_CSV.exists():
        with open(APPLICATIONS_CSV, "r", encoding="utf-8") as f:
            stats["applications"] = sum(1 for _ in csv.DictReader(f))

    # Tracker stats
    if TRACKER_FILE.exists():
        tracker = json.loads(TRACKER_FILE.read_text())
        apps = tracker.get("applications", {})
        stats["interviews"] = sum(1 for a in apps.values() if a.get("stage") in ["screening", "technical", "onsite"])
        stats["offers"] = sum(1 for a in apps.values() if a.get("stage") == "offer")

    return stats


def generate_weekly_stats_post(stats):
    """Generate a weekly stats blog post."""
    date_range = f"{(datetime.now() - timedelta(days=7)).strftime('%b %d')} - {datetime.now().strftime('%b %d, %Y')}"

    top_boards_md = "\n".join(f"- **{board}**: {count} matches" for board, count in stats["top_boards"]) if stats["top_boards"] else "- No data yet"
    top_skills_md = ", ".join(f"`{skill}`" for skill, _ in stats["top_skills"][:8]) if stats["top_skills"] else "No data yet"

    content = f"""---
title: "Weekly Job Pipeline Report — {date_range}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
tags: ["weekly-report", "job-search", "automation"]
author: "Chaowalit 'Book' Greepoke"
draft: false
---

# Weekly Job Pipeline Report

This week my automated job scraping pipeline processed data from **25+ job boards** across the internet. Here's what it found:

## 📊 This Week's Numbers

| Metric | Value |
|--------|-------|
| New Jobs Scraped | {stats['week_jobs']:,} |
| Total in Pipeline | {stats['total_postings']:,} |
| Matched to My Profile | {stats['matched_jobs']:,} |
| Applications Submitted | {stats['applications']} |
| Interviews Scheduled | {stats['interviews']} |

## 🏆 Top Job Boards

{top_boards_md}

## 🛠️ Most In-Demand Skills

{top_skills_md}

## 💰 Average Salary (Matched Jobs)

{"${:,.0f}".format(stats['avg_salary']) if stats['avg_salary'] > 0 else "Data not available yet"}

## 🔍 What I Learned

This week's data shows some interesting trends in the developer job market. The pipeline continues to improve its matching accuracy, and I'm seeing better quality matches as the keyword tuning kicks in.

---

*This report was auto-generated by my job search pipeline. The entire process — from scraping to matching to notification — runs automatically.*
"""
    return content


def generate_insights_post(stats):
    """Generate an insights/analysis blog post using AI."""
    prompt = f"""Write a short, engaging blog post (300-500 words) about job search insights based on these pipeline stats:

- {stats['total_postings']:,} total jobs scraped
- {stats['matched_jobs']} matched to profile
- {stats['applications']} applications submitted
- {stats['interviews']} interviews
- Top skills: {', '.join(s for s, _ in stats['top_skills'][:5])}
- Average salary: {"${:,.0f}".format(stats['avg_salary']) if stats['avg_salary'] else 'N/A'}

The author is a Senior Full-Stack Developer based in Bangkok, Thailand, running an automated job search pipeline. Make it personal, insightful, and include actionable tips for other job seekers. Write in first person. Use markdown format with frontmatter."""

    if OPENROUTER_API_KEY:
        result = ai_call([
            {"role": "system", "content": "You are a tech job search blogger who writes engaging, data-driven content. Include markdown frontmatter with title, date, tags, author, and draft: false."},
            {"role": "user", "content": prompt}
        ], temperature=0.8)
        if result:
            return result

    # Fallback template
    return f"""---
title: "What {stats['total_postings']:,} Job Postings Taught Me About the Dev Job Market"
date: "{datetime.now().strftime('%Y-%m-%d')}"
tags: ["insights", "job-search", "data-analysis"]
author: "Chaowalit 'Book' Greepoke"
draft: false
---

# What {stats['total_postings']:,} Job Postings Taught Me

After scraping and analyzing {stats['total_postings']:,} job postings through my automated pipeline, here are my key insights:

## The Numbers Don't Lie

- **{stats['matched_jobs']}** out of {stats['total_postings']:,} jobs matched my profile ({stats['matched_jobs']/max(stats['total_postings'],1)*100:.1f}%)
- **{stats['applications']}** applications submitted
- Top skills in demand: {', '.join(s for s, _ in stats['top_skills'][:5])}

## Key Takeaways

1. **Automation wins** — My pipeline scans 25+ boards daily, catching jobs within hours of posting
2. **Skills matter more than titles** — The same role has 10 different titles across companies
3. **Remote is competitive** — Remote positions get 5x more applicants
4. **Speed matters** — Early applicants have significantly higher response rates

## What's Next

I'm continuously tuning my pipeline's keyword matching and adding new job boards. The goal: find the right opportunities faster than anyone else.

---

*Built with Python, automated with cron, powered by curiosity.*
"""


def generate_post(topic="weekly-stats"):
    """Generate a blog post."""
    BLOG_DIR.mkdir(parents=True, exist_ok=True)

    stats = load_pipeline_stats()

    if topic == "weekly-stats":
        content = generate_weekly_stats_post(stats)
    elif topic == "insights":
        content = generate_insights_post(stats)
    else:
        print(f"Unknown topic: {topic}. Use 'weekly-stats' or 'insights'.")
        return

    # Save
    slug = f"{topic}_{datetime.now().strftime('%Y%m%d')}"
    filename = f"{slug}.md"
    filepath = BLOG_DIR / filename
    filepath.write_text(content)

    print(f"Blog post generated: {filepath}")
    print(f"  Topic: {topic}")
    print(f"  Length: {len(content)} chars")

    # Also copy to portfolio blog if directory exists
    if PORTFOLIO_BLOG_DIR.exists():
        portfolio_path = PORTFOLIO_BLOG_DIR / filename
        portfolio_path.write_text(content)
        print(f"  Also saved to portfolio: {portfolio_path}")

    return filepath


def list_posts():
    """List all generated blog posts."""
    if not BLOG_DIR.exists():
        print("No blog posts generated yet.")
        return

    posts = sorted(BLOG_DIR.glob("*.md"))
    if not posts:
        print("No blog posts yet.")
        return

    print(f"\n📝 BLOG POSTS ({len(posts)} total):\n")
    for post in posts:
        # Extract title from frontmatter
        lines = post.read_text().split("\n")
        title = post.stem
        for line in lines:
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"')
                break
        date = post.stat().st_mtime
        date_str = datetime.fromtimestamp(date).strftime("%Y-%m-%d")
        print(f"  {date_str}  {title}")


def main():
    parser = argparse.ArgumentParser(description="Portfolio Auto-Blog")
    parser.add_argument("--generate", action="store_true", help="Generate blog post")
    parser.add_argument("--topic", default="weekly-stats", choices=["weekly-stats", "insights"])
    parser.add_argument("--list", action="store_true", help="List posts")
    parser.add_argument("--publish", action="store_true", help="Publish post")
    parser.add_argument("--post", help="Post file to publish")
    args = parser.parse_args()

    if args.generate:
        generate_post(args.topic)
    elif args.list:
        list_posts()
    elif args.publish:
        if not args.post:
            print("Error: --post required")
            return
        print(f"Publishing: {args.post}")
        print("  Post would be deployed via Vercel on next git push.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
