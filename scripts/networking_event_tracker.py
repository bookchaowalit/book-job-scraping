#!/usr/bin/env python3
"""
Networking Event Tracker
Tracks tech meetups, conferences, and networking events.
Auto-finds events in Bangkok/remote via RSS and web scraping.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
EVENTS_DIR = DATA_DIR / "networking_events"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_FILE = EVENTS_DIR / "events.json"

# Event sources
EVENT_SOURCES = {
    "meetup_bangkok": {
        "name": "Meetup.com Bangkok Tech",
        "url": "https://www.meetup.com/find/?source=EVENTS&keywords=tech&location=th--Bangkok",
        "type": "web",
        "category": "meetup",
    },
    "eventbrite_bangkok": {
        "name": "Eventbrite Bangkok Tech",
        "url": "https://www.eventbrite.com/d/thailand--bangkok/tech/",
        "type": "web",
        "category": "conference",
    },
    "dev_events": {
        "name": "Dev.events",
        "url": "https://dev.events/",
        "type": "web",
        "category": "conference",
    },
    "tech_calendar": {
        "name": "Tech Events Calendar",
        "url": "https://www.techgig.com/events",
        "type": "web",
        "category": "conference",
    },
}

# Known recurring events in Bangkok
RECURRING_EVENTS = [
    {"name": "Bangkok Dev Meetup", "frequency": "monthly", "location": "Bangkok", "category": "meetup",
     "tags": ["web", "javascript", "react"], "url": "https://www.meetup.com/bangkok-dev/"},
    {"name": "Bangkok.js", "frequency": "monthly", "location": "Bangkok", "category": "meetup",
     "tags": ["javascript", "node.js", "frontend"], "url": "https://www.meetup.com/bangkok-js/"},
    {"name": "PyData Bangkok", "frequency": "monthly", "location": "Bangkok", "category": "meetup",
     "tags": ["python", "data", "ml"], "url": "https://www.meetup.com/pydata-bangkok/"},
    {"name": "Bangkok AWS User Group", "frequency": "quarterly", "location": "Bangkok", "category": "meetup",
     "tags": ["aws", "cloud", "devops"], "url": ""},
    {"name": "DevMountain Bangkok", "frequency": "monthly", "location": "Bangkok", "category": "meetup",
     "tags": ["general", "networking"], "url": ""},
    {"name": "Google Developer Group Bangkok", "frequency": "monthly", "location": "Bangkok", "category": "meetup",
     "tags": ["google", "android", "gcp", "flutter"], "url": "https://gdg.community.dev/gdg-bangkok/"},
]

# Remote-friendly events/conferences
REMOTE_EVENTS = [
    {"name": "React Summit (Remote)", "location": "Remote", "category": "conference",
     "tags": ["react", "frontend"], "url": "https://reactsummit.com/"},
    {"name": "NodeConf (Remote)", "location": "Remote", "category": "conference",
     "tags": ["node.js", "backend"], "url": "https://www.nodeconf.com/"},
    {"name": "JSConf", "location": "Various", "category": "conference",
     "tags": ["javascript", "web"], "url": "https://jsconf.com/"},
    {"name": "PyCon", "location": "Various", "category": "conference",
     "tags": ["python"], "url": "https://pycon.org/"},
    {"name": "KubeCon", "location": "Various", "category": "conference",
     "tags": ["kubernetes", "devops", "cloud"], "url": "https://events.linuxfoundation.org/kubecon-cloudnativecon/"},
    {"name": "AWS re:Invent", "location": "Las Vegas + Virtual", "category": "conference",
     "tags": ["aws", "cloud"], "url": "https://reinvent.awsevents.com/"},
    {"name": "Next.js Conf", "location": "Remote", "category": "conference",
     "tags": ["next.js", "react", "frontend"], "url": "https://nextjs.org/conf"},
    {"name": "Vercel Ship", "location": "Remote", "category": "conference",
     "tags": ["vercel", "frontend", "deployment"], "url": "https://vercel.com/ship"},
]


def load_events():
    """Load saved events."""
    if not EVENTS_FILE.exists():
        return {"events": [], "last_updated": None}
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": [], "last_updated": None}


def save_events(data):
    """Save events to file."""
    data["last_updated"] = datetime.now().isoformat()
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def add_event(name, date="", location="Bangkok", category="meetup", tags=None, url="", notes=""):
    """Add a new event."""
    data = load_events()
    event = {
        "id": f"evt_{len(data['events']) + 1:03d}",
        "name": name,
        "date": date,
        "location": location,
        "category": category,
        "tags": tags or [],
        "url": url,
        "notes": notes,
        "status": "upcoming",
        "added_at": datetime.now().isoformat(),
        "rsvp": False,
    }
    data["events"].append(event)
    save_events(data)
    return event


def list_events(category=None, status="upcoming", include_recurring=True):
    """List events."""
    data = load_events()
    events = data.get("events", [])

    if category:
        events = [e for e in events if e.get("category") == category]
    if status:
        events = [e for e in events if e.get("status") == status]

    print(f"\n📅 Networking Events ({len(events)} events)")
    print("=" * 70)

    if events:
        for e in events:
            rsvp_icon = "✅" if e.get("rsvp") else "  "
            date_str = e.get("date", "TBD")
            print(f"  {rsvp_icon} [{e['id']}] {e['name']}")
            print(f"      📅 {date_str} | 📍 {e.get('location', 'N/A')} | 🏷️  {e.get('category', '')}")
            if e.get("tags"):
                print(f"      Tags: {', '.join(e['tags'][:5])}")
            if e.get("url"):
                print(f"      🔗 {e['url'][:60]}")
            print()

    if include_recurring:
        print(f"\n🔄 Recurring Bangkok Events:")
        print(f"  {'─' * 50}")
        for e in RECURRING_EVENTS:
            print(f"  🔄 {e['name']} ({e['frequency']}) — {', '.join(e.get('tags', [])[:3])}")

    print(f"\n🌐 Remote-Friendly Conferences:")
    print(f"  {'─' * 50}")
    for e in REMOTE_EVENTS:
        print(f"  🌐 {e['name']} — {', '.join(e.get('tags', [])[:3])}")

    print(f"\n{'=' * 70}")


def search_events(keywords):
    """Search events by keywords."""
    data = load_events()
    all_events = data.get("events", []) + RECURRING_EVENTS + REMOTE_EVENTS

    results = []
    for event in all_events:
        text = f"{event.get('name', '')} {' '.join(event.get('tags', []))} {event.get('location', '')}".lower()
        if any(kw.lower() in text for kw in keywords):
            results.append(event)

    print(f"\n🔍 Search results for: {', '.join(keywords)} ({len(results)} found)")
    print("=" * 60)
    for e in results:
        print(f"  📅 {e.get('name', 'N/A')}")
        print(f"     📍 {e.get('location', 'N/A')} | 🏷️  {e.get('category', '')}")
    print("=" * 60)


def update_rsvp(event_id, rsvp_status=True):
    """Update RSVP status."""
    data = load_events()
    for event in data["events"]:
        if event["id"] == event_id:
            event["rsvp"] = rsvp_status
            save_events(data)
            print(f"✅ RSVP {'confirmed' if rsvp_status else 'cancelled'} for {event['name']}")
            return
    print(f"❌ Event {event_id} not found")


def mark_attended(event_id):
    """Mark event as attended."""
    data = load_events()
    for event in data["events"]:
        if event["id"] == event_id:
            event["status"] = "attended"
            event["attended_at"] = datetime.now().isoformat()
            save_events(data)
            print(f"✅ Marked {event['name']} as attended")
            return
    print(f"❌ Event {event_id} not found")


def import_recurring():
    """Import known recurring events."""
    data = load_events()
    existing_names = {e["name"] for e in data["events"]}
    added = 0

    for event in RECURRING_EVENTS + REMOTE_EVENTS:
        if event["name"] not in existing_names:
            new_event = {
                "id": f"evt_{len(data['events']) + 1:03d}",
                "name": event["name"],
                "date": "",
                "location": event.get("location", "Bangkok"),
                "category": event.get("category", "meetup"),
                "tags": event.get("tags", []),
                "url": event.get("url", ""),
                "notes": f"Recurring: {event.get('frequency', 'unknown')}",
                "status": "upcoming",
                "added_at": datetime.now().isoformat(),
                "rsvp": False,
            }
            data["events"].append(new_event)
            added += 1

    save_events(data)
    print(f"✅ Imported {added} recurring events (total: {len(data['events'])})")


def stats():
    """Show event statistics."""
    data = load_events()
    events = data.get("events", [])

    categories = {}
    locations = {}
    rsvp_count = 0

    for e in events:
        cat = e.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
        loc = e.get("location", "unknown")
        locations[loc] = locations.get(loc, 0) + 1
        if e.get("rsvp"):
            rsvp_count += 1

    print(f"\n📊 Networking Event Stats")
    print(f"{'=' * 50}")
    print(f"  Total events: {len(events)}")
    print(f"  RSVP'd: {rsvp_count}")
    print(f"  Last updated: {data.get('last_updated', 'Never')}")
    print(f"\n  By Category:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")
    print(f"\n  By Location:")
    for loc, count in sorted(locations.items(), key=lambda x: -x[1]):
        print(f"    {loc}: {count}")
    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(description="Networking Event Tracker")
    parser.add_argument("--list", action="store_true", help="List all events")
    parser.add_argument("--add", action="store_true", help="Add new event")
    parser.add_argument("--name", type=str, help="Event name")
    parser.add_argument("--date", type=str, help="Event date")
    parser.add_argument("--location", type=str, default="Bangkok", help="Event location")
    parser.add_argument("--category", type=str, default="meetup", help="Event category")
    parser.add_argument("--tags", type=str, help="Comma-separated tags")
    parser.add_argument("--url", type=str, default="", help="Event URL")
    parser.add_argument("--search", type=str, nargs="+", help="Search events")
    parser.add_argument("--rsvp", type=str, help="RSVP for event ID")
    parser.add_argument("--cancel-rsvp", type=str, help="Cancel RSVP for event ID")
    parser.add_argument("--attended", type=str, help="Mark event as attended")
    parser.add_argument("--import", action="store_true", help="Import recurring events")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()

    if args.list:
        list_events()
        return

    if args.stats:
        stats()
        return

    if getattr(args, "import"):
        import_recurring()
        return

    if args.add:
        if not args.name:
            print("❌ --name is required")
            return
        tags = args.tags.split(",") if args.tags else []
        event = add_event(args.name, args.date, args.location, args.category, tags, args.url)
        print(f"✅ Added: {event['name']} ({event['id']})")
        return

    if args.search:
        search_events(args.search)
        return

    if args.rsvp:
        update_rsvp(args.rsvp, True)
        return

    if args.cancel_rsvp:
        update_rsvp(args.cancel_rsvp, False)
        return

    if args.attended:
        mark_attended(args.attended)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
