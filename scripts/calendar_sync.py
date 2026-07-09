#!/usr/bin/env python3
"""
Calendar Integration — Auto-schedule interview prep blocks on Google Calendar.
Syncs with application tracker to create events when applications advance.

Usage:
    python calendar_sync.py --check
    python calendar_sync.py --schedule-prep --job-id <id> --date 2026-06-25
    python calendar_sync.py --sync-applications
    python calendar_sync.py --list-events [--days 7]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
TRACKER_FILE = DATA_DIR / "application_tracker.json"
CALENDAR_CACHE = DATA_DIR / "calendar_cache.json"

# Google OAuth2 credentials (from .env)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Google Calendar API
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def get_access_token():
    """Get Google API access token from refresh token."""
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        return None

    try:
        resp = requests.post(TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception as e:
        print(f"Token error: {e}")
    return None


def calendar_request(method, endpoint, token, data=None):
    """Make Google Calendar API request."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{CALENDAR_API}/{endpoint}"

    try:
        resp = requests.request(method, url, headers=headers, json=data, timeout=15)
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            print(f"Calendar API error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"Calendar request error: {e}")
    return None


def load_tracker():
    """Load application tracker."""
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return {"applications": {}}


def check_calendar_connection():
    """Check if Google Calendar API is accessible."""
    token = get_access_token()
    if not token:
        print("❌ Google Calendar not connected.")
        print("  Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in .env")
        return False

    result = calendar_request("GET", f"calendars/{CALENDAR_ID}", token)
    if result:
        print(f"✅ Connected to Google Calendar: {result.get('summary', CALENDAR_ID)}")
        return True
    else:
        print("❌ Calendar API connection failed.")
        return False


def schedule_interview_prep(job_id, date_str=None, duration_minutes=60):
    """Schedule interview prep block on Google Calendar."""
    token = get_access_token()
    if not token:
        print("Google Calendar not configured. Simulating schedule...")
        tracker = load_tracker()
        app = tracker.get("applications", {}).get(job_id, {})
        title = app.get("title", "Unknown")
        company = app.get("company", "Unknown")
        print(f"  [SIMULATED] Interview prep: {title} at {company}")
        print(f"  Date: {date_str or 'TBD'}, Duration: {duration_minutes}min")
        return

    tracker = load_tracker()
    app = tracker.get("applications", {}).get(job_id, {})
    if not app:
        print(f"Application {job_id} not found in tracker.")
        return

    title = app.get("title", "Interview")
    company = app.get("company", "")
    prep_title = f"🎯 Interview Prep: {title} @ {company}"

    # Parse date
    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
            return
    else:
        date = datetime.now() + timedelta(days=2)  # Default: 2 days from now

    # Create event
    start_time = f"{date.strftime('%Y-%m-%d')}T09:00:00"
    end_time_dt = date.replace(hour=9) + timedelta(minutes=duration_minutes)
    end_time = f"{date.strftime('%Y-%m-%d')}T{end_time_dt.strftime('%H:%M:%S')}"

    event = {
        "summary": prep_title,
        "description": f"Interview preparation for {title} at {company}.\n\nJob ID: {job_id}\n\nPrep checklist:\n- Review company intel\n- Practice technical questions\n- Prepare behavioral stories (STAR method)\n- Prepare questions for interviewer",
        "start": {"dateTime": start_time, "timeZone": "Asia/Bangkok"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Bangkok"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 1440},  # 24 hours before
            ]
        },
        "colorId": "11",  # Red
    }

    result = calendar_request("POST", f"calendars/{CALENDAR_ID}/events", token, data=event)
    if result:
        print(f"✅ Scheduled: {prep_title}")
        print(f"  Date: {date.strftime('%Y-%m-%d')} 09:00-{end_time_dt.strftime('%H:%M')}")
        print(f"  Link: {result.get('htmlLink', 'N/A')}")
    else:
        print(f"❌ Failed to schedule event.")


def sync_applications_to_calendar():
    """Auto-create calendar events for applications in interview stages."""
    tracker = load_tracker()
    apps = tracker.get("applications", {})

    interview_stages = ["screening", "technical", "onsite"]
    to_schedule = []

    for job_id, app in apps.items():
        if app["stage"] in interview_stages:
            to_schedule.append(app)

    if not to_schedule:
        print("No applications in interview stages to schedule.")
        return

    print(f"Found {len(to_schedule)} applications in interview stages:\n")
    for app in to_schedule:
        print(f"  {app['title'][:35]:<35} {app['company']:<20} Stage: {app['stage']}")

    token = get_access_token()
    if not token:
        print("\n[Simulated mode — Google Calendar not configured]")
        for app in to_schedule:
            print(f"  [SIMULATED] Would schedule prep for: {app['title']} at {app['company']}")
        return

    print(f"\nScheduling interview prep blocks...")
    for app in to_schedule:
        schedule_interview_prep(app["job_id"])


def list_upcoming_events(days=7):
    """List upcoming calendar events."""
    token = get_access_token()
    if not token:
        print("Google Calendar not configured.")
        print("  Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in .env")
        return

    time_min = datetime.now().isoformat() + "Z"
    time_max = (datetime.now() + timedelta(days=days)).isoformat() + "Z"

    result = calendar_request(
        "GET",
        f"calendars/{CALENDAR_ID}/events?timeMin={time_min}&timeMax={time_max}&singleEvents=true&orderBy=startTime",
        token
    )

    if not result:
        print("Failed to fetch events.")
        return

    events = result.get("items", [])
    if not events:
        print(f"No events in the next {days} days.")
        return

    print(f"\n📅 UPCOMING EVENTS (next {days} days):\n")
    for event in events:
        start = event.get("start", {}).get("dateTime", "N/A")[:16]
        summary = event.get("summary", "No title")
        print(f"  {start}  {summary}")

    print(f"\n  Total: {len(events)} events")


def main():
    parser = argparse.ArgumentParser(description="Calendar Integration")
    parser.add_argument("--check", action="store_true", help="Check calendar connection")
    parser.add_argument("--schedule-prep", action="store_true", help="Schedule interview prep")
    parser.add_argument("--job-id", help="Job ID")
    parser.add_argument("--date", help="Date (YYYY-MM-DD)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in minutes")
    parser.add_argument("--sync-applications", action="store_true", help="Sync all interview applications")
    parser.add_argument("--list-events", action="store_true", help="List upcoming events")
    parser.add_argument("--days", type=int, default=7, help="Days to look ahead")
    args = parser.parse_args()

    if args.check:
        check_calendar_connection()
    elif args.schedule_prep:
        if not args.job_id:
            print("Error: --job-id required")
            return
        schedule_interview_prep(args.job_id, args.date, args.duration)
    elif args.sync_applications:
        sync_applications_to_calendar()
    elif args.list_events:
        list_upcoming_events(args.days)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
