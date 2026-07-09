#!/usr/bin/env python3
"""
Cloudflare Analytics Integration
Pulls traffic statistics from Cloudflare for your domains.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
import os

from _env import BRIEFINGS_DIR, get_cloudflare_token

# Get Cloudflare API token from environment
CF_API_TOKEN = get_cloudflare_token() or ""

if not CF_API_TOKEN:
    print("Error: CLOUDFLARE_API_TOKEN not set (check .env)")
    exit(1)

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# Your domains to track (only root domains, not subdomains)
DOMAINS = [
    "bookchaowalit.com"
]


def cf_request(endpoint, params=None):
    """Make a Cloudflare API request (GET)."""
    url = f"{CF_API_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"API error: {e}")
        return None


def cf_graphql(query):
    """Make a Cloudflare GraphQL request (POST with JSON body)."""
    url = f"{CF_API_BASE}/graphql"
    data = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"GraphQL API error: {e}")
        return None


def get_zone_id(domain):
    """Get Cloudflare zone ID for a domain."""
    result = cf_request("/zones", {"name": domain})
    if result and result.get("success") and result.get("result"):
        return result["result"][0]["id"]
    return None


def get_analytics(zone_id, since="7d"):
    """Get analytics for a zone."""
    # Cloudflare GraphQL API for analytics
    query = """
    query {
        viewer {
            zones(filter: {zoneTag: "%s"}) {
                httpRequests1dGroups(limit: 7, filter: {date_gt: "%s"}) {
                    dimensions {
                        date
                    }
                    sum {
                        pageViews
                        requests
                        bytes
                        threats
                        country
                    }
                }
            }
        }
    }
    """
    
    # Calculate date threshold
    days = int(since.rstrip("d"))
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    
    result = cf_graphql(query % (zone_id, threshold))
    
    if result and result.get("data"):
        return result["data"]
    return None


def get_zone_stats(zone_id):
    """Get zone statistics using GraphQL API."""
    # Use GraphQL for analytics (requires Analytics:Read permission)
    analytics = get_analytics(zone_id, since="7d")
    
    if analytics:
        # Parse GraphQL response
        try:
            zones = analytics.get("viewer", {}).get("zones", [])
            if zones:
                zone_data = zones[0]
                groups = zone_data.get("httpRequests1dGroups", [])
                
                # Aggregate data from last 7 days
                total_requests = 0
                total_page_views = 0
                total_bytes = 0
                total_threats = 0
                
                for group in groups:
                    sum_data = group.get("sum", {})
                    total_requests += sum_data.get("requests", 0)
                    total_page_views += sum_data.get("pageViews", 0)
                    total_bytes += sum_data.get("bytes", 0)
                    total_threats += sum_data.get("threats", 0)
                
                return {
                    "requests": {"all": total_requests, "cached": 0, "uncached": 0},
                    "pageViews": {"all": total_page_views},
                    "bandwidth": {"all": total_bytes},
                    "threats": {"all": total_threats},
                    "uniques": {"all": 0},  # Not available in this query
                    "period": "7 days"
                }
        except Exception as e:
            print(f"  ⚠️  Error parsing analytics: {e}")
    
    # Fallback: get DNS records count as a basic metric
    dns_result = cf_request(f"/zones/{zone_id}/dns_records")
    if dns_result and dns_result.get("success"):
        return {
            "dns_records": len(dns_result.get("result", [])),
            "zone_id": zone_id
        }
    
    return None


def main():
    print("☁️  Cloudflare Analytics Integration\n")
    
    all_stats = []
    
    for domain in DOMAINS:
        print(f"📊 Fetching stats for {domain}...")
        
        zone_id = get_zone_id(domain)
        if not zone_id:
            print(f"  ℹ️  Domain not found in Cloudflare (may be a subdomain)")
            continue
        
        print(f"  Zone ID: {zone_id}")
        
        # Get basic stats
        stats = get_zone_stats(zone_id)
        if stats:
            # Handle different response formats
            if "dns_records" in stats:
                # Fallback format
                domain_stats = {
                    "domain": domain,
                    "zone_id": zone_id,
                    "dns_records": stats["dns_records"],
                    "timestamp": datetime.now().isoformat()
                }
                print(f"  ✅ Zone found:")
                print(f"     DNS records: {domain_stats['dns_records']}")
            else:
                # Full analytics format — get_zone_stats returns keys at top level
                requests = stats.get("requests", {})
                page_views = stats.get("pageViews", {})
                uniques = stats.get("uniques", {})
                bandwidth = stats.get("bandwidth", {})
                threats = stats.get("threats", {})
                
                domain_stats = {
                    "domain": domain,
                    "zone_id": zone_id,
                    "requests": {
                        "all": requests.get("all", 0),
                        "cached": requests.get("cached", 0),
                        "uncached": requests.get("uncached", 0)
                    },
                    "page_views": page_views.get("all", 0),
                    "uniques": uniques.get("all", 0),
                    "bandwidth": bandwidth.get("all", 0),
                    "threats": threats.get("all", 0),
                    "timestamp": datetime.now().isoformat()
                }
                
                print(f"  ✅ Stats retrieved:")
                print(f"     Page views: {domain_stats['page_views']:,}")
                print(f"     Unique visitors: {domain_stats['uniques']:,}")
                print(f"     Total requests: {domain_stats['requests']['all']:,}")
                print(f"     Bandwidth: {domain_stats['bandwidth']:,} bytes")
                print(f"     Threats blocked: {domain_stats['threats']:,}")
            
            all_stats.append(domain_stats)
        else:
            print(f"  ⚠️  Could not retrieve stats")
    
    # Save report
    if all_stats:
        report = {
            "timestamp": datetime.now().isoformat(),
            "domains": all_stats
        }
        
        report_path = BRIEFINGS_DIR / "cloudflare-analytics.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✅ Report saved to {report_path}")
    else:
        print("\n⚠️  No stats retrieved")


if __name__ == "__main__":
    main()
