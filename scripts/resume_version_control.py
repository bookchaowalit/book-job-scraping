#!/usr/bin/env python3
"""
Resume Version Control — Git-tracked resume versions per application.
Know exactly which resume was sent where, with diff tracking.

Usage:
    python resume_version_control.py --create --job-id <id> --resume <path> --notes "Tailored for AI role"
    python resume_version_control.py --list [--job-id <id>]
    python resume_version_control.py --diff --job-id <id> --v1 1 --v2 2
    python resume_version_control.py --latest --job-id <id>
    python resume_version_control.py --stats
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
RESUMES_DIR = DATA_DIR / "resume_versions"
REGISTRY_FILE = DATA_DIR / "resume_registry.json"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
DEFAULT_RESUME = Path.home() / "Documents" / "resume.pdf"


def load_registry():
    """Load resume version registry."""
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {"resumes": {}, "total_versions": 0}


def save_registry(registry):
    """Save resume version registry."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, default=str))


def file_hash(filepath):
    """Calculate file hash."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def create_version(job_id, resume_path, notes="", tags=None):
    """Create a new resume version for a job."""
    registry = load_registry()
    resume_path = Path(resume_path)

    if not resume_path.exists():
        print(f"Error: Resume file not found: {resume_path}")
        return

    # Create job directory
    job_dir = RESUMES_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Get version number
    if job_id not in registry["resumes"]:
        registry["resumes"][job_id] = {"versions": [], "created_at": datetime.now().isoformat()}

    version_num = len(registry["resumes"][job_id]["versions"]) + 1

    # Copy resume to versioned location
    ext = resume_path.suffix
    version_filename = f"resume_v{version_num}{ext}"
    version_path = job_dir / version_filename
    shutil.copy2(resume_path, version_path)

    # Calculate hash
    fhash = file_hash(version_path)

    # Record version
    version_record = {
        "version": version_num,
        "filename": version_filename,
        "path": str(version_path),
        "hash": fhash,
        "notes": notes,
        "tags": tags or [],
        "created_at": datetime.now().isoformat(),
        "file_size": version_path.stat().st_size,
        "file_type": ext.lstrip("."),
    }

    registry["resumes"][job_id]["versions"].append(version_record)
    registry["total_versions"] = sum(len(r["versions"]) for r in registry["resumes"].values())
    save_registry(registry)

    print(f"Resume version {version_num} created for job {job_id}")
    print(f"  File: {version_path}")
    print(f"  Hash: {fhash}")
    print(f"  Size: {version_path.stat().st_size:,} bytes")
    if notes:
        print(f"  Notes: {notes}")


def list_versions(job_id=None):
    """List resume versions."""
    registry = load_registry()
    resumes = registry.get("resumes", {})

    if not resumes:
        print("No resume versions recorded yet.")
        return

    if job_id:
        if job_id not in resumes:
            print(f"No versions for job {job_id}")
            return
        resumes = {job_id: resumes[job_id]}

    total = 0
    for jid, data in resumes.items():
        versions = data.get("versions", [])
        total += len(versions)
        print(f"\n📄 Job: {jid} ({len(versions)} versions)")
        print(f"  {'Ver':<5} {'Date':<12} {'Size':<10} {'Hash':<18} Notes")
        print(f"  {'-'*70}")
        for v in versions:
            date = v["created_at"][:10]
            size = f"{v['file_size']:,}B"
            notes = v.get("notes", "")[:30]
            tags = " ".join(f"#{t}" for t in v.get("tags", []))
            print(f"  v{v['version']:<4} {date:<12} {size:<10} {v['hash']:<18} {notes} {tags}")

    print(f"\nTotal: {total} versions across {len(resumes)} jobs")


def diff_versions(job_id, v1, v2):
    """Show diff between two resume versions (text files only)."""
    registry = load_registry()
    if job_id not in registry["resumes"]:
        print(f"No versions for job {job_id}")
        return

    versions = registry["resumes"][job_id]["versions"]
    file1 = file2 = None
    for v in versions:
        if v["version"] == v1:
            file1 = v["path"]
        if v["version"] == v2:
            file2 = v["path"]

    if not file1 or not file2:
        print(f"Version {v1} or {v2} not found for job {job_id}")
        return

    # Check if text-comparable
    p1, p2 = Path(file1), Path(file2)
    if p1.suffix == ".pdf" or p2.suffix == ".pdf":
        print("PDF diff not supported directly. Use a PDF diff tool.")
        print(f"  v{v1}: {file1}")
        print(f"  v{v2}: {file2}")
        return

    # Text diff
    try:
        result = subprocess.run(
            ["diff", "-u", file1, file2],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("No differences found (files are identical).")
        else:
            print(f"\nDiff between v{v1} and v{v2}:")
            print(result.stdout[:3000])
    except Exception as e:
        print(f"Diff error: {e}")


def get_latest(job_id):
    """Get the latest resume version for a job."""
    registry = load_registry()
    if job_id not in registry["resumes"]:
        print(f"No versions for job {job_id}")
        return None

    versions = registry["resumes"][job_id]["versions"]
    if not versions:
        print(f"No versions for job {job_id}")
        return None

    latest = versions[-1]
    print(f"Latest resume for job {job_id}:")
    print(f"  Version: v{latest['version']}")
    print(f"  Path: {latest['path']}")
    print(f"  Created: {latest['created_at']}")
    print(f"  Notes: {latest.get('notes', 'N/A')}")
    return latest["path"]


def show_stats():
    """Show resume version control stats."""
    registry = load_registry()
    resumes = registry.get("resumes", {})

    if not resumes:
        print("No resume versions recorded yet.")
        return

    total_versions = registry.get("total_versions", 0)
    total_jobs = len(resumes)

    # Calculate total storage
    total_size = 0
    for data in resumes.values():
        for v in data.get("versions", []):
            total_size += v.get("file_size", 0)

    # Most versions
    most_versions = max(resumes.items(), key=lambda x: len(x[1]["versions"]))

    # File types
    types = {}
    for data in resumes.values():
        for v in data.get("versions", []):
            ft = v.get("file_type", "unknown")
            types[ft] = types.get(ft, 0) + 1

    print(f"\n📊 RESUME VERSION CONTROL STATS")
    print(f"  Total jobs: {total_jobs}")
    print(f"  Total versions: {total_versions}")
    print(f"  Total storage: {total_size:,} bytes ({total_size/1024:.1f} KB)")
    print(f"  Most versions: {most_versions[0]} ({len(most_versions[1]['versions'])} versions)")
    print(f"  File types: {', '.join(f'{k}: {v}' for k, v in types.items())}")

    # Recent activity
    all_versions = []
    for jid, data in resumes.items():
        for v in data["versions"]:
            all_versions.append({**v, "job_id": jid})
    recent = sorted(all_versions, key=lambda x: x["created_at"], reverse=True)[:5]
    print(f"\n  Recent versions:")
    for v in recent:
        print(f"    {v['job_id'][:30]:<30} v{v['version']} {v['created_at'][:10]}")


def main():
    parser = argparse.ArgumentParser(description="Resume Version Control")
    parser.add_argument("--create", action="store_true", help="Create new version")
    parser.add_argument("--job-id", help="Job ID")
    parser.add_argument("--resume", help="Path to resume file")
    parser.add_argument("--notes", default="", help="Version notes")
    parser.add_argument("--tags", nargs="*", help="Tags for this version")
    parser.add_argument("--list", action="store_true", help="List versions")
    parser.add_argument("--diff", action="store_true", help="Diff two versions")
    parser.add_argument("--v1", type=int, help="First version")
    parser.add_argument("--v2", type=int, help="Second version")
    parser.add_argument("--latest", action="store_true", help="Get latest version")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()

    if args.create:
        if not args.job_id or not args.resume:
            print("Error: --job-id and --resume required")
            return
        create_version(args.job_id, args.resume, args.notes, args.tags)

    elif args.list:
        list_versions(args.job_id)

    elif args.diff:
        if not args.job_id or not args.v1 or not args.v2:
            print("Error: --job-id, --v1, --v2 required")
            return
        diff_versions(args.job_id, args.v1, args.v2)

    elif args.latest:
        if not args.job_id:
            print("Error: --job-id required")
            return
        get_latest(args.job_id)

    elif args.stats:
        show_stats()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
