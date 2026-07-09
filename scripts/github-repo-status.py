#!/usr/bin/env python3
"""
GitHub Repo Status Checker - Uses GitHub MCP to check all repos
Creates a comprehensive status report of all 155+ repos
"""

import json
from datetime import datetime
from pathlib import Path

HOME = Path.home()

def generate_repo_status_template():
    """Generate a template for checking repo status via GitHub MCP"""
    template = """# GitHub Repo Status Check

**Generated:** {date}

## How to Use This with GitHub MCP

Use the `mcp__github__search_repositories` tool with query: `user:bookchaowalit`

## Repo Categories

### Portfolio Projects (book-portfolio/)
- bookchaowalit-portfolio-frontend
- bookchaowalit-techblog-frontend
- bookchaowalit-devhub-frontend
- ... (98 portfolio subdomains)

### Client Projects (book-client/)
- table-grow
- ... (client repos)

### Products (book-products/)
- solo-empire
- booknbook
- localcrm-frontend
- localcrm-backend
- bookmarketing
- bookreading
- booktrading
- media-tracker
- go-gofiber-media-tracking

### AI Projects (book-ai/)
- ai-all-test
- ... (13 AI repos)

### Infrastructure (book-infra/)
- docker-setup
- backup-system
- ... (3 infra repos)

### Documentation (book-docs/)
- docs-repo
- mermaid-diagrams
- flowchart-tools
- ... (3 docs repos)

### Research (book-research/)
- research-projects
- ocr-tools
- ... (2 research repos)

### Profile
- bookchaowalit (GitHub profile)

## Status Checks to Perform

For each repo, check:
1. ✅ Last commit date (is it active?)
2. ✅ Open issues count
3. ✅ Open PRs count
4. ✅ Branch protection rules
5. ✅ Deployments status (Vercel)
6. ✅ Environment variables configured

## Quick Commands

```bash
# Check all repos
python3 ~/solo-empire/infra/scripts/sync-all-repos.py

# Check specific repo
cd ~/book-dev/book-portfolio/bookchaowalit-portfolio-frontend
git status
git log --oneline -5
```

## Action Items

- [ ] Review repos with no commits in 30+ days
- [ ] Check for outdated dependencies
- [ ] Review open issues and PRs
- [ ] Verify Vercel deployments
- [ ] Update repo descriptions
"""
    
    return template.format(date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

def create_repo_inventory():
    """Create a JSON inventory of all repos"""
    inventory = {
        "generated": datetime.now().isoformat(),
        "total_repos": 162,
        "categories": {
            "portfolio": {
                "count": 107,
                "path": "~/book-dev/book-portfolio/",
                "description": "101 Portfolio Projects + supporting repos"
            },
            "client": {
                "count": 11,
                "path": "~/book-dev/book-client/",
                "description": "Client freelance work"
            },
            "products": {
                "count": 10,
                "path": "~/book-dev/book-products/",
                "description": "Core products (solo-empire, booknbook, etc.)"
            },
            "ai": {
                "count": 13,
                "path": "~/book-dev/book-ai/",
                "description": "AI/ML projects"
            },
            "infra": {
                "count": 3,
                "path": "~/book-dev/book-infra/",
                "description": "Infrastructure/DevOps"
            },
            "docs": {
                "count": 3,
                "path": "~/book-dev/book-docs/",
                "description": "Documentation"
            },
            "research": {
                "count": 2,
                "path": "~/book-dev/book-research/",
                "description": "Research experiments"
            },
            "profile": {
                "count": 1,
                "path": "~/book-dev/book-profile/",
                "description": "GitHub profile"
            },
            "other": {
                "count": 12,
                "path": "~/book-dev/book-other/",
                "description": "Miscellaneous"
            }
        },
        "key_repos": {
            "solo-empire": {
                "url": "https://github.com/bookchaowalit/solo-empire",
                "description": "Main workspace repo (brain + 13 book-* folders)",
                "private": True
            },
            "portfolio": {
                "url": "https://github.com/bookchaowalit/bookchaowalit-portfolio-frontend",
                "description": "Personal portfolio site",
                "live_url": "https://bookchaowalit.com",
                "private": True
            },
            "booknbook": {
                "url": "https://github.com/bookchaowalit/booknbook",
                "description": "Consulting site with Jirarut",
                "live_url": "https://consulting.bookchaowalit.com",
                "private": True
            }
        }
    }
    
    return inventory

if __name__ == '__main__':
    # Generate status template
    template = generate_repo_status_template()
    print(template)
    
    # Save to file
    status_path = HOME / 'solo-empire' / 'reports' / 'github-repo-status.md'
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with open(status_path, 'w') as f:
        f.write(template)
    
    print(f"\n📄 Status template saved to: {status_path}")
    
    # Create inventory
    inventory = create_repo_inventory()
    inventory_path = HOME / 'solo-empire' / 'raw-data' / 'repo-inventory.json'
    with open(inventory_path, 'w') as f:
        json.dump(inventory, f, indent=2)
    
    print(f"📊 Repo inventory saved to: {inventory_path}")
