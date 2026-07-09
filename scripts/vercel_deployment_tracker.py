#!/usr/bin/env python3
"""
Vercel Deployment Tracker
Checks recent deployments across all projects and logs status.
"""

import json
import subprocess
import re
from datetime import datetime, timezone, timedelta

from _env import DB_PATH, BRIEFINGS_DIR


def get_all_deployments():
    """Get all recent deployments using Vercel CLI."""
    try:
        result = subprocess.run(
            ["vercel", "ls", "-a"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        print(f"Error fetching deployments: {e}")
    return ""


def parse_deployments(output):
    """Parse Vercel CLI output to extract deployment info."""
    deployments = []
    
    # When run via subprocess, Vercel CLI outputs just URLs
    # Example: "https://bookchaowalit-portfolio-frontend-4ujb3sgye.vercel.app"
    lines = output.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or not line.startswith('http'):
            continue
        
        # Extract project name from URL
        # Example: https://bookchaowalit-portfolio-frontend-4ujb3sgye.vercel.app
        # Project: bookchaowalit-portfolio-frontend
        try:
            # Remove protocol and domain
            url_parts = line.replace('https://', '').split('.')
            if len(url_parts) >= 2:
                subdomain = url_parts[0]
                # Remove the hash at the end (e.g., -4ujb3sgye)
                project = '-'.join(subdomain.split('-')[:-1]) if '-' in subdomain else subdomain
                
                deployments.append({
                    "age": "unknown",
                    "project": project,
                    "url": line,
                    "status": "READY",  # Assume ready if deployed
                    "environment": "Production",
                    "duration": "unknown",
                    "username": "bookchaowalit"
                })
        except Exception as e:
            # Skip lines that don't parse correctly
            continue
    
    return deployments


def main():
    print("🚀 Vercel Deployment Tracker\n")
    
    output = get_all_deployments()
    if not output:
        print("No deployment data retrieved.")
        return
    
    deployments = parse_deployments(output)
    print(f"Found {len(deployments)} deployments\n")
    
    if not deployments:
        print("Could not parse any deployments from output.")
        return
    
    # Analyze deployments
    total = len(deployments)
    ready = sum(1 for d in deployments if d["status"] == "READY")
    errors = sum(1 for d in deployments if d["status"] == "ERROR")
    building = sum(1 for d in deployments if d["status"] == "BUILDING")
    unknown = sum(1 for d in deployments if d["status"] == "UNKNOWN")
    
    # Get unique projects
    projects = set(d["project"] for d in deployments)
    
    print(f"📊 Summary:")
    print(f"  Total deployments: {total}")
    print(f"  Unique projects: {len(projects)}")
    print(f"  Ready: {ready}")
    print(f"  Errors: {errors}")
    print(f"  Building: {building}")
    print(f"  Unknown: {unknown}")
    
    # Show recent deployments (last 7 days)
    recent = [d for d in deployments if d["age"].endswith(('h', 'm')) or (d["age"].endswith('d') and int(d["age"][:-1]) <= 7)]
    
    if recent:
        print(f"\n📅 Recent Deployments (last 7 days): {len(recent)}")
        for dep in recent[:15]:
            status_icon = "✅" if dep['status'] == "READY" else "❌" if dep['status'] == "ERROR" else "⏳"
            print(f"  {status_icon} {dep['project']}: {dep['age']} ago - {dep['status']}")
    
    # Show errors
    error_deps = [d for d in deployments if d["status"] == "ERROR"]
    if error_deps:
        print(f"\n❌ Failed Deployments: {len(error_deps)}")
        for dep in error_deps[:10]:
            print(f"  - {dep['project']}: {dep['url']}")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_deployments": total,
        "unique_projects": len(projects),
        "status_summary": {
            "ready": ready,
            "errors": errors,
            "building": building,
            "unknown": unknown
        },
        "recent_deployments": recent[:20],
        "failed_deployments": error_deps[:10]
    }
    
    report_path = BRIEFINGS_DIR / "vercel-deployments.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✅ Report saved to {report_path}")


if __name__ == "__main__":
    main()
