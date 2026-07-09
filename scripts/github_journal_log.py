#!/usr/bin/env python3
"""
GitHub Activity → Journal Auto-Log
Summarizes daily GitHub commits and creates journal entries in Solo Empire DB.
"""

import sqlite3
import json
import subprocess
from datetime import datetime, timezone, timedelta

from _env import DB_PATH, PROJECT_ROOT


def get_today_commits():
    """Get today's commits across all repos using gh CLI."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Get user's recent commits
    try:
        result = subprocess.run(
            ["gh", "search", "commits", "--author=bookchaowalit", "--committer-date=>=" + today,
             "--json", "repository,commit,sha", "--limit", "50"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            print(f"   ⚠️  gh search failed: {result.stderr}")
            return []
        
        commits = json.loads(result.stdout)
        return commits
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
        return []


def get_local_commits():
    """Get commits from local repos as fallback."""
    today = datetime.now().strftime("%Y-%m-%d")
    commits = []
    
    # Check solo-empire repo
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "log", "--oneline", 
             f"--since={today}", "--format=%s"],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                commits.append({
                    "repository": {"name": "solo-empire"},
                    "commit": {"message": line}
                })
    except Exception:
        pass
    
    return commits


def create_journal_entry(title, content, tags=None, mood=None):
    """Create a journal entry in the database."""
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if entry already exists for today
    existing = conn.execute(
        "SELECT id FROM journal WHERE entry_date = ? AND entry_type = 'daily'",
        (today,)
    ).fetchone()
    
    if existing:
        # Update existing entry
        conn.execute("""
            UPDATE journal SET content = ?, tags = ?, updated_at = ?
            WHERE id = ?
        """, (content, tags, now, existing[0]))
        conn.commit()
        conn.close()
        return existing[0], "updated"
    else:
        # Create new entry
        cursor = conn.execute("""
            INSERT INTO journal (entry_type, title, content, tags, mood, entry_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("daily", title, content, tags, mood, today, now, now))
        conn.commit()
        entry_id = cursor.lastrowid
        conn.close()
        return entry_id, "created"


def main():
    print("📝 GitHub Activity → Journal Auto-Log...")
    
    # Try GitHub API first, fallback to local
    commits = get_today_commits()
    if not commits:
        print("   No commits from GitHub API, checking local repos...")
        commits = get_local_commits()
    
    if not commits:
        print("   No commits found today")
        return
    
    print(f"   Found {len(commits)} commits today")
    
    # Build journal content
    today = datetime.now().strftime("%A, %B %d, %Y")
    title = f"Dev Log — {today}"
    
    content_parts = [f"# Development Log — {today}\n"]
    content_parts.append(f"## Summary\n")
    content_parts.append(f"Made {len(commits)} commit(s) today.\n")
    
    # Group by repo
    by_repo = {}
    for c in commits:
        repo_name = c.get("repository", {}).get("name", "unknown")
        message = c.get("commit", {}).get("message", "").split("\n")[0]
        
        if repo_name not in by_repo:
            by_repo[repo_name] = []
        by_repo[repo_name].append(message)
    
    content_parts.append("\n## Commits by Repository\n")
    for repo, messages in by_repo.items():
        content_parts.append(f"\n### {repo}\n")
        for msg in messages:
            content_parts.append(f"- {msg}")
    
    content = "\n".join(content_parts)
    tags = "github,daily-log,development"
    
    # Create journal entry
    entry_id, action = create_journal_entry(title, content, tags, mood=4)
    
    print(f"\n   ✅ Journal entry {action}: ID {entry_id}")
    print(f"   Title: {title}")
    print(f"   Repos: {', '.join(by_repo.keys())}")


if __name__ == "__main__":
    main()
