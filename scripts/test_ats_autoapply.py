#!/usr/bin/env python3
"""Test HTTP auto-apply on ATS platforms (Greenhouse, Lever, Ashby)."""

import requests
import json
import time
from pathlib import Path

BASE = "/home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping"
TRACKER_FILE = f"{BASE}/data/apply_tracker.csv"

def test_greenhouse_api():
    """Test if Greenhouse has a public application API."""
    # Greenhouse job boards typically use: job-boards.greenhouse.io/{company}/jobs/{id}
    # Application endpoint might be: job-boards.greenhouse.io/{company}/applications
    
    test_url = "https://job-boards.greenhouse.io/builder/jobs/6020728004"
    
    # Try to find the application endpoint
    company = "builder"
    job_id = "6020728004"
    
    # Common Greenhouse application endpoints
    endpoints = [
        f"https://job-boards.greenhouse.io/{company}/applications",
        f"https://job-boards.greenhouse.io/{company}/jobs/{job_id}/applications",
        f"https://boards-api.greenhouse.io/v1/{company}/jobs/{job_id}",
    ]
    
    print("Testing Greenhouse endpoints...")
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, timeout=10)
            print(f"  GET {endpoint}")
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"    Response: {resp.text[:200]}")
        except Exception as e:
            print(f"  GET {endpoint} - Error: {e}")
    
    # Try POST with test data
    print("\nTesting POST to Greenhouse...")
    test_data = {
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "phone": "555-555-5555",
        "resume": "",
        "cover_letter": "",
    }
    
    try:
        resp = requests.post(
            f"https://job-boards.greenhouse.io/{company}/applications",
            json=test_data,
            timeout=10
        )
        print(f"  POST Status: {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")
    except Exception as e:
        print(f"  POST Error: {e}")

def test_lever_api():
    """Test if Lever has a public application API."""
    print("\nTesting Lever endpoints...")
    
    # Lever uses: jobs.lever.co/{company}/{job-id}
    company = "firstup"
    job_id = "ec51ee72-a369-4018-8a45-15a26b7e9309"
    
    endpoints = [
        f"https://jobs.lever.co/{company}/{job_id}",
        f"https://api.lever.co/v1/postings/{company}/{job_id}",
    ]
    
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, timeout=10)
            print(f"  GET {endpoint}")
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"    Response: {resp.text[:200]}")
        except Exception as e:
            print(f"  GET {endpoint} - Error: {e}")

def test_ashby_api():
    """Test if Ashby has a public application API."""
    print("\nTesting Ashby endpoints...")
    
    # Ashby uses: jobs.ashbyhq.com/{company}/{job-id}
    company = "mapbox"
    job_id = "dfeb1598-b717-427b-9da3-7caaef670eb9"
    
    endpoints = [
        f"https://jobs.ashbyhq.com/{company}/{job_id}",
        f"https://api.ashbyhq.com/v1/{company}/jobs/{job_id}",
    ]
    
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, timeout=10)
            print(f"  GET {endpoint}")
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"    Response: {resp.text[:200]}")
        except Exception as e:
            print(f"  GET {endpoint} - Error: {e}")

if __name__ == "__main__":
    test_greenhouse_api()
    test_lever_api()
    test_ashby_api()
