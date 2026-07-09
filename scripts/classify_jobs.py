#!/usr/bin/env python3
"""
Auto-classify jobs in apply_tracker.csv with work_type, visa_sponsor, job_type, experience_level, country.

Reads existing tracker, adds new columns, and classifies based on title/note/URL patterns.

Usage:
    python3 scripts/classify_jobs.py              # Dry run - show classification stats
    python3 scripts/classify_jobs.py --apply      # Actually update the tracker
"""

import argparse
import csv
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"

# Classification patterns
WORK_TYPE_PATTERNS = {
    "WFA": [
        r"\bremote\b", r"\bwork from anywhere\b", r"\banywhere\b", r"\b100%\s*remote\b",
        r"\bfully\s*remote\b", r"\bglobally\s*remote\b", r"\bworldwide\b"
    ],
    "WFH": [
        r"\bremote\s*[-–]?\s*(us|europe|asia|uk|de|nl)\b", r"\bremote\s*work\b",
        r"\bwork\s*from\s*home\b", r"\bwfh\b", r"\bremote\s*position\b"
    ],
    "Hybrid": [
        r"\bhybrid\b", r"\b\d+[-–]?\d*\s*days?\s*(in\s*office|on[-–]site)\b",
        r"\bflexible\s*hybrid\b", r"\bpartially\s*remote\b"
    ],
    "WFO": [
        r"\bon[-–]site\b", r"\bonsite\b", r"\bin[-–]person\b", r"\boffice[-–]based\b",
        r"\brelocation\s*required\b", r"\bwork\s*from\s*office\b"
    ]
}

VISA_PATTERNS = [
    r"\bvisa\s*sponsor(ship|ed)?\b", r"\bsponsor(ship|ed)?\s*visa\b",
    r"\brelocation\s*(package|support|assistance)\b", r"\bwork\s*permit\b",
    r"\bvisa\s*(support|assistance)\b", r"\btier\s*2\b", r"\bskilled\s*worker\b"
]

JOB_TYPE_PATTERNS = {
    "Full-time": [
        r"\bfull[-–]?time\b", r"\bpermanent\b", r"\bregular\b"
    ],
    "Contract": [
        r"\bcontract\b", r"\btemporary\b", r"\btemp\b", r"\b6[-–]month\b",
        r"\b12[-–]month\b", r"\bfixed[-–]term\b"
    ],
    "Freelance": [
        r"\bfreelance\b", r"\bindependent\s*contractor\b", r"\bgig\b"
    ],
    "Part-time": [
        r"\bpart[-–]?time\b", r"\b\d+[-–]?\d*\s*hours?\b"
    ]
}

EXPERIENCE_PATTERNS = {
    "Junior": [
        r"\bjunior\b", r"\bentry[-–]?level\b", r"\b0[-–]2\s*years?\b",
        r"\bnew\s*grad\b", r"\bgraduate\b", r"\bintern(ship)?\b"
    ],
    "Mid": [
        r"\bmid[-–]?level\b", r"\b3[-–]5\s*years?\b", r"\bmid[\s-]career\b"
    ],
    "Senior": [
        r"\bsenior\b", r"\bsr\b", r"\b5[-–]10\s*years?\b", r"\blead\b",
        r"\bstaff\b", r"\bprincipal\b", r"\b10\+\s*years?\b"
    ]
}

# Country detection (from URL or note)
COUNTRY_PATTERNS = {
    "TH": [r"\bthailand\b", r"\bbangkok\b", r"\.co\.th\b", r"\bthai\b"],
    "US": [r"\bunited\s*states\b", r"\busa\b", r"\bca\b", r"\bny\b", r"\bsf\b", r"\bla\b", r"\.com\b"],
    "UK": [r"\bunited\s*kingdom\b", r"\buk\b", r"\blondon\b", r"\.co\.uk\b"],
    "DE": [r"\bgermany\b", r"\bberlin\b", r"\bmunich\b", r"\.de\b"],
    "NL": [r"\bnetherlands\b", r"\bdutch\b", r"\bamsterdam\b", r"\.nl\b"],
    "SG": [r"\bsingapore\b", r"\.sg\b"],
    "AU": [r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\.au\b"],
    "CA": [r"\bcanada\b", r"\btoronto\b", r"\.ca\b"],
    "JP": [r"\bjapan\b", r"\btokyo\b", r"\.jp\b"],
    "Remote": [r"\bremote\b", r"\banywhere\b", r"\bworldwide\b"]
}


def classify_work_type(text: str) -> str:
    """Classify work location type from text."""
    text_lower = text.lower()
    
    for work_type, patterns in WORK_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return work_type
    
    # Default based on common patterns
    if "remote" in text_lower:
        return "WFA"
    
    return ""


def classify_visa_sponsor(text: str) -> str:
    """Check if job mentions visa sponsorship."""
    text_lower = text.lower()
    
    for pattern in VISA_PATTERNS:
        if re.search(pattern, text_lower):
            return "Yes"
    
    return ""


def classify_job_type(text: str) -> str:
    """Classify employment type."""
    text_lower = text.lower()
    
    for job_type, patterns in JOB_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return job_type
    
    # Default to Full-time if no contract/freelance mention
    return "Full-time"


def classify_experience(text: str) -> str:
    """Classify experience level."""
    text_lower = text.lower()
    
    for level, patterns in EXPERIENCE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return level
    
    # Default to Mid if no mention
    return ""


def classify_country(text: str, url: str = "") -> str:
    """Classify target country."""
    combined = (text + " " + url).lower()
    
    # Check Thai first (priority)
    for pattern in COUNTRY_PATTERNS["TH"]:
        if re.search(pattern, combined):
            return "TH"
    
    # Check other countries
    for country, patterns in COUNTRY_PATTERNS.items():
        if country == "TH":
            continue
        for pattern in patterns:
            if re.search(pattern, combined):
                return country if country != "Remote" else "Remote"
    
    return ""


def main():
    parser = argparse.ArgumentParser(description="Auto-classify jobs in tracker")
    parser.add_argument("--apply", action="store_true", help="Update tracker file")
    args = parser.parse_args()
    
    print("=" * 70)
    print("  JOB CLASSIFIER")
    print("=" * 70)
    
    # Load tracker
    if not TRACKER_FILE.exists():
        print(f"Error: Tracker file not found: {TRACKER_FILE}")
        return
    
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    
    print(f"Loaded {len(rows)} jobs from tracker")
    
    # Check if new columns already exist
    new_cols = ["work_type", "visa_sponsor", "job_type", "experience_level", "country"]
    existing_cols = fieldnames or []
    cols_to_add = [c for c in new_cols if c not in existing_cols]
    
    if not cols_to_add:
        print("All classification columns already exist")
    else:
        print(f"Adding columns: {cols_to_add}")
    
    # Classify each job
    classified = []
    stats = {col: {} for col in new_cols}
    
    for row in rows:
        # Build text from title + note
        title = row.get("title", "")
        note = row.get("note", "")
        url = row.get("url", "")
        text = f"{title} {note}"
        
        # Add new columns if missing
        for col in cols_to_add:
            row[col] = ""
        
        # Classify
        if "work_type" in cols_to_add or not row.get("work_type"):
            row["work_type"] = classify_work_type(text)
        if "visa_sponsor" in cols_to_add or not row.get("visa_sponsor"):
            row["visa_sponsor"] = classify_visa_sponsor(text)
        if "job_type" in cols_to_add or not row.get("job_type"):
            row["job_type"] = classify_job_type(text)
        if "experience_level" in cols_to_add or not row.get("experience_level"):
            row["experience_level"] = classify_experience(text)
        if "country" in cols_to_add or not row.get("country"):
            row["country"] = classify_country(text, url)
        
        classified.append(row)
        
        # Collect stats
        for col in new_cols:
            val = row.get(col, "") or "(empty)"
            stats[col][val] = stats[col].get(val, 0) + 1
    
    # Print stats
    print("\nClassification stats:")
    for col in new_cols:
        print(f"\n  {col}:")
        for val, count in sorted(stats[col].items(), key=lambda x: -x[1])[:10]:
            print(f"    {val}: {count}")
    
    if args.apply:
        # Save updated tracker
        all_cols = existing_cols + cols_to_add
        with open(TRACKER_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_cols)
            writer.writeheader()
            writer.writerows(classified)
        
        print(f"\n✓ Updated tracker with {len(classified)} jobs")
        print(f"  Added columns: {cols_to_add}")
    else:
        print("\nDRY RUN - Use --apply to update tracker")


if __name__ == "__main__":
    main()
