#!/usr/bin/env python3
"""
Skills Gap Analyzer
Compares current skills vs. top job requirements.
Identifies missing skills and suggests learning resources.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_DIR = DATA_DIR / "skills_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# User's current skills
CURRENT_SKILLS = {
    # Languages
    "javascript": 9, "typescript": 9, "python": 8, "html": 9, "css": 8,
    "sql": 8, "go": 4, "rust": 2, "dart": 3, "php": 5,
    # Frontend
    "react": 9, "next.js": 9, "vue.js": 6, "svelte": 4, "tailwindcss": 9,
    "redux": 8, "zustand": 7, "webpack": 7, "vite": 7,
    # Backend
    "node.js": 9, "express.js": 9, "fastapi": 8, "django": 5, "flask": 6,
    "graphql": 7, "rest api": 9, "websocket": 7,
    # Database
    "postgresql": 8, "mongodb": 7, "redis": 7, "mysql": 7, "sqlite": 8,
    "prisma": 8, "supabase": 7, "firebase": 7,
    # Cloud & DevOps
    "aws": 7, "gcp": 5, "docker": 8, "kubernetes": 4, "terraform": 3,
    "ci/cd": 8, "github actions": 8, "vercel": 8, "cloudflare": 6,
    # AI/ML
    "openai api": 7, "langchain": 5, "embeddings": 5, "prompt engineering": 7,
    "rag": 4, "vector database": 4,
    # Tools & Other
    "git": 9, "linux": 8, "nginx": 7, "jest": 7, "playwright": 6,
    "figma": 5, "agile": 8, "scrum": 7,
}

# Skill taxonomy — map variations to canonical names
SKILL_ALIASES = {
    "react.js": "react", "reactjs": "react", "react native": "react",
    "nextjs": "next.js", "next-js": "next.js",
    "node.js": "node.js", "nodejs": "node.js", "node": "node.js",
    "express": "express.js", "expressjs": "express.js",
    "ts": "typescript", "js": "javascript",
    "py": "python", "python3": "python",
    "go": "go", "golang": "go",
    "tailwind": "tailwindcss", "tailwind css": "tailwindcss",
    "postgre": "postgresql", "postgres": "postgresql", "pg": "postgresql",
    "mongo": "mongodb", "mssql": "mysql",
    "k8s": "kubernetes", "kube": "kubernetes",
    "rest": "rest api", "restful": "rest api", "rest api": "rest api",
    "gql": "graphql",
    "ci cd": "ci/cd", "cicd": "ci/cd", "ci-cd": "ci/cd",
    "gh actions": "github actions",
    "fast api": "fastapi",
    "vue": "vue.js", "vuejs": "vue.js",
    "lang chain": "langchain", "lang-chain": "langchain",
    "llm": "openai api", "chatgpt": "openai api",
    "vite.js": "vite",
    "redux toolkit": "redux",
    "docker compose": "docker",
}

# Learning resources by skill category
LEARNING_RESOURCES = {
    "go": {
        "course": "https://go.dev/tour/",
        "book": "The Go Programming Language",
        "practice": "https://exercism.org/tracks/go",
        "level": "intermediate",
    },
    "rust": {
        "course": "https://doc.rust-lang.org/book/",
        "book": "The Rust Programming Language",
        "practice": "https://exercism.org/tracks/rust",
        "level": "advanced",
    },
    "kubernetes": {
        "course": "https://kubernetes.io/docs/tutorials/",
        "book": "Kubernetes in Action",
        "practice": "https://killercoda.com/kubernetes",
        "level": "advanced",
    },
    "terraform": {
        "course": "https://developer.hashicorp.com/terraform/tutorials",
        "book": "Terraform: Up & Running",
        "practice": "https://terraform.io/registry",
        "level": "intermediate",
    },
    "langchain": {
        "course": "https://python.langchain.com/docs/get_started",
        "book": "Building LLM Apps with LangChain",
        "practice": "Build a RAG chatbot",
        "level": "intermediate",
    },
    "rag": {
        "course": "https://www.deeplearning.ai/short-courses/",
        "book": "Building LLM Applications",
        "practice": "Build a document Q&A system",
        "level": "intermediate",
    },
    "vector database": {
        "course": "https://www.pinecone.io/learn/",
        "book": "Vector Database Guide",
        "practice": "Build semantic search with Pinecone/Weaviate",
        "level": "intermediate",
    },
    "docker": {
        "course": "https://docs.docker.com/get-started/",
        "book": "Docker Deep Dive",
        "practice": "Containerize a full-stack app",
        "level": "beginner",
    },
    "aws": {
        "course": "https://aws.amazon.com/training/",
        "book": "AWS Certified Solutions Architect",
        "practice": "https://aws.amazon.com/free/",
        "level": "intermediate",
    },
    "gcp": {
        "course": "https://cloud.google.com/training",
        "book": "Google Cloud Platform in Action",
        "practice": "https://cloud.google.com/free",
        "level": "intermediate",
    },
    "system design": {
        "course": "https://systemdesignprimer.com",
        "book": "Designing Data-Intensive Applications",
        "practice": "Design Twitter, Uber, etc.",
        "level": "advanced",
    },
    "graphql": {
        "course": "https://graphql.org/learn/",
        "book": "Learning GraphQL",
        "practice": "Build a GraphQL API with Apollo",
        "level": "intermediate",
    },
    "svelte": {
        "course": "https://svelte.dev/tutorial",
        "book": "Svelte and Sapper in Action",
        "practice": "Build a SvelteKit app",
        "level": "beginner",
    },
    "kafka": {
        "course": "https://developer.confluent.io/learn-kafka/",
        "book": "Kafka: The Definitive Guide",
        "practice": "Build an event-driven system",
        "level": "advanced",
    },
}

DEFAULT_RESOURCE = {
    "course": "Search YouTube / Udemy",
    "book": "Check O'Reilly / Amazon",
    "practice": "Build a personal project",
    "level": "varies",
}


def load_jobs():
    """Load all job data."""
    jobs = []
    for fname in ["matched_jobs.csv", "job_postings.csv"]:
        csv_path = DATA_DIR / fname
        if not csv_path.exists():
            continue
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    jobs.append(row)
        except Exception:
            pass
    return jobs


def normalize_skill(skill):
    """Normalize skill name."""
    skill = skill.lower().strip()
    return SKILL_ALIASES.get(skill, skill)


def extract_skills_from_job(job):
    """Extract skills from a job posting."""
    skills = set()
    text = " ".join(str(v) for v in job.values() if v)

    # Known skill patterns
    skill_patterns = [
        r'\b(react|vue\.?js?|svelte|angular|next\.?js?|nuxt)\b',
        r'\b(node\.?js?|express\.?js?|fastapi|django|flask|rails|laravel)\b',
        r'\b(python|javascript|typescript|golang?|rust|java|kotlin|swift|php|ruby)\b',
        r'\b(postgresql?|mongodb|redis|mysql|elasticsearch|dynamodb|cassandra)\b',
        r'\b(aws|gcp|azure|docker|kubernetes|terraform|ansible)\b',
        r'\b(graphql|rest|grpc|websocket|microservices?|serverless)\b',
        r'\b(ci/cd|cicd|github actions|jenkins|gitlab ci)\b',
        r'\b(tailwindcss?|bootstrap|material ui|chakra ui)\b',
        r'\b(langchain|rag|vector database|embeddings|llm|openai|anthropic)\b',
        r'\b(kafka|rabbitmq|celery|redis queue)\b',
        r'\b(system design|architecture|scalability)\b',
        r'\b(agile|scrum|kanban|jira)\b',
        r'\b(jest|vitest|cypress|playwright|testing)\b',
        r'\b(prisma|supabase|firebase|planetscale)\b',
        r'\b(figma|sketch|design system|ux/ui)\b',
        r'\b(git|linux|nginx|vercel|cloudflare)\b',
    ]

    for pattern in skill_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            skills.add(normalize_skill(m))

    return skills


def analyze_gaps(jobs, top_n=50):
    """Analyze skill gaps."""
    # Count skill frequency across jobs
    skill_counter = Counter()
    skill_jobs = defaultdict(list)

    for job in jobs:
        skills = extract_skills_from_job(job)
        for skill in skills:
            skill_counter[skill] += 1
            if len(skill_jobs[skill]) < 3:
                skill_jobs[skill].append({
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                })

    # Categorize
    have_skills = {}
    missing_skills = {}
    learning_skills = {}

    for skill, count in skill_counter.most_common(top_n):
        current_level = CURRENT_SKILLS.get(skill, 0)

        if current_level >= 7:
            have_skills[skill] = {
                "level": current_level,
                "demand": count,
                "status": "strong",
            }
        elif current_level >= 4:
            learning_skills[skill] = {
                "level": current_level,
                "demand": count,
                "status": "developing",
                "gap": 7 - current_level,
            }
        else:
            missing_skills[skill] = {
                "level": current_level,
                "demand": count,
                "status": "gap",
                "gap": 7 - current_level,
                "resources": LEARNING_RESOURCES.get(skill, DEFAULT_RESOURCE),
                "example_jobs": skill_jobs.get(skill, [])[:2],
            }

    return {
        "total_jobs_analyzed": len(jobs),
        "unique_skills_found": len(skill_counter),
        "have_skills": have_skills,
        "learning_skills": learning_skills,
        "missing_skills": missing_skills,
        "top_demanded": skill_counter.most_common(20),
    }


def print_report(results):
    """Print skills gap report."""
    print(f"\n🎯 Skills Gap Analysis")
    print(f"{'=' * 70}")
    print(f"  Jobs analyzed: {results['total_jobs_analyzed']}")
    print(f"  Unique skills found: {results['unique_skills_found']}")

    print(f"\n  ✅ STRONG SKILLS (level ≥ 7, in demand)")
    print(f"  {'─' * 50}")
    for skill, info in sorted(results["have_skills"].items(), key=lambda x: -x[1]["demand"]):
        bar = "█" * info["level"] + "░" * (10 - info["level"])
        print(f"     {skill:20s} [{bar}] {info['level']}/10  (demand: {info['demand']})")

    print(f"\n  🔄 DEVELOPING SKILLS (level 4-6, needs improvement)")
    print(f"  {'─' * 50}")
    for skill, info in sorted(results["learning_skills"].items(), key=lambda x: -x[1]["demand"]):
        bar = "█" * info["level"] + "░" * (10 - info["level"])
        print(f"     {skill:20s} [{bar}] {info['level']}/10  (demand: {info['demand']}, gap: {info['gap']})")

    print(f"\n  ❌ SKILL GAPS (level < 4, high demand)")
    print(f"  {'─' * 50}")
    for skill, info in sorted(results["missing_skills"].items(), key=lambda x: -x[1]["demand"]):
        res = info["resources"]
        print(f"     {skill:20s} demand={info['demand']:3d}  gap={info['gap']}")
        print(f"       📚 {res.get('course', 'N/A')[:50]}")
        if info.get("example_jobs"):
            ej = info["example_jobs"][0]
            print(f"       💼 e.g. {ej['title'][:30]} @ {ej['company'][:20]}")

    print(f"\n  📊 TOP 20 MOST DEMANDED SKILLS")
    print(f"  {'─' * 50}")
    for skill, count in results["top_demanded"]:
        level = CURRENT_SKILLS.get(skill, 0)
        status = "✅" if level >= 7 else "🔄" if level >= 4 else "❌"
        bar = "█" * level + "░" * (10 - level)
        print(f"     {status} {skill:20s} [{bar}] {level}/10  (seen in {count} jobs)")

    print(f"{'=' * 70}")


def save_report(results):
    """Save analysis to JSON."""
    filepath = OUTPUT_DIR / "skills_gap_latest.json"
    # Convert for JSON serialization
    serializable = {
        "total_jobs_analyzed": results["total_jobs_analyzed"],
        "unique_skills_found": results["unique_skills_found"],
        "have_skills": results["have_skills"],
        "learning_skills": results["learning_skills"],
        "missing_skills": {k: {kk: vv for kk, vv in v.items()} for k, v in results["missing_skills"].items()},
        "top_demanded": results["top_demanded"],
        "generated_at": datetime.now().isoformat(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n💾 Saved to {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Skills Gap Analyzer")
    parser.add_argument("--analyze", action="store_true", help="Run skills gap analysis")
    parser.add_argument("--top", type=int, default=50, help="Top N skills to analyze")
    parser.add_argument("--save", action="store_true", help="Save results to JSON")
    parser.add_argument("--current", action="store_true", help="Show current skills")
    parser.add_argument("--resources", type=str, help="Get resources for a skill")
    args = parser.parse_args()

    if args.current:
        print(f"\n🛠️  Current Skills ({len(CURRENT_SKILLS)} skills)")
        print("=" * 60)
        for skill, level in sorted(CURRENT_SKILLS.items(), key=lambda x: -x[1]):
            bar = "█" * level + "░" * (10 - level)
            status = "✅" if level >= 7 else "🔄" if level >= 4 else "❌"
            print(f"  {status} {skill:20s} [{bar}] {level}/10")
        return

    if args.resources:
        skill = args.resources.lower()
        res = LEARNING_RESOURCES.get(skill, DEFAULT_RESOURCE)
        print(f"\n📚 Learning Resources for '{skill}':")
        print(f"  🎓 Course: {res.get('course', 'N/A')}")
        print(f"  📖 Book:   {res.get('book', 'N/A')}")
        print(f"  🔨 Practice: {res.get('practice', 'N/A')}")
        print(f"  📊 Level:  {res.get('level', 'N/A')}")
        return

    if args.analyze:
        jobs = load_jobs()
        if not jobs:
            print("❌ No job data found. Run the pipeline first.")
            return

        print(f"\n📊 Analyzing {len(jobs)} jobs for skill gaps...")
        results = analyze_gaps(jobs, args.top)
        print_report(results)

        if args.save:
            save_report(results)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Skills Gap Analyzer - Analyzes matched jobs and identifies missing skills.
Generates actionable learning recommendations based on job market demand.

Usage:
    python3 skills_gap_analyzer.py
    python3 skills_gap_analyzer.py --top 20
    python3 skills_gap_analyzer.py --output skills_gap_report.json
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
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
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5255551291")

# Your current skills (from match_jobs.py)
YOUR_SKILLS = {
    # Core dev skills
    "python", "react", "next.js", "typescript", "node.js", "fastapi", "django", "full-stack",
    "javascript", "api", "rest", "graphql",
    # Frontend
    "vue", "tailwind", "css", "html", "redux",
    # Backend / Infra
    "postgresql", "mysql", "redis", "docker", "aws", "gcp", "linux", "git",
    # AI / Data
    "ai", "machine learning", "llm", "openai", "data", "analytics",
    # General
    "remote", "agile", "scrum",
}

# Skill categories for better organization
SKILL_CATEGORIES = {
    "frontend": ["react", "vue", "angular", "svelte", "next.js", "nuxt", "typescript", "javascript", "html", "css", "tailwind", "redux", "webpack", "vite"],
    "backend": ["python", "node.js", "django", "fastapi", "flask", "express", "nestjs", "java", "spring", "go", "rust", "ruby", "rails", "php", "laravel"],
    "database": ["postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "cassandra", "sqlite"],
    "cloud": ["aws", "gcp", "azure", "docker", "kubernetes", "terraform", "serverless", "lambda"],
    "ai_ml": ["ai", "machine learning", "deep learning", "tensorflow", "pytorch", "openai", "llm", "nlp", "computer vision"],
    "devops": ["docker", "kubernetes", "ci/cd", "jenkins", "github actions", "gitlab", "ansible", "terraform"],
    "testing": ["jest", "pytest", "mocha", "cypress", "selenium", "unit testing", "integration testing", "e2e"],
    "mobile": ["react native", "flutter", "ios", "android", "swift", "kotlin"],
}


def extract_skills_from_text(text: str) -> set:
    """Extract skill keywords from job description text."""
    text_lower = text.lower()
    found_skills = set()
    
    # Common tech skills pattern
    skill_patterns = [
        r'\b(python|javascript|typescript|java|golang|rust|ruby|php|c\+\+|c#)\b',
        r'\b(react|vue|angular|svelte|next\.?js|nuxt)\b',
        r'\b(node\.?js|express|nestjs|django|flask|fastapi|spring|rails|laravel)\b',
        r'\b(postgresql|mysql|mongodb|redis|elasticsearch|dynamodb)\b',
        r'\b(aws|gcp|azure|docker|kubernetes|terraform)\b',
        r'\b(ai|machine learning|deep learning|tensorflow|pytorch|openai|llm|nlp)\b',
        r'\b(rest|graphql|api|microservices)\b',
        r'\b(git|agile|scrum|ci/cd|devops)\b',
        r'\b(tailwind|css|html|webpack|vite)\b',
        r'\b(jest|pytest|mocha|cypress|selenium|testing)\b',
        r'\b(rabbitmq|kafka|celery|redis)\b',
        r'\b(linux|unix|bash|shell)\b',
    ]
    
    for pattern in skill_patterns:
        matches = re.findall(pattern, text_lower)
        found_skills.update(matches)
    
    return found_skills


def analyze_job_postings() -> dict:
    """Analyze all job postings for skill frequency."""
    if not JOB_POSTINGS_CSV.exists():
        print(f"ERROR: {JOB_POSTINGS_CSV} not found")
        return {}
    
    skill_counts = Counter()
    total_jobs = 0
    
    with open(JOB_POSTINGS_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_jobs += 1
            # Combine all text fields
            text = f"{row.get('title', '')} {row.get('tags', '')} {row.get('keyword', '')}"
            skills = extract_skills_from_text(text)
            for skill in skills:
                skill_counts[skill] += 1
    
    return {
        "total_jobs": total_jobs,
        "skill_counts": dict(skill_counts.most_common(100)),
    }


def analyze_matched_jobs() -> dict:
    """Analyze matched jobs for skill requirements."""
    if not MATCHED_CSV.exists():
        print(f"WARNING: {MATCHED_CSV} not found")
        return {}
    
    skill_counts = Counter()
    total_jobs = 0
    
    with open(MATCHED_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_jobs += 1
            text = f"{row.get('title', '')} {row.get('tags', '')} {row.get('keyword', '')} {row.get('_matched', '')}"
            skills = extract_skills_from_text(text)
            for skill in skills:
                skill_counts[skill] += 1
    
    return {
        "total_jobs": total_jobs,
        "skill_counts": dict(skill_counts.most_common(50)),
    }


def find_skills_gaps(job_skills: dict, your_skills: set) -> list:
    """Find skills in demand that you don't have."""
    gaps = []
    for skill, count in job_skills.items():
        if skill not in your_skills:
            gaps.append({
                "skill": skill,
                "demand_count": count,
                "category": get_skill_category(skill),
            })
    
    # Sort by demand
    gaps.sort(key=lambda x: x["demand_count"], reverse=True)
    return gaps


def get_skill_category(skill: str) -> str:
    """Get category for a skill."""
    skill_lower = skill.lower()
    for category, skills_list in SKILL_CATEGORIES.items():
        if skill_lower in [s.lower() for s in skills_list]:
            return category
    return "other"


def generate_learning_recommendations(gaps: list, top_n: int = 10) -> list:
    """Generate actionable learning recommendations."""
    recommendations = []
    
    for gap in gaps[:top_n]:
        skill = gap["skill"]
        category = gap["category"]
        demand = gap["demand_count"]
        
        # Learning resources based on skill type
        resources = get_learning_resources(skill, category)
        
        recommendations.append({
            "skill": skill,
            "category": category,
            "demand": demand,
            "priority": "HIGH" if demand > 20 else "MEDIUM" if demand > 10 else "LOW",
            "resources": resources,
            "estimated_hours": estimate_learning_time(skill, category),
        })
    
    return recommendations


def get_learning_resources(skill: str, category: str) -> list:
    """Get learning resources for a skill."""
    resources = {
        # Frontend
        "angular": ["Angular Official Tutorial", "Angular University", "Frontend Masters"],
        "svelte": ["Svelte Tutorial", "SvelteKit Docs", "Level Up Svelte"],
        "nuxt": ["Nuxt.js Docs", "Vue Mastery Nuxt Course"],
        
        # Backend
        "go": ["Go by Example", "A Tour of Go", "Go Programming Language Book"],
        "rust": ["The Rust Book", "Rust by Example", "Rustlings"],
        "java": ["Java Official Tutorials", "Spring Boot Guide", "Baeldung"],
        "ruby": ["Ruby in Twenty Minutes", "Ruby on Rails Tutorial"],
        
        # Database
        "mongodb": ["MongoDB University", "MongoDB Official Docs"],
        "elasticsearch": ["Elasticsearch Definitive Guide", "Elastic Official Training"],
        
        # Cloud
        "azure": ["Microsoft Learn Azure", "Azure Fundamentals"],
        "kubernetes": ["Kubernetes Docs", "Kubernetes the Hard Way", "CKA Certification"],
        
        # AI/ML
        "tensorflow": ["TensorFlow Official Tutorial", "Deep Learning with Python"],
        "pytorch": ["PyTorch Official Tutorials", "Deep Learning with PyTorch"],
        "nlp": ["Hugging Face Course", "NLTK Book", "SpaCy Course"],
        
        # DevOps
        "terraform": ["Terraform Official Docs", "Terraform Up & Running"],
        "ansible": ["Ansible for DevOps Book", "Red Hat Ansible Training"],
        
        # Testing
        "cypress": ["Cypress Official Docs", "Cypress Testing Strategies"],
        "selenium": ["Selenium Official Docs", "Automated Testing with Selenium"],
    }
    
    return resources.get(skill.lower(), [f"Search: '{skill} tutorial'", f"Check: {skill}.com official docs"])


def estimate_learning_time(skill: str, category: str) -> str:
    """Estimate learning time for a skill."""
    time_estimates = {
        "frontend": "20-40 hours",
        "backend": "30-60 hours",
        "database": "15-30 hours",
        "cloud": "20-50 hours",
        "ai_ml": "40-80 hours",
        "devops": "25-50 hours",
        "testing": "10-20 hours",
        "mobile": "30-60 hours",
    }
    return time_estimates.get(category, "20-40 hours")


def build_trends_json(
    job_analysis: dict,
    matched_analysis: dict,
    gaps: list,
    recommendations: list,
    category_counts: Counter,
    category_demand: Counter,
) -> dict:
    """Build a structured JSON snapshot of skills trends for dashboard consumption."""
    all_skills = job_analysis.get("skill_counts", {})
    your_set = YOUR_SKILLS

    # Trending = top 20 by demand across all postings
    trending = [
        {"skill": s, "demand": c, "have_it": s in your_set}
        for s, c in list(all_skills.items())[:20]
    ]

    # Missing = skills in demand you don't have
    missing = [
        {"skill": g["skill"], "demand": g["demand_count"], "category": g["category"]}
        for g in gaps[:20]
    ]

    # Category summary
    cat_summary = [
        {"category": cat, "gap_count": category_counts.get(cat, 0), "total_demand": category_demand.get(cat, 0)}
        for cat in category_counts
    ]
    cat_summary.sort(key=lambda x: x["total_demand"], reverse=True)

    return {
        "generated_at": datetime.now().isoformat(),
        "total_jobs_analyzed": job_analysis.get("total_jobs", 0),
        "total_matched_jobs": matched_analysis.get("total_jobs", 0),
        "total_skill_gaps": len(gaps),
        "trending_skills": trending,
        "missing_skills": missing,
        "your_skills": sorted(your_set),
        "category_breakdown": cat_summary,
        "recommendations": [
            {
                "skill": r["skill"],
                "category": r["category"],
                "demand": r["demand"],
                "priority": r["priority"],
                "estimated_hours": r["estimated_hours"],
                "top_resource": r["resources"][0] if r["resources"] else "",
            }
            for r in recommendations
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Skills Gap Analyzer")
    parser.add_argument("--top", type=int, default=15, help="Show top N skill gaps")
    parser.add_argument("--output", default="", help="Save full report to JSON file")
    parser.add_argument("--json-output", action="store_true", help="Save skills_trends.json for dashboard consumption")
    parser.add_argument("--send-telegram", action="store_true", help="Send report via Telegram")
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"  SKILLS GAP ANALYZER")
    print(f"{'='*80}\n")
    
    # Analyze job postings
    print("Analyzing job postings...")
    job_analysis = analyze_job_postings()
    if not job_analysis:
        return
    
    print(f"  Analyzed {job_analysis['total_jobs']} jobs")
    
    # Analyze matched jobs
    print("\nAnalyzing matched jobs...")
    matched_analysis = analyze_matched_jobs()
    if matched_analysis:
        print(f"  Analyzed {matched_analysis['total_jobs']} matched jobs")
    
    # Find skill gaps
    print("\nFinding skill gaps...")
    all_job_skills = {**job_analysis.get("skill_counts", {}), **matched_analysis.get("skill_counts", {})}
    gaps = find_skills_gaps(all_job_skills, YOUR_SKILLS)
    
    print(f"  Found {len(gaps)} skills in demand that you don't have")
    
    # Generate recommendations
    print("\nGenerating learning recommendations...")
    recommendations = generate_learning_recommendations(gaps, top_n=args.top)
    
    # Display results
    print(f"\n{'='*80}")
    print(f"  TOP {len(recommendations)} SKILL GAPS & RECOMMENDATIONS")
    print(f"{'='*80}\n")
    
    for i, rec in enumerate(recommendations, 1):
        priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}[rec["priority"]]
        print(f"{i:2d}. {priority_icon} {rec['skill'].upper()}")
        print(f"    Category: {rec['category']}")
        print(f"    Demand: {rec['demand']} jobs require this")
        print(f"    Priority: {rec['priority']}")
        print(f"    Estimated time: {rec['estimated_hours']}")
        print(f"    Resources:")
        for res in rec["resources"][:3]:
            print(f"      • {res}")
        print()
    
    # Summary by category
    print(f"{'='*80}")
    print(f"  SKILL GAPS BY CATEGORY")
    print(f"{'='*80}\n")
    
    category_counts = Counter()
    category_demand = Counter()
    for gap in gaps:
        category_counts[gap["category"]] += 1
        category_demand[gap["category"]] += gap["demand_count"]
    
    for category, count in category_counts.most_common():
        total_demand = category_demand[category]
        print(f"  {category:15s}: {count:3d} skills | Total demand: {total_demand:4d} jobs")
    
    # Save report if requested
    if args.output:
        report = {
            "summary": {
                "total_jobs_analyzed": job_analysis["total_jobs"],
                "total_matched_jobs": matched_analysis.get("total_jobs", 0),
                "total_skill_gaps": len(gaps),
            },
            "skill_gaps": gaps[:args.top],
            "recommendations": recommendations,
            "category_summary": dict(category_counts),
        }
        
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✓ Report saved to {args.output}")

    # Save skills trends JSON for dashboard
    if args.json_output:
        trends = build_trends_json(
            job_analysis, matched_analysis, gaps, recommendations, category_counts, category_demand
        )
        trends_file = DATA_DIR / "skills_trends.json"
        with open(trends_file, "w") as f:
            json.dump(trends, f, indent=2)
        print(f"\n✓ Skills trends saved: {trends_file}")
    
    print(f"\n{'='*80}")
    print(f"  ACTION PLAN")
    print(f"{'='*80}\n")
    
    high_priority = [r for r in recommendations if r["priority"] == "HIGH"]
    medium_priority = [r for r in recommendations if r["priority"] == "MEDIUM"]
    
    if high_priority:
        print("🔴 HIGH PRIORITY (learn these first):")
        for rec in high_priority[:5]:
            print(f"   • {rec['skill']} - {rec['demand']} jobs demand")
        print()
    
    if medium_priority:
        print("🟡 MEDIUM PRIORITY (learn these next):")
        for rec in medium_priority[:5]:
            print(f"   • {rec['skill']} - {rec['demand']} jobs demand")
        print()
    
    print("💡 TIP: Focus on 1-2 skills at a time. Start with HIGH priority skills.")
    print("   Most impactful: Learn skills that appear in 20+ job postings.\n")

    # Send Telegram notification
    if args.send_telegram:
        send_telegram_report(recommendations, gaps, category_counts)


def send_telegram_report(recommendations: list, gaps: list, category_counts: Counter):
    """Send skills gap report via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    high = [r for r in recommendations if r["priority"] == "HIGH"]
    medium = [r for r in recommendations if r["priority"] == "MEDIUM"]

    lines = [
        "📊 <b>SKILLS GAP ANALYSIS</b>",
        "",
        f"Found <b>{len(gaps)}</b> skill gaps in job market",
        "",
    ]

    if high:
        lines.append("🔴 <b>HIGH PRIORITY:</b>")
        for r in high[:5]:
            lines.append(f"  • {r['skill'].upper()} — {r['demand']} jobs")
        lines.append("")

    if medium:
        lines.append("🟡 <b>MEDIUM PRIORITY:</b>")
        for r in medium[:5]:
            lines.append(f"  • {r['skill'].upper()} — {r['demand']} jobs")
        lines.append("")

    lines.append("📂 <b>BY CATEGORY:</b>")
    for cat, count in category_counts.most_common(5):
        lines.append(f"  • {cat}: {count} skills")
    lines.append("")
    lines.append("💡 Focus on 1-2 HIGH priority skills first")

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
        print("✓ Telegram skills gap report sent")
        return True
    except Exception as e:
        print(f"ERROR: Telegram send failed: {e}")
        return False


if __name__ == "__main__":
    main()
