#!/usr/bin/env python3
"""
Interview Question Bank Generator
Generate comprehensive question bank from top companies and matched jobs.
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
INTERVIEW_DIR = DATA_DIR / "interview_prep"
INTERVIEW_DIR.mkdir(parents=True, exist_ok=True)

MATCHED_JOBS = DATA_DIR / "matched_jobs.csv"
QUESTION_BANK = INTERVIEW_DIR / "question_bank.json"

# OpenRouter
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Top companies to focus on
TOP_COMPANIES = [
    "Google", "Meta", "Amazon", "Microsoft", "Apple",
    "Netflix", "Stripe", "Airbnb", "Uber", "Spotify",
    "Shopify", "Atlassian", "GitLab", "HashiCorp", "Datadog"
]


def load_matched_jobs(top_n=100):
    """Load top matched jobs."""
    if not MATCHED_JOBS.exists():
        return []
    
    jobs = []
    with open(MATCHED_JOBS, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    
    jobs.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    return jobs[:top_n]


def extract_companies(jobs):
    """Extract unique companies from jobs."""
    companies = {}
    for job in jobs:
        company = job.get("company", "")
        if company:
            if company not in companies:
                companies[company] = 0
            companies[company] += 1
    
    # Sort by job count
    sorted_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)
    return sorted_companies


def extract_technical_skills(jobs):
    """Extract technical skills from jobs."""
    skill_count = {}
    technologies = [
        "react", "node.js", "typescript", "python", "next.js", "aws", "docker",
        "postgresql", "mongodb", "redis", "graphql", "rest", "kubernetes",
        "tailwindcss", "redux", "express", "fastapi", "golang", "rust", "java",
        "vue", "angular", "django", "flask", "spring", "terraform", "jenkins"
    ]
    
    for job in jobs:
        text = " ".join(str(v) for v in job.values() if v).lower()
        for tech in technologies:
            if tech in text:
                skill_count[tech] = skill_count.get(tech, 0) + 1
    
    sorted_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_skills


def call_openrouter(prompt, max_tokens=2000):
    """Call OpenRouter API."""
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️  OpenRouter error: {e}")
        return None


def generate_technical_questions(skills, category):
    """Generate technical questions for a skill category."""
    top_skills = [s[0] for s in skills[:10]]
    
    prompt = f"""Generate 10 technical interview questions for {category} role focusing on: {', '.join(top_skills[:8])}.

Format as JSON array:
[
  {{
    "question": "Question text?",
    "difficulty": "easy|medium|hard",
    "topic": "specific topic",
    "expected_answer": "Brief answer outline"
  }}
]

Mix of:
- 3 easy questions
- 4 medium questions  
- 3 hard questions

Focus on practical, real-world scenarios. Return ONLY valid JSON."""
    
    result = call_openrouter(prompt, max_tokens=1500)
    if result:
        try:
            # Try to parse JSON
            questions = json.loads(result)
            if isinstance(questions, list):
                return questions
        except Exception:
            pass
    
    # Fallback
    return [
        {
            "question": f"Explain {top_skills[0]} architecture and best practices",
            "difficulty": "medium",
            "topic": top_skills[0],
            "expected_answer": "Key concepts and patterns"
        }
    ]


def generate_system_design_questions():
    """Generate system design questions."""
    return [
        {
            "question": "Design a real-time job matching system like our pipeline",
            "difficulty": "hard",
            "topic": "System Design",
            "expected_answer": "Message queues, scoring algorithm, caching layer, database schema"
        },
        {
            "question": "Design a URL shortener service",
            "difficulty": "medium",
            "topic": "System Design",
            "expected_answer": "Hash function, database, caching, redirect logic"
        },
        {
            "question": "Design a notification system for 1M users",
            "difficulty": "hard",
            "topic": "System Design",
            "expected_answer": "Pub/sub, push notifications, rate limiting, delivery tracking"
        },
        {
            "question": "Design an e-commerce shopping cart",
            "difficulty": "medium",
            "topic": "System Design",
            "expected_answer": "Session management, inventory checks, price calculation, persistence"
        },
        {
            "question": "Design a rate limiter for API gateway",
            "difficulty": "hard",
            "topic": "System Design",
            "expected_answer": "Token bucket/sliding window, Redis, distributed locks"
        },
    ]


def generate_behavioral_questions():
    """Generate behavioral questions."""
    return [
        {
            "question": "Tell me about a time you led a technical migration project",
            "difficulty": "medium",
            "topic": "Leadership",
            "expected_answer": "STAR method: Situation, Task, Action, Result with metrics"
        },
        {
            "question": "Describe a challenging bug you debugged in production",
            "difficulty": "medium",
            "topic": "Problem Solving",
            "expected_answer": "Systematic approach, debugging tools, root cause, prevention"
        },
        {
            "question": "How do you handle disagreements with team members on technical decisions?",
            "difficulty": "easy",
            "topic": "Collaboration",
            "expected_answer": "Listen first, data-driven decisions, compromise, respect"
        },
        {
            "question": "Tell me about a time you had to learn a new technology quickly",
            "difficulty": "easy",
            "topic": "Adaptability",
            "expected_answer": "Learning strategy, resources used, outcome, lessons learned"
        },
        {
            "question": "Describe your approach to mentoring junior developers",
            "difficulty": "medium",
            "topic": "Mentorship",
            "expected_answer": "Code reviews, pair programming, gradual responsibility, feedback"
        },
    ]


def generate_coding_challenges():
    """Generate coding challenges."""
    return [
        {
            "question": "Implement a function to find the kth largest element in an array",
            "difficulty": "medium",
            "topic": "Algorithms",
            "expected_answer": "Quickselect O(n) or heap O(n log k)",
            "starter_code": "def findKthLargest(nums, k):\n    # Your code here\n    pass"
        },
        {
            "question": "Design a rate limiter class that allows at most N requests per second",
            "difficulty": "medium",
            "topic": "Design",
            "expected_answer": "Sliding window with deque or timestamp queue",
            "starter_code": "class RateLimiter:\n    def __init__(self, max_requests):\n        pass\n    \n    def allow_request(self):\n        pass"
        },
        {
            "question": "Implement LRU cache with O(1) get and put operations",
            "difficulty": "hard",
            "topic": "Data Structures",
            "expected_answer": "Hash map + doubly linked list",
            "starter_code": "class LRUCache:\n    def __init__(self, capacity):\n        pass\n    \n    def get(self, key):\n        pass\n    \n    def put(self, key, value):\n        pass"
        },
        {
            "question": "Write a function to merge k sorted linked lists",
            "difficulty": "hard",
            "topic": "Data Structures",
            "expected_answer": "Min-heap or divide and conquer",
            "starter_code": "def mergeKLists(lists):\n    # Your code here\n    pass"
        },
        {
            "question": "Implement a trie (prefix tree) with insert, search, and startsWith",
            "difficulty": "medium",
            "topic": "Data Structures",
            "expected_answer": "Tree node with children hash map",
            "starter_code": "class Trie:\n    def __init__(self):\n        pass\n    \n    def insert(self, word):\n        pass\n    \n    def search(self, word):\n        pass\n    \n    def startsWith(self, prefix):\n        pass"
        },
    ]


def generate_question_bank(jobs, send_telegram_flag=False):
    """Generate comprehensive question bank."""
    print(f"\n{'='*70}")
    print(f"  INTERVIEW QUESTION BANK GENERATOR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # Analyze jobs
    print(f"📊 Analyzing {len(jobs)} matched jobs...")
    companies = extract_companies(jobs)
    skills = extract_technical_skills(jobs)
    
    print(f"   Found {len(companies)} companies")
    print(f"   Found {len(skills)} technical skills")
    
    print("\n🔍 Top Companies:")
    for company, count in companies[:10]:
        print(f"   • {company}: {count} jobs")
    
    print("\n🔧 Top Skills:")
    for skill, count in skills[:10]:
        print(f"   • {skill}: {count} jobs")
    
    # Generate questions
    print("\n🤖 Generating question bank...")
    
    question_bank = {
        "generated_at": datetime.now().isoformat(),
        "total_jobs_analyzed": len(jobs),
        "top_companies": [c[0] for c in companies[:15]],
        "top_skills": [s[0] for s in skills[:20]],
        "categories": {}
    }
    
    # Technical questions by category
    categories = ["frontend", "backend", "fullstack", "devops", "database"]
    for category in categories:
        print(f"  → {category.title()} questions...")
        category_skills = [(s, c) for s, c in skills if s in category.lower() or category in s.lower()]
        if not category_skills:
            category_skills = skills[:10]
        
        questions = generate_technical_questions(category_skills, category)
        question_bank["categories"][category] = questions
        print(f"     Generated {len(questions)} questions")
    
    # System design
    print("  → System design questions...")
    question_bank["categories"]["system_design"] = generate_system_design_questions()
    
    # Behavioral
    print("  → Behavioral questions...")
    question_bank["categories"]["behavioral"] = generate_behavioral_questions()
    
    # Coding challenges
    print("  → Coding challenges...")
    question_bank["categories"]["coding"] = generate_coding_challenges()
    
    # Save
    QUESTION_BANK.write_text(json.dumps(question_bank, indent=2))
    print(f"\n✅ Question bank saved: {QUESTION_BANK.name}")
    
    # Generate markdown summary
    md_content = f"""# Interview Question Bank
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
*Based on {len(jobs)} matched jobs from {len(companies)} companies*

---

## Top Companies
{chr(10).join(f'- {c[0]} ({c[1]} jobs)' for c in companies[:15])}

## Top Skills
{chr(10).join(f'- {s[0].title()} ({s[1]} jobs)' for s in skills[:20])}

---

## Questions by Category

### Frontend ({len(question_bank['categories'].get('frontend', []))} questions)
"""
    
    for q in question_bank["categories"].get("frontend", [])[:5]:
        md_content += f"\n**{q['question']}** ({q['difficulty']})\n"
    
    md_content += "\n### Backend ({len(question_bank['categories'].get('backend', []))} questions)\n"
    for q in question_bank["categories"].get("backend", [])[:5]:
        md_content += f"\n**{q['question']}** ({q['difficulty']})\n"
    
    md_content += "\n### System Design ({len(question_bank['categories'].get('system_design', []))} questions)\n"
    for q in question_bank["categories"].get("system_design", [])[:5]:
        md_content += f"\n**{q['question']}** ({q['difficulty']})\n"
    
    md_content += "\n### Behavioral ({len(question_bank['categories'].get('behavioral', []))} questions)\n"
    for q in question_bank["categories"].get("behavioral", [])[:5]:
        md_content += f"\n**{q['question']}** ({q['difficulty']})\n"
    
    md_content += "\n### Coding Challenges ({len(question_bank['categories'].get('coding', []))} questions)\n"
    for q in question_bank["categories"].get("coding", [])[:5]:
        md_content += f"\n**{q['question']}** ({q['difficulty']})\n"
    
    md_file = INTERVIEW_DIR / "question_bank_summary.md"
    md_file.write_text(md_content)
    print(f"✅ Summary saved: {md_file.name}")
    
    # Stats
    total_questions = sum(len(qs) for qs in question_bank["categories"].values())
    print(f"\n📊 Total questions: {total_questions}")
    
    # Telegram
    if send_telegram_flag:
        try:
            import requests
            msg = f"📚 *Interview Question Bank Generated*\n\n"
            msg += f"Analyzed {len(jobs)} jobs from {len(companies)} companies\n\n"
            msg += f"Total questions: {total_questions}\n"
            msg += f"Categories: {len(question_bank['categories'])}\n\n"
            msg += f"Top skills: {', '.join(s[0] for s in skills[:8])}"
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
            print("📱 Telegram notification sent")
        except Exception as e:
            print(f"⚠️  Telegram error: {e}")
    
    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Interview Question Bank Generator")
    parser.add_argument("--top", type=int, default=100, help="Number of top jobs to analyze")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram notification")
    args = parser.parse_args()
    
    jobs = load_matched_jobs(args.top)
    if not jobs:
        print("❌ No matched jobs found")
        sys.exit(1)
    
    generate_question_bank(jobs, send_telegram_flag=args.send_telegram)


if __name__ == "__main__":
    main()
