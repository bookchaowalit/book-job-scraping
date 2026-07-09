#!/usr/bin/env python3
"""
Pipeline Backup & Rotation — Auto-backup CSV data files with rotation.

Backup strategy:
  - Daily backups: keep last 7 days
  - Weekly backups: keep last 4 weeks (Sunday snapshots)
  - Monthly backups: keep last 3 months (1st of month snapshots)

Backs up all critical CSV/JSON files to data/backups/ as compressed archives.

Usage:
    python3 pipeline_backup.py              # Backup + rotate
    python3 pipeline_backup.py --dry-run    # Show what would happen
    python3 pipeline_backup.py --restore    # List available backups
    python3 pipeline_backup.py --restore FILE  # Restore from backup
"""

import argparse
import gzip
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
BACKUP_DIR = DATA_DIR / "backups"

# Files to back up
BACKUP_FILES = [
    "job_postings.csv",
    "matched_jobs.csv",
    "apply_tracker.csv",
    "job_descriptions.csv",
    "pipeline_metrics.json",
    "pipeline_health.json",
    "board_health.json",
    "weekly_snapshots.json",
    "keyword_rotation.json",
    "tailor_log.json",
    "daily_digest.json",
]

# Retention policy
RETENTION = {
    "daily": 7,    # Keep 7 daily backups
    "weekly": 4,   # Keep 4 weekly backups
    "monthly": 3,  # Keep 3 monthly backups
}


def get_file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def get_backup_type(filename: str) -> str:
    """Determine backup type from filename pattern."""
    if "_daily_" in filename:
        return "daily"
    elif "_weekly_" in filename:
        return "weekly"
    elif "_monthly_" in filename:
        return "monthly"
    return "unknown"


def create_backup(dry_run: bool = False) -> dict:
    """Create a compressed backup of all critical files."""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d_%H%M%S")

    # Determine backup type
    if now.day == 1:
        backup_type = "monthly"
    elif now.weekday() == 6:  # Sunday
        backup_type = "weekly"
    else:
        backup_type = "daily"

    backup_name = f"solo-empire_{backup_type}_{date_str}"
    backup_path = BACKUP_DIR / backup_name

    if dry_run:
        print(f"  [DRY RUN] Would create: {backup_name}.tar.gz")
        total_size = 0
        for fname in BACKUP_FILES:
            fpath = DATA_DIR / fname
            if fpath.exists():
                size = get_file_size(fpath)
                total_size += size
                print(f"    • {fname} ({size:,} bytes)")
            else:
                print(f"    • {fname} (missing)")
        print(f"  Total: {total_size:,} bytes → compressed archive")
        return {"backup_name": backup_name, "dry_run": True}

    # Create backup directory
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create compressed tar archive
    import tarfile
    archive_path = BACKUP_DIR / f"{backup_name}.tar.gz"

    files_backed = 0
    total_size = 0
    with tarfile.open(archive_path, "w:gz") as tar:
        for fname in BACKUP_FILES:
            fpath = DATA_DIR / fname
            if fpath.exists():
                tar.add(fpath, arcname=f"{backup_name}/{fname}")
                files_backed += 1
                total_size += get_file_size(fpath)

    archive_size = get_file_size(archive_path)
    compression_ratio = round(archive_size / max(total_size, 1) * 100, 1)

    result = {
        "backup_name": backup_name,
        "backup_path": str(archive_path),
        "backup_type": backup_type,
        "files_backed_up": files_backed,
        "original_size": total_size,
        "compressed_size": archive_size,
        "compression_ratio": compression_ratio,
        "timestamp": now.isoformat(),
    }

    print(f"  ✓ Backup created: {backup_name}.tar.gz")
    print(f"    Files: {files_backed} | Original: {total_size:,} bytes → Compressed: {archive_size:,} bytes ({compression_ratio}%)")

    return result


def rotate_backups(dry_run: bool = False) -> dict:
    """Apply retention policy: remove old backups beyond limits."""
    if not BACKUP_DIR.exists():
        return {"removed": 0, "kept": 0}

    # Group backups by type
    daily_backups = []
    weekly_backups = []
    monthly_backups = []

    for f in sorted(BACKUP_DIR.glob("solo-empire_*.tar.gz"), reverse=True):
        btype = get_backup_type(f.stem)
        if btype == "daily":
            daily_backups.append(f)
        elif btype == "weekly":
            weekly_backups.append(f)
        elif btype == "monthly":
            monthly_backups.append(f)

    to_remove = []

    # Apply retention limits
    if len(daily_backups) > RETENTION["daily"]:
        to_remove.extend(daily_backups[RETENTION["daily"]:])
    if len(weekly_backups) > RETENTION["weekly"]:
        to_remove.extend(weekly_backups[RETENTION["weekly"]:])
    if len(monthly_backups) > RETENTION["monthly"]:
        to_remove.extend(monthly_backups[RETENTION["monthly"]:])

    removed = 0
    freed_bytes = 0
    for f in to_remove:
        if dry_run:
            print(f"  [DRY RUN] Would remove: {f.name}")
        else:
            size = get_file_size(f)
            f.unlink()
            removed += 1
            freed_bytes += size

    kept = len(list(BACKUP_DIR.glob("solo-empire_*.tar.gz"))) if not dry_run else 0

    if not dry_run and removed > 0:
        print(f"  ✓ Rotated: removed {removed} old backup(s), freed {freed_bytes:,} bytes")
        print(f"    Remaining: {kept} backup(s)")

    return {"removed": removed, "kept": kept, "freed_bytes": freed_bytes}


def list_backups():
    """List all available backups."""
    if not BACKUP_DIR.exists():
        print("  No backups found")
        return

    backups = sorted(BACKUP_DIR.glob("solo-empire_*.tar.gz"), reverse=True)
    if not backups:
        print("  No backups found")
        return

    print(f"\n  Available backups ({len(backups)}):")
    print(f"  {'Name':<55} {'Type':<10} {'Size':>12} {'Date':<16}")
    print(f"  {'-'*95}")

    for f in backups:
        btype = get_backup_type(f.stem)
        size = get_file_size(f)
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size_str = f"{size:,} bytes" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
        print(f"  {f.name:<55} {btype:<10} {size_str:>12} {mtime.strftime('%Y-%m-%d %H:%M')}")


def restore_backup(backup_name: str):
    """Restore from a backup archive."""
    # Find the backup
    if backup_name.endswith(".tar.gz"):
        archive_path = BACKUP_DIR / backup_name
    else:
        archive_path = BACKUP_DIR / f"{backup_name}.tar.gz"

    if not archive_path.exists():
        print(f"  ✗ Backup not found: {archive_path}")
        sys.exit(1)

    print(f"\n  Restoring from: {archive_path.name}")

    import tarfile
    with tarfile.open(archive_path, "r:gz") as tar:
        # Extract to data directory
        for member in tar.getmembers():
            # Strip the backup_name/ prefix
            parts = member.name.split("/", 1)
            if len(parts) < 2:
                continue
            fname = parts[1]
            target = DATA_DIR / fname
            print(f"    • Restoring: {fname}")
            # Extract file
            f = tar.extractfile(member)
            if f:
                with open(target, "wb") as out:
                    out.write(f.read())

    print(f"\n  ✓ Restore complete from {archive_path.name}")
    print(f"  ⚠️  Existing files were overwritten")


def save_backup_log(result: dict, rotation: dict):
    """Append to backup log."""
    log_file = BACKUP_DIR / "backup.log"
    with open(log_file, "a") as f:
        f.write(f"[{result.get('timestamp', datetime.now().isoformat())}] "
                f"type={result.get('backup_type', 'unknown')} "
                f"files={result.get('files_backed_up', 0)} "
                f"size={result.get('compressed_size', 0)} "
                f"rotated={rotation.get('removed', 0)}\n")


def main():
    parser = argparse.ArgumentParser(description="Pipeline Backup & Rotation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--restore", type=str, nargs="?", const="list", help="Restore from backup (or list available)")
    parser.add_argument("--list", action="store_true", help="List available backups")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  PIPELINE BACKUP & ROTATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # List mode
    if args.list or args.restore == "list":
        list_backups()
        return

    # Restore mode
    if args.restore:
        restore_backup(args.restore)
        return

    # Backup + rotate
    print("  [1/2] Creating backup...")
    result = create_backup(dry_run=args.dry_run)

    print(f"\n  [2/2] Applying retention policy...")
    if not args.dry_run:
        rotation = rotate_backups(dry_run=False)
        save_backup_log(result, rotation)
    else:
        rotation = rotate_backups(dry_run=True)

    # Show current state
    print(f"\n  Retention Policy:")
    print(f"    • Daily: keep last {RETENTION['daily']}")
    print(f"    • Weekly: keep last {RETENTION['weekly']} (Sunday)")
    print(f"    • Monthly: keep last {RETENTION['monthly']} (1st)")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
