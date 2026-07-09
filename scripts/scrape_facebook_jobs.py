#!/usr/bin/env python3
"""
Scrape job postings from Thai Facebook groups and integrate into the pipeline.

Sources:
  - "Jobs for Thai Programmers" (FB group 647718825333067)
  - "JobThai Programmer WFH" (FB group jobthaiwfh)
  - "Job Thai Developer/Programmer" (FB group 581252398692342)

Extracts company names, hiring emails, job titles, and domains from
publicly indexed Facebook group posts, then feeds them into
contact_emails.json and apply_tracker.csv.

Usage:
    python3 scripts/scrape_facebook_jobs.py              # Dry run — show what would be added
    python3 scripts/scrape_facebook_jobs.py --apply      # Actually write to JSON + CSV
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

CONTACT_FILE = DATA_DIR / "contact_emails.json"
TRACKER_FILE = DATA_DIR / "apply_tracker.csv"

# ──────────────────────────────────────────────────────────────────────
# Extracted from public Facebook group posts (Google-indexed)
# Source: "Jobs for Thai Programmers", "JobThai Programmer WFH", etc.
# ──────────────────────────────────────────────────────────────────────

FB_COMPANIES = {
    # ── Direct employers (Thai companies) ──

    "stickydevs": {
        "domain": "stickydevs.com",
        "emails": [],
        "best": None,
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring Senior Software Engineer (Permanent / Thai National), Bangkok",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25325038133841127/",
    },
    "Notus IT Solution Co., Ltd.": {
        "domain": "no-tus.com",
        "emails": ["hr@no-tus.com"],
        "best": "hr@no-tus.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring Developer (Contract), back-end, full-stack, front-end. Also DevOps, full-stack, data engineer roles.",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25391298187215121/",
    },
    "BLOCKFINT": {
        "domain": "blockfint.com",
        "emails": [],
        "best": None,
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hot Jobs update — fintech/blockchain company, Bangkok",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25360592693619004/",
    },
    "Magnum Tech Solution": {
        "domain": "magmatechsolution.com",
        "emails": ["Thananpaphak@magmatechsolution.com"],
        "best": "Thananpaphak@magmatechsolution.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring SAP (BW and SAP Basis), Node.js. Urgent.",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/8753551584749710/",
    },
    "Solvis": {
        "domain": "solvis.co.th",
        "emails": ["pornnabhasorn.s@solvis.co.th"],
        "best": "pornnabhasorn.s@solvis.co.th",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring QA Engineer at True Digital Park",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24282471598097791/",
    },
    "Tech Combine": {
        "domain": "techcombine.co",
        "emails": ["sirapassorn.c@techcombine.co"],
        "best": "sirapassorn.c@techcombine.co",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring Senior Performance, QA Manager, and other positions",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/26927812053563719/",
    },
    "Infos": {
        "domain": "infos.co.th",
        "emails": ["hr@infos.co.th"],
        "best": "hr@infos.co.th",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring multiple positions",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/26927812053563719/",
    },
    "Thailand Vibes": {
        "domain": "thailand-vibes.com",
        "emails": ["jobs@thailand-vibes.com"],
        "best": "jobs@thailand-vibes.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring Developer (Contract)",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25391298187215121/",
    },
    "Synthmind Co., Ltd. (บริษัทซินธ์ไมนด์ จำกัด)": {
        "domain": None,
        "emails": [],
        "best": None,
        "source": "FB JobThai Programmer WFH group",
        "note": "Hiring developers — found in jobthaiwfh group",
        "fb_post": "https://www.facebook.com/groups/jobthaiwfh/posts/1179195033933419/",
    },

    # ── Recruitment agencies (useful for multiple placements) ──

    "GetLinks": {
        "domain": "getlinks.com",
        "emails": ["parita.s@getlinks.com", "hang.nguyen@getlinks.com"],
        "best": "parita.s@getlinks.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Recruitment agency — multiple Thai tech positions, up to 85k budget",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25295815900096684/",
    },
    "RobinHunters": {
        "domain": "robinhunters.com",
        "emails": ["presidentnwres@yahoo.com"],
        "best": "presidentnwres@yahoo.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Recruitment agency — June Edition hot jobs, Bangkok IT roles",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/26655314534146807/",
    },
    "Keen Profile": {
        "domain": "keenprofile.com",
        "emails": ["phatsorn@keenprofile.com"],
        "best": "phatsorn@keenprofile.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Recruitment agency — hiring Full Stack Engineers (2 positions)",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24786321144379498/",
    },
    "TalentX": {
        "domain": "talentx.dev",
        "emails": ["support@talentx.dev"],
        "best": "support@talentx.dev",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Recruitment agency — developer positions",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24786321144379498/",
    },
    "Optima Search Jobs": {
        "domain": "optimasearchjobs.net",
        "emails": ["Sarawoot@optimasearchjobs.net"],
        "best": "Sarawoot@optimasearchjobs.net",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Recruitment agency — Codemonday co. job openings in Bangkok",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24033685789643041/",
    },
    "Boss Deal Corporation": {
        "domain": None,
        "emails": ["bossdealcorporation@gmail.com"],
        "best": "bossdealcorporation@gmail.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Job openings for developers and analysts in Thailand",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24211638798514405/",
    },
    "RCX Recruitment": {
        "domain": "rcx-recruitment.com",
        "emails": ["phimlaphat@rcx-recruitment.com"],
        "best": "phimlaphat@rcx-recruitment.com",
        "source": "FB JobThai Programmer WFH group",
        "note": "Recruitment agency — C programmer positions, Sadwaekao area",
        "fb_post": "https://www.facebook.com/groups/jobthaiwfh/",
    },
    "JP Tech Solutions": {
        "domain": "jpstechsolutions.com",
        "emails": ["vinay@jpstechsolutions.com"],
        "best": "vinay@jpstechsolutions.com",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Software Engineer positions — WFH or Hybrid preferred",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/24494804976864451/",
    },
    "Codup (Balerion)": {
        "domain": "codup.co",
        "emails": ["raheel.akhtar@codup.co"],
        "best": "raheel.akhtar@codup.co",
        "source": "FB Jobs for Thai Programmers group",
        "note": "Balerion hiring for software development and business roles",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/25197795383232070/",
    },
    "IHTAD": {
        "domain": None,
        "emails": [],
        "best": None,
        "source": "FB Jobs for Thai Programmers group",
        "note": "Hiring Software Engineer (Python), Remote",
        "fb_post": "https://www.facebook.com/groups/647718825333067/posts/26655314534146807/",
    },
    "Shreyan Tech": {
        "domain": "shreyantech.com",
        "emails": ["info@shreyantech.com"],
        "best": "info@shreyantech.com",
        "source": "FB JobThai Programmer WFH group",
        "note": "Developer positions — email resume",
        "fb_post": "https://www.facebook.com/groups/jobthaiwfh/",
    },
}


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_to_tracker(tracker_path, companies):
    """Add companies to apply_tracker.csv if not already present."""
    existing = set()
    rows = []
    if os.path.exists(tracker_path):
        with open(tracker_path, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)
                existing.add(row["company"].lower().strip())

    added = 0
    for company, data in companies.items():
        if company.lower().strip() in existing:
            continue
        domain = data.get("domain") or ""
        url = f"https://{domain}" if domain else ""
        row = {
            "url": url,
            "title": "Software Developer",
            "company": company,
            "status": "discovered",
            "note": data.get("note", f"FB group — email: {data.get('best', 'N/A')}"),
            "updated_at": "",
            "work_type": "WFO",
            "visa_sponsor": "",
            "job_type": "Full-time",
            "experience_level": "",
            "country": "TH",
        }
        if fieldnames:
            filtered = {k: row.get(k, "") for k in fieldnames if k in row}
            rows.append(filtered)
        else:
            rows.append(row)
        added += 1

    if added > 0:
        fieldnames = fieldnames or [
            "url", "title", "company", "status", "note", "updated_at",
            "work_type", "visa_sponsor", "job_type", "experience_level", "country",
        ]
        with open(tracker_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    return added


def main():
    dry_run = "--apply" not in sys.argv

    contacts = load_json(CONTACT_FILE)
    print(f"Existing contacts: {len(contacts)}")

    new_contacts = 0
    updated_contacts = 0
    for company, data in FB_COMPANIES.items():
        if company in contacts:
            existing = contacts[company]
            # Update if existing has no emails but new data does
            if not existing.get("emails") and data.get("emails"):
                contacts[company].update(data)
                updated_contacts += 1
                print(f"  Updated: {company} → {data.get('best', 'N/A')}")
            else:
                print(f"  Skip (exists): {company}")
            continue
        contacts[company] = data
        new_contacts += 1
        email_info = data.get("best") or "no email"
        print(f"  New: {company} ({email_info})")

    print(f"\nNew contacts: {new_contacts}")
    print(f"Updated contacts: {updated_contacts}")
    print(f"Total contacts: {len(contacts)}")

    # Count by source
    fb_count = sum(
        1 for v in contacts.values()
        if "FB" in v.get("source", "") or "facebook" in v.get("source", "").lower()
    )
    print(f"FB-sourced contacts in DB: {fb_count}")

    if dry_run:
        print("\n[DRY RUN] No changes written. Use --apply to write.")
        return

    # Save contacts
    save_json(CONTACT_FILE, contacts)
    print(f"Saved to {CONTACT_FILE}")

    # Add to tracker
    tracker_added = add_to_tracker(TRACKER_FILE, FB_COMPANIES)
    print(f"Added {tracker_added} entries to tracker")

    # Summary of sendable
    sendable = sum(
        1 for company, data in FB_COMPANIES.items()
        if data.get("best") and data["best"] not in [
            "info@", "support@", "hello@", "contact@", "careers@"
        ]
    )
    print(f"\nSendable (have hiring email): {sendable}/{len(FB_COMPANIES)}")


if __name__ == "__main__":
    main()
