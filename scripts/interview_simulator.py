#!/usr/bin/env python3
"""
AI Interview Simulator — Mock interview bot trained on company intel + JD.
Records answers and gives AI-powered feedback with scoring.

Usage:
    python interview_simulator.py --job-id <id> --start
    python interview_simulator.py --job-id <id> --answer "..."
    python interview_simulator.py --job-id <id> --feedback
    python interview_simulator.py --list
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
MATCHED_JOBS_CSV = DATA_DIR / "matched_jobs.csv"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
COMPANY_INTEL_DIR = DATA_DIR / "company_intel"
SESSIONS_DIR = DATA_DIR / "interview_sessions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# Question categories with templates
QUESTION_CATEGORIES = {
    "technical": [
        "Explain your experience with {skill}. What was the most challenging project?",
        "How would you design a system that handles {skill} at scale?",
        "What's your approach to debugging a complex issue in {skill}?",
        "Describe a technical architecture decision you made involving {skill}.",
        "How do you stay current with {skill} developments?",
    ],
    "behavioral": [
        "Tell me about a time you had a disagreement with a teammate. How did you handle it?",
        "Describe a situation where you had to learn something new quickly.",
        "Tell me about a project where you had to balance technical debt with delivery.",
        "Give an example of when you went above and beyond on a project.",
        "Describe a time you received critical feedback. What did you do?",
    ],
    "company_fit": [
        "Why are you interested in working at {company}?",
        "What do you know about {company}'s products and recent developments?",
        "How do your values align with {company}'s mission?",
        "What unique perspective would you bring to the {company} team?",
        "Where do you see yourself in 3 years, and how does {company} fit into that?",
    ],
    "role_specific": [
        "What interests you most about this specific role?",
        "How does your experience match the key requirements of this position?",
        "What would you focus on in your first 30 days in this role?",
        "What questions do you have about the team and this position?",
        "How would you measure success in this role?",
    ],
}


def ai_call(messages, temperature=0.7):
    """Call OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature, max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  AI error: {e}")
        return None


def load_job(job_id):
    """Load job details from matched jobs."""
    if not MATCHED_JOBS_CSV.exists():
        return None
    with open(MATCHED_JOBS_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") == job_id or row.get("job_id") == job_id:
                return row
    return None


def load_company_intel(company_name):
    """Load company intel report."""
    if not company_name or not COMPANY_INTEL_DIR.exists():
        return None
    for f in COMPANY_INTEL_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if company_name.lower() in data.get("company", "").lower():
                return data
        except:
            continue
    return None


def load_session(job_id):
    """Load or create interview session."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / f"{job_id}.json"

    if session_file.exists():
        return json.loads(session_file.read_text())

    return {
        "job_id": job_id,
        "started_at": datetime.now().isoformat(),
        "questions_asked": [],
        "answers": [],
        "scores": {},
        "category_index": {cat: 0 for cat in QUESTION_CATEGORIES},
        "total_questions": 0,
    }


def save_session(session):
    """Save interview session."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / f"{session['job_id']}.json"
    session_file.write_text(json.dumps(session, indent=2, default=str))


def generate_question(session, job, category=None):
    """Generate next interview question using AI."""
    if category:
        cats = [category]
    else:
        # Rotate through categories
        cats = list(QUESTION_CATEGORIES.keys())
        idx = session["total_questions"] % len(cats)
        category = cats[idx]

    templates = QUESTION_CATEGORIES[category]
    cat_idx = session["category_index"].get(category, 0)
    template = templates[cat_idx % len(templates)]

    # Fill in placeholders
    skills = []
    if job:
        skills = [s.strip() for s in (job.get("skills") or job.get("title", ""))[:100].split(",") if s.strip()]
    skill = skills[0] if skills else "modern web technologies"
    company = job.get("company", "our company") if job else "our company"

    question = template.format(skill=skill, company=company)

    # Use AI to customize the question further
    if OPENROUTER_API_KEY and job:
        context = f"Job: {job.get('title', '')} at {job.get('company', '')}. Skills: {job.get('skills', '')[:200]}"
        ai_q = ai_call([
            {"role": "system", "content": "You are a senior technical interviewer. Generate ONE specific, challenging interview question. Return ONLY the question text."},
            {"role": "user", "content": f"Context: {context}\nCategory: {category}\nTemplate: {template}\n\nGenerate a specific, customized interview question based on this context. Make it feel natural and conversational."}
        ], temperature=0.8)
        if ai_q:
            question = ai_q.strip()

    return question, category


def score_answer(question, answer, category, job=None):
    """Score an answer using AI (1-10 scale with feedback)."""
    if not OPENROUTER_API_KEY:
        return {"score": 7, "feedback": "AI scoring unavailable. Answer recorded.", "strengths": ["Recorded"], "improvements": ["Review when AI is available"]}

    context = ""
    if job:
        context = f"Job: {job.get('title', '')} at {job.get('company', '')}"

    result = ai_call([
        {"role": "system", "content": """You are an expert interview coach. Score the candidate's answer on a scale of 1-10.
Return JSON: {"score": N, "feedback": "...", "strengths": ["..."], "improvements": ["..."]}
Be honest but constructive. Focus on content quality, specificity, and relevance."""},
        {"role": "user", "content": f"Context: {context}\nCategory: {category}\nQuestion: {question}\n\nCandidate's Answer: {answer}"}
    ], temperature=0.3)

    if result:
        try:
            # Try to parse JSON from response
            result = result.strip()
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            return json.loads(result)
        except:
            return {"score": 5, "feedback": result[:200], "strengths": ["Answer provided"], "improvements": ["Could be more specific"]}

    return {"score": 0, "feedback": "Failed to get AI feedback", "strengths": [], "improvements": []}


def generate_full_feedback(session, job=None):
    """Generate comprehensive interview feedback."""
    if not session["answers"]:
        return "No answers recorded yet. Use --start first."

    total_score = sum(s.get("score", 0) for s in session["scores"].values() if isinstance(s, dict))
    max_score = len(session["scores"]) * 10
    avg_score = total_score / max(len(session["scores"]), 1)

    report = f"""# Interview Simulation Report
**Date:** {session['started_at'][:10]}
**Job ID:** {session['job_id']}
**Questions:** {session['total_questions']}
**Overall Score:** {avg_score:.1f}/10

## Score Breakdown
"""
    for i, (q, a, s) in enumerate(zip(session["questions_asked"], session["answers"], session.get("scores", {}).values())):
        if isinstance(s, dict):
            report += f"\n### Q{i+1}: {q[:80]}...\n"
            report += f"**Score:** {s.get('score', '?')}/10\n"
            report += f"**Feedback:** {s.get('feedback', 'N/A')}\n"
            if s.get("strengths"):
                report += f"**Strengths:** {', '.join(s['strengths'])}\n"
            if s.get("improvements"):
                report += f"**Improve:** {', '.join(s['improvements'])}\n"

    # AI overall assessment
    if OPENROUTER_API_KEY:
        summary = ai_call([
            {"role": "system", "content": "You are an interview coach. Provide a brief overall assessment and top 3 tips for improvement."},
            {"role": "user", "content": f"Candidate completed {session['total_questions']} questions with average score {avg_score:.1f}/10. Provide overall assessment and actionable tips."}
        ], temperature=0.5)
        if summary:
            report += f"\n## Overall Assessment\n{summary}\n"

    return report


def list_sessions():
    """List all interview sessions."""
    if not SESSIONS_DIR.exists():
        print("No interview sessions yet.")
        return

    sessions = sorted(SESSIONS_DIR.glob("*.json"))
    if not sessions:
        print("No interview sessions yet.")
        return

    print(f"\n{'Job ID':<40} {'Questions':<10} {'Avg Score':<10} {'Date'}")
    print("-" * 80)
    for sf in sessions:
        try:
            s = json.loads(sf.read_text())
            total = s.get("total_questions", 0)
            scores = [v.get("score", 0) for v in s.get("scores", {}).values() if isinstance(v, dict)]
            avg = sum(scores) / len(scores) if scores else 0
            print(f"{s['job_id']:<40} {total:<10} {avg:<10.1f} {s['started_at'][:10]}")
        except:
            continue


def main():
    parser = argparse.ArgumentParser(description="AI Interview Simulator")
    parser.add_argument("--job-id", help="Job ID to practice for")
    parser.add_argument("--start", action="store_true", help="Start new session")
    parser.add_argument("--question", action="store_true", help="Get next question")
    parser.add_argument("--answer", help="Submit answer to current question")
    parser.add_argument("--category", choices=["technical", "behavioral", "company_fit", "role_specific"])
    parser.add_argument("--feedback", action="store_true", help="Get full feedback report")
    parser.add_argument("--list", action="store_true", help="List sessions")
    args = parser.parse_args()

    if args.list:
        list_sessions()
        return

    if args.feedback:
        if not args.job_id:
            print("Error: --job-id required for --feedback")
            return
        session = load_session(args.job_id)
        job = load_job(args.job_id)
        report = generate_full_feedback(session, job)
        # Save report
        report_dir = DATA_DIR / "interview_prep"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"simulation_{args.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_file.write_text(report)
        print(report)
        print(f"\nReport saved: {report_file}")
        return

    if args.start:
        if not args.job_id:
            print("Error: --job-id required for --start")
            return
        job = load_job(args.job_id)
        session = {
            "job_id": args.job_id,
            "started_at": datetime.now().isoformat(),
            "questions_asked": [],
            "answers": [],
            "scores": {},
            "category_index": {cat: 0 for cat in QUESTION_CATEGORIES},
            "total_questions": 0,
        }
        save_session(session)
        print(f"Interview session started for job: {args.job_id}")
        if job:
            print(f"Position: {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}")
        print(f"\nUse --question to get your first question.")
        return

    if args.question:
        if not args.job_id:
            print("Error: --job-id required")
            return
        session = load_session(args.job_id)
        job = load_job(args.job_id)
        question, category = generate_question(session, job, args.category)
        session["questions_asked"].append(question)
        session["total_questions"] += 1
        session["category_index"][category] = session["category_index"].get(category, 0) + 1
        save_session(session)
        print(f"\n[{category.upper()}] Question #{session['total_questions']}:")
        print(f"\n  {question}\n")
        print(f"Submit your answer with: --answer \"your answer\"")
        return

    if args.answer:
        if not args.job_id:
            print("Error: --job-id required")
            return
        session = load_session(args.job_id)
        if not session["questions_asked"]:
            print("No question asked yet. Use --question first.")
            return

        job = load_job(args.job_id)
        last_question = session["questions_asked"][-1]
        # Determine category from last question
        category = "general"
        for cat in QUESTION_CATEGORIES:
            if any(kw in last_question.lower() for kw in ["design", "code", "technical", "system", "debug"]):
                category = "technical"
                break
            elif any(kw in last_question.lower() for kw in ["time you", "tell me about", "describe a situation"]):
                category = "behavioral"
                break

        session["answers"].append(args.answer)
        print("Scoring your answer...")
        score = score_answer(last_question, args.answer, category, job)
        session["scores"][str(session["total_questions"])] = score
        save_session(session)

        print(f"\nScore: {score.get('score', '?')}/10")
        print(f"Feedback: {score.get('feedback', 'N/A')}")
        if score.get("strengths"):
            print(f"Strengths: {', '.join(score['strengths'])}")
        if score.get("improvements"):
            print(f"Improve: {', '.join(score['improvements'])}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
