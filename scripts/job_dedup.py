#!/usr/bin/env python3
"""
Job Deduplication — Detect and remove duplicate jobs across boards.

Uses multiple strategies:
  1. Exact URL match (already in scraper, but this works on existing CSV)
  2. Normalized title + company match
  3. Fuzzy title similarity (Jaccard) for same-company jobs

Usage:
    python3 job_dedup.py                    # Analyze duplicates
    python3 job_dedup.py --clean            # Remove duplicates from job_postings.csv
    python3 job_dedup.py --clean --matched  # Also clean matched_jobs.csv
    python3 job_dedup.py --report           # Generate dedup report JSON
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
JOB_POSTINGS_CSV = DATA_DIR / "job_postings.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"


def load_csv(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return list(csv.DictReader(f))


def save_csv(path: Path, rows: list, fieldnames: list):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace, decode HTML entities."""
    text = text.lower().strip()
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#x2f;|/", "/", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s/]", "", text)
    return text.strip()


def jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings (word-level)."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def find_duplicates(postings: list, similarity_threshold: float = 0.8) -> list:
    """
    Find duplicate jobs using multiple strategies.
    Returns list of (kept_index, duplicate_indices, reason) tuples.
    """
    n = len(postings)

    # Pre-compute normalized fields
    norm_titles = [normalize_text(p.get("title", "")) for p in postings]
    norm_companies = [normalize_text(p.get("company", "")) for p in postings]
    urls = [p.get("url", "") for p in postings]

    # Track which rows to remove: {index_to_remove: (kept_index, reason)}
    to_remove = {}

    # Strategy 1: Exact URL duplicates
    url_groups = defaultdict(list)
    for i, url in enumerate(urls):
        if url:
            url_groups[url].append(i)

    url_dupes = 0
    for url, indices in url_groups.items():
        if len(indices) > 1:
            # Keep first, remove rest
            for idx in indices[1:]:
                if idx not in to_remove:
                    to_remove[idx] = (indices[0], "exact_url")
                    url_dupes += 1

    # Strategy 2: Exact title + company match
    tc_groups = defaultdict(list)
    for i in range(n):
        if i in to_remove:
            continue
        key = (norm_titles[i], norm_companies[i])
        if key[0] and key[1]:
            tc_groups[key].append(i)

    tc_dupes = 0
    for key, indices in tc_groups.items():
        if len(indices) > 1:
            for idx in indices[1:]:
                if idx not in to_remove:
                    to_remove[idx] = (indices[0], "exact_title_company")
                    tc_dupes += 1

    # Strategy 3: Fuzzy title match (same company, similar title)
    company_groups = defaultdict(list)
    for i in range(n):
        if i in to_remove:
            continue
        if norm_companies[i]:
            company_groups[norm_companies[i]].append(i)

    fuzzy_dupes = 0
    for company, indices in company_groups.items():
        if len(indices) < 2:
            continue
        for a_idx in range(len(indices)):
            for b_idx in range(a_idx + 1, len(indices)):
                i = indices[a_idx]
                j = indices[b_idx]
                if i in to_remove or j in to_remove:
                    continue
                sim = jaccard_similarity(norm_titles[i], norm_titles[j])
                if sim >= similarity_threshold:
                    # Keep the one with more tags (likely more complete)
                    tags_i = len(postings[i].get("tags", "").split(","))
                    tags_j = len(postings[j].get("tags", "").split(","))
                    keep, remove = (i, j) if tags_i >= tags_j else (j, i)
                    to_remove[remove] = (keep, "fuzzy_title")
                    fuzzy_dupes += 1

    return to_remove, url_dupes, tc_dupes, fuzzy_dupes


def analyze_duplicates(postings: list):
    """Print analysis of duplicates in postings."""
    print(f"\n{'='*60}")
    print(f"  JOB DEDUPLICATION ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"\n  Total postings: {len(postings)}")

    to_remove, url_dupes, tc_dupes, fuzzy_dupes = find_duplicates(postings)

    print(f"\n  Duplicates found:")
    print(f"    • Exact URL duplicates: {url_dupes}")
    print(f"    • Exact title+company: {tc_dupes}")
    print(f"    • Fuzzy title (same company): {fuzzy_dupes}")
    print(f"    • Total to remove: {len(to_remove)}")
    print(f"    • Unique jobs remaining: {len(postings) - len(to_remove)}")

    # Show breakdown by source
    if to_remove:
        source_dupes = Counter()
        for idx, (kept, reason) in to_remove.items():
            src = postings[idx].get("source", "unknown")
            source_dupes[src] += 1
        print(f"\n  Duplicates by source:")
        for src, count in source_dupes.most_common(10):
            print(f"    • {src}: {count}")

    # Show some examples
    examples = list(to_remove.items())[:5]
    if examples:
        print(f"\n  Examples of duplicates:")
        for idx, (kept_idx, reason) in examples:
            dup = postings[idx]
            orig = postings[kept_idx]
            print(f"\n    [{reason}]")
            print(f"      KEEP: {orig['title'][:50]} @ {orig['company'][:25]} ({orig['source']})")
            print(f"      DROP: {dup['title'][:50]} @ {dup['company'][:25]} ({dup['source']})")

    print(f"\n{'='*60}\n")
    return to_remove


def clean_postings(postings: list, to_remove: dict) -> list:
    """Remove duplicate entries from postings."""
    cleaned = [p for i, p in enumerate(postings) if i not in to_remove]
    return cleaned


def clean_matched_jobs(matched: list, kept_urls: set) -> tuple:
    """Remove matched jobs whose URLs were deduped. Returns (cleaned, removed_count)."""
    cleaned = []
    removed = 0
    for m in matched:
        if m.get("url", "") in kept_urls:
            cleaned.append(m)
        else:
            removed += 1
    return cleaned, removed


def generate_report(postings: list, to_remove: dict) -> dict:
    """Generate a dedup report as JSON."""
    source_dupes = Counter()
    reason_counts = Counter()
    for idx, (kept, reason) in to_remove.items():
        src = postings[idx].get("source", "unknown")
        source_dupes[src] += 1
        reason_counts[reason] += 1

    return {
        "generated_at": datetime.now().isoformat(),
        "total_postings": len(postings),
        "duplicates_found": len(to_remove),
        "unique_jobs": len(postings) - len(to_remove),
        "by_reason": dict(reason_counts),
        "by_source": dict(source_dupes.most_common(10)),
    }


def main():
    parser = argparse.ArgumentParser(description="Job Deduplication")
    parser.add_argument("--clean", action="store_true", help="Remove duplicates from CSV")
    parser.add_argument("--matched", action="store_true", help="Also clean matched_jobs.csv")
    parser.add_argument("--report", action="store_true", help="Output dedup report JSON")
    parser.add_argument("--threshold", type=float, default=0.8, help="Fuzzy match threshold (0-1)")
    args = parser.parse_args()

    postings = load_csv(JOB_POSTINGS_CSV)
    if not postings:
        print("No job_postings.csv found")
        sys.exit(1)

    # Analyze
    to_remove, url_dupes, tc_dupes, fuzzy_dupes = find_duplicates(postings, args.threshold)

    if args.report:
        report = generate_report(postings, to_remove)
        report_path = DATA_DIR / "dedup_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        print(f"\n  ✓ Report saved: {report_path}")
        return

    # Print analysis
    analyze_duplicates(postings)

    if args.clean:
        # Clean job_postings.csv
        cleaned = clean_postings(postings, to_remove)
        fieldnames = list(postings[0].keys())
        save_csv(JOB_POSTINGS_CSV, cleaned, fieldnames)
        print(f"  ✓ Cleaned job_postings.csv: {len(postings)} → {len(cleaned)} (removed {len(to_remove)})")

        # Optionally clean matched_jobs.csv
        if args.matched:
            matched = load_csv(MATCHED_CSV)
            if matched:
                kept_urls = {p.get("url", "") for i, p in enumerate(postings) if i not in to_remove}
                cleaned_matched, removed = clean_matched_jobs(matched, kept_urls)
                matched_fields = list(matched[0].keys())
                save_csv(MATCHED_CSV, cleaned_matched, matched_fields)
                print(f"  ✓ Cleaned matched_jobs.csv: {len(matched)} → {len(cleaned_matched)} (removed {removed})")

    elif not args.report:
        print("  Run with --clean to remove duplicates")


if __name__ == "__main__":
    main()
