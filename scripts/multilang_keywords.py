#!/usr/bin/env python3
"""
Multi-Language Job Matching - Extends keyword list for Thai and Japanese markets.
Use this to scrape jobs in multiple languages.

Usage:
    python3 multilang_keywords.py --lang thai
    python3 multilang_keywords.py --lang japanese
    python3 multilang_keywords.py --lang all
    
    # Then use with main scraper:
    python3 scrape_job_postings.py --keywords "$(python3 multilang_keywords.py --print --lang thai)"
"""

import argparse
import sys
from pathlib import Path

# English keywords (default)
ENGLISH_KEYWORDS = [
    "python", "react", "next.js", "typescript", "full-stack", "developer",
    "AI engineer", "backend", "frontend", "node.js", "FastAPI", "Django",
    "software engineer", "web developer", "fullstack", "devops",
]

# Thai keywords for Bangkok/Thailand market
THAI_KEYWORDS = [
    "โปรแกรมเมอร์",        # Programmer
    "นักพัฒนา",           # Developer
    "พัฒนาซอฟต์แวร์",     # Software Development
    "เว็บ",              # Web
    "Python",
    "React",
    "Full-Stack",
    "Backend",
    "Frontend",
    "AI",
    "วิศวกรซอฟต์แวร์",    # Software Engineer
    "นักเขียนโปรแกรม",    # Programmer (formal)
    "พัฒนาเว็บ",          # Web Developer
    "ระบบ",              # System
    "API",
    "Database",
    "ฐานข้อมูล",          # Database (Thai)
]

# Japanese keywords for Tokyo/Japan market
JAPANESE_KEYWORDS = [
    "エンジニア",          # Engineer
    "プログラマー",        # Programmer
    "開発者",             # Developer
    "ソフトウェア開発",    # Software Development
    "Web開発",            # Web Development
    "Python",
    "React",
    "TypeScript",
    "フルスタック",        # Full-Stack
    "バックエンド",        # Backend
    "フロントエンド",      # Frontend
    "AIエンジニア",        # AI Engineer
    "システムエンジニア",  # System Engineer
    "インフラ",           # Infrastructure
    "クラウド",           # Cloud
    "DevOps",
]

# Chinese keywords for Greater China market
CHINESE_KEYWORDS = [
    "工程师",             # Engineer
    "程序员",             # Programmer
    "开发者",             # Developer
    "软件开发",           # Software Development
    "全栈",              # Full-Stack
    "后端",              # Backend
    "前端",              # Frontend
    "Python",
    "React",
    "TypeScript",
    "AI",
    "Web开发",           # Web Development
]

# Korean keywords for South Korea market
KOREAN_KEYWORDS = [
    "엔지니어",           # Engineer
    "개발자",             # Developer
    "프로그래머",         # Programmer
    "소프트웨어",         # Software
    "웹개발",             # Web Development
    "풀스택",            # Full-Stack
    "백엔드",            # Backend
    "프론트엔드",         # Frontend
    "Python",
    "React",
    "TypeScript",
]

LANGUAGE_MAP = {
    "en": ENGLISH_KEYWORDS,
    "english": ENGLISH_KEYWORDS,
    "th": THAI_KEYWORDS,
    "thai": THAI_KEYWORDS,
    "ja": JAPANESE_KEYWORDS,
    "japanese": JAPANESE_KEYWORDS,
    "zh": CHINESE_KEYWORDS,
    "chinese": CHINESE_KEYWORDS,
    "ko": KOREAN_KEYWORDS,
    "korean": KOREAN_KEYWORDS,
}


def get_keywords_for_language(lang: str) -> list:
    """Get keywords for specified language."""
    lang_lower = lang.lower()
    return LANGUAGE_MAP.get(lang_lower, ENGLISH_KEYWORDS)


def get_all_keywords() -> list:
    """Get all keywords from all languages."""
    all_kw = set()
    for keywords in LANGUAGE_MAP.values():
        all_kw.update(keywords)
    return sorted(list(all_kw))


def print_keywords(keywords: list, separator: str = ","):
    """Print keywords in format suitable for command-line use."""
    print(separator.join(keywords))


def main():
    parser = argparse.ArgumentParser(description="Multi-Language Job Keywords")
    parser.add_argument("--lang", default="en", help="Language code (en, th, ja, zh, ko, all)")
    parser.add_argument("--print", action="store_true", help="Print keywords for use with scraper")
    parser.add_argument("--separator", default=",", help="Separator for printed keywords")
    parser.add_argument("--list-langs", action="store_true", help="List available languages")
    args = parser.parse_args()
    
    if args.list_langs:
        print("\nAvailable languages:")
        print("  en, english  - English (default)")
        print("  th, thai     - Thai (Bangkok/Thailand)")
        print("  ja, japanese - Japanese (Tokyo/Japan)")
        print("  zh, chinese  - Chinese (Greater China)")
        print("  ko, korean   - Korean (South Korea)")
        print("  all          - All languages combined")
        return
    
    if args.lang == "all":
        keywords = get_all_keywords()
    else:
        keywords = get_keywords_for_language(args.lang)
    
    if not keywords:
        print(f"ERROR: No keywords found for language: {args.lang}")
        print("  Available: en, th, ja, zh, ko, all")
        return
    
    if args.print:
        print_keywords(keywords, args.separator)
    else:
        print(f"\n{'='*80}")
        print(f"  MULTI-LANGUAGE KEYWORDS")
        print(f"{'='*80}\n")
        
        lang_name = {
            "en": "English", "th": "Thai", "ja": "Japanese",
            "zh": "Chinese", "ko": "Korean", "all": "All Languages"
        }.get(args.lang.lower(), args.lang)
        
        print(f"Language: {lang_name}")
        print(f"Keywords ({len(keywords)}):\n")
        
        for i, kw in enumerate(keywords, 1):
            print(f"  {i:2d}. {kw}")
        
        print(f"\n{'='*80}")
        print(f"  USAGE")
        print(f"{'='*80}\n")
        print(f"  # Use with main scraper:")
        print(f"  python3 scrape_job_postings.py --keywords \"$(python3 multilang_keywords.py --print --lang {args.lang})\"")
        print()
        print(f"  # Or manually:")
        print(f"  python3 scrape_job_postings.py --keywords \"{','.join(keywords[:5])}\"")
        print()


if __name__ == "__main__":
    main()
