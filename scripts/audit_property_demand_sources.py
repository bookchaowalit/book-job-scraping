#!/usr/bin/env python3
"""Audit major public property/community sources for the demand lane.

This command stores only source metadata and HTTP/robots results. It does not
save page content, enumerate listings, crawl profiles, or treat a listing as a
buyer/renter demand record.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "exported" / "property_demand_source_audit.csv"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SoloEmpirePropertyResearch/1.0"
SOURCE_AUDIT_FIELDS = [
    "observed_at",
    "source_platform",
    "source_url",
    "source_role",
    "demand_capability",
    "collection_decision",
    "http_status",
    "robots_status",
    "robots_allowed",
    "access_status",
    "evidence",
    "next_action",
]

# These are deliberately source roles, not lead rows. A portal can be useful
# for supply intelligence while remaining invalid for the demand handoff.
SOURCE_REGISTRY = [
    {
        "source_platform": "pantip",
        "source_url": "https://pantip.com/search?q=%E0%B8%AB%E0%B8%B2%E0%B8%84%E0%B8%AD%E0%B8%99%E0%B9%82%E0%B8%94%E0%B9%80%E0%B8%8A%E0%B9%88%E0%B8%B2",
        "source_role": "public_forum",
        "demand_capability": "demand_capable",
        "collection_decision": "include_demand",
        "evidence": "Public topic pages contain first-person buyer/renter requests.",
        "next_action": "Use bounded topic parser and human review.",
    },
    {
        "source_platform": "kaidee",
        "source_url": "https://baan.kaidee.com/",
        "source_role": "marketplace",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public categories expose sale/rent listings, not wanted ads.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "ennxo",
        "source_url": "https://www.ennxo.com/",
        "source_role": "marketplace",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public property pages expose sale/rent listings, not wanted ads.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "propertyhub",
        "source_url": "https://propertyhub.in.th/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public navigation is for selling and renting properties.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "renthub",
        "source_url": "https://www.renthub.in.th/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public pages expose rooms/apartments offered for rent.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "livinginsider",
        "source_url": "https://www.livinginsider.com/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public portal is a property sale/rent listing surface.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "zmyhome",
        "source_url": "https://zmyhome.com/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public portal is a property listing surface.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "meezub",
        "source_url": "https://www.meezub.com/",
        "source_role": "marketplace",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public marketplace pages expose property listings.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "dotproperty",
        "source_url": "https://www.dotproperty.co.th/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public portal is a property sale/rent listing surface.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "baania",
        "source_url": "https://www.baania.com/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public portal is a property listing and market surface.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "hipflat",
        "source_url": "https://www.hipflat.co.th/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "exclude_demand",
        "evidence": "Public portal is a property sale/rent listing surface.",
        "next_action": "Keep in supply lane; do not add to demand CSV.",
    },
    {
        "source_platform": "ddproperty",
        "source_url": "https://www.ddproperty.com/",
        "source_role": "property_portal",
        "demand_capability": "listing_only",
        "collection_decision": "blocked",
        "evidence": "Listing source is currently blocked by an HTTP challenge.",
        "next_action": "Do not bypass challenge; keep source disabled.",
    },
    {
        "source_platform": "reddit_thailand",
        "source_url": "https://www.reddit.com/r/Thailand/search.rss?q=condo%20rent&restrict_sr=1&sort=new&t=year",
        "source_role": "public_forum",
        "demand_capability": "demand_capable",
        "collection_decision": "blocked",
        "evidence": "Public RSS/JSON access is robots-disallowed; prior direct probes returned HTTP 403.",
        "next_action": "Use an approved official API or user-provided export.",
    },
    {
        "source_platform": "aseann",
        "source_url": "https://aseann.com/search/?q=condo",
        "source_role": "public_forum",
        "demand_capability": "demand_capable",
        "collection_decision": "blocked",
        "evidence": "Public endpoint timed out during bounded HTTP probe.",
        "next_action": "Do not retry aggressively; obtain an approved export/API.",
    },
    {
        "source_platform": "facebook_public_groups",
        "source_url": "https://www.facebook.com/",
        "source_role": "social",
        "demand_capability": "demand_capable",
        "collection_decision": "manual_export_only",
        "evidence": "Direct platform crawling is outside this lane; user-selected public export is supported.",
        "next_action": "Use the local rendered-post export flow for public groups only.",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _robots_url(source_url: str) -> str:
    parsed = urlsplit(source_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _robots_allowed(robots_body: str, robots_url: str, source_url: str) -> str:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(robots_body.splitlines())
    if parser.can_fetch(USER_AGENT, source_url):
        return "yes"
    return "no"


def audit_sources(*, timeout: float = 8.0, delay: float = 1.0) -> list[dict[str, str]]:
    """Probe source metadata without retaining page content."""

    observed_at = _utc_now()
    rows: list[dict[str, str]] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json"},
        follow_redirects=False,
        timeout=max(1.0, min(float(timeout), 30.0)),
    ) as client:
        for index, source in enumerate(SOURCE_REGISTRY):
            row = {field: "" for field in SOURCE_AUDIT_FIELDS}
            row.update({key: str(value) for key, value in source.items() if key in row})
            row["observed_at"] = observed_at
            if source["collection_decision"] == "manual_export_only":
                row["access_status"] = "manual_export_only"
                rows.append(row)
                continue

            robots_url = _robots_url(source["source_url"])
            try:
                robots = client.get(robots_url)
                row["robots_status"] = str(robots.status_code)
                if robots.status_code == 200:
                    row["robots_allowed"] = _robots_allowed(robots.text, robots_url, source["source_url"])
                else:
                    row["robots_allowed"] = "unknown"
            except httpx.HTTPError:
                row["robots_status"] = "error"
                row["robots_allowed"] = "unknown"

            if row["robots_allowed"] == "no":
                row["access_status"] = "robots_disallowed"
                rows.append(row)
                continue

            if delay and index < len(SOURCE_REGISTRY) - 1:
                time.sleep(max(0.0, min(float(delay), 30.0)))
            try:
                response = client.get(source["source_url"])
                row["http_status"] = str(response.status_code)
                if response.status_code in {200, 204}:
                    row["access_status"] = "reachable"
                elif response.status_code in {301, 302, 303, 307, 308}:
                    row["access_status"] = "redirect"
                elif response.status_code in {401, 403, 429}:
                    row["access_status"] = "blocked"
                else:
                    row["access_status"] = "http_error"
            except httpx.TimeoutException:
                row["http_status"] = "timeout"
                row["access_status"] = "timeout"
            except httpx.HTTPError:
                row["http_status"] = "error"
                row["access_status"] = "http_error"
            rows.append(row)
    return rows


def write_audit_csv(rows: list[dict[str, str]], output: Path) -> int:
    """Write source metadata only and return row count."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_AUDIT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in SOURCE_AUDIT_FIELDS} for row in rows)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="Print redacted summary JSON")
    args = parser.parse_args(argv)

    rows = audit_sources(timeout=args.timeout, delay=args.delay)
    count = write_audit_csv(rows, args.output)
    summary = {
        "status": "ok",
        "rows": count,
        "output": str(args.output),
        "decisions": {},
    }
    for row in rows:
        decision = row["collection_decision"]
        summary["decisions"][decision] = summary["decisions"].get(decision, 0) + 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"property_demand_source_audit: {count} sources -> {args.output}")
        print(f"decisions={summary['decisions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
