#!/usr/bin/env python3
"""
Portfolio Health Check
Checks if all *.bookchaowalit.com subdomains are responding (HTTP 200).
Flags broken links and generates a report.
"""

import urllib.request
import urllib.error
import json
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from _env import BRIEFINGS_DIR

def get_portfolio_repos():
    """Get all portfolio frontend repos from GitHub."""
    try:
        result = subprocess.run(
            ["gh", "repo", "list", "bookchaowalit", "--limit", "200", "--json", "name",
             "--jq", '.[] | select(.name | contains("-frontend")) | .name'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            repos = [r for r in result.stdout.strip().split('\n') if r]
            return repos
    except Exception as e:
        print(f"Error fetching repos: {e}")
    return []

def check_subdomain(repo_name):
    """Check if a subdomain is responding."""
    # Convert repo name to subdomain: bookchaowalit-ai-art-gallery-frontend -> ai-art-gallery
    if repo_name.startswith("bookchaowalit-") and repo_name.endswith("-frontend"):
        subdomain = repo_name.replace("bookchaowalit-", "").replace("-frontend", "")
    else:
        return None
    
    # Skip special cases
    if subdomain in ["portfolio", "devhub", "projects-showcase"]:
        return None
    
    url = f"https://{subdomain}.bookchaowalit.com"
    
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        status = response.getcode()
        return {
            "subdomain": subdomain,
            "url": url,
            "status": status,
            "working": status == 200
        }
    except urllib.error.HTTPError as e:
        return {
            "subdomain": subdomain,
            "url": url,
            "status": e.code,
            "working": False
        }
    except Exception as e:
        return {
            "subdomain": subdomain,
            "url": url,
            "status": "error",
            "working": False,
            "error": str(e)
        }

def main():
    print("🔍 Portfolio Health Check\n")
    print("Fetching portfolio repos from GitHub...")
    
    repos = get_portfolio_repos()
    print(f"Found {len(repos)} portfolio repos\n")
    
    if not repos:
        print("No repos found. Exiting.")
        return
    
    print("Checking subdomains (this may take a minute)...\n")
    
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_subdomain, repo): repo for repo in repos}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
                status_icon = "✅" if result["working"] else "❌"
                print(f"{status_icon} {result['subdomain']}: {result['status']}")
    
    # Generate report
    working = [r for r in results if r["working"]]
    broken = [r for r in results if not r["working"]]
    
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Total checked: {len(results)}")
    print(f"Working: {len(working)}")
    print(f"Broken: {len(broken)}")
    
    if broken:
        print("\n❌ BROKEN SUBDOMAINS:")
        for r in broken:
            print(f"  - {r['subdomain']}: {r['status']}")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "working": len(working),
        "broken": len(broken),
        "broken_list": [r["subdomain"] for r in broken]
    }
    
    report_path = BRIEFINGS_DIR / "portfolio-health.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✅ Report saved to {report_path}")

if __name__ == "__main__":
    main()
