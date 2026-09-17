"""Public social-search lead normalisation for property research.

The collector consumes search-engine result metadata only.  It does not crawl
or authenticate to Facebook, Instagram, TikTok, LINE, or private groups.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

from .lead_extraction import CONTACT_FIELDS, SOCIAL_HOSTS, _clean_url, extract_contact_details


SOCIAL_FIELDNAMES = [
    "captured_at",
    # The property.v1 capture contract uses scraped_at as its common event
    # field. Keep captured_at too so social rows retain their source-specific
    # name while remaining replayable through the shared lake contract.
    "scraped_at",
    "social_query",
    "title",
    "type",
    "url",
    "description",
    "source_channel",
    "source_platform",
    *CONTACT_FIELDS,
]


def _platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return SOCIAL_HOSTS.get(host, "")


def extract_social_leads(
    results: Iterable[dict[str, Any]],
    query: str,
    captured_at: str | None = None,
) -> list[dict[str, Any]]:
    """Normalise public social URLs and their indexed text into review rows."""

    timestamp = captured_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        raw_url = str(result.get("url") or "")
        url = _clean_url(raw_url)
        platform = _platform(url)
        if not url or not platform or url in seen:
            continue
        seen.add(url)
        title = str(result.get("title") or "").strip()[:200]
        description = str(result.get("description") or result.get("snippet") or "").strip()[:500]
        text = f"{title} {description}".strip()
        details = extract_contact_details(text, url)
        # The indexed result URL is itself the public social source. Keep it
        # in the platform field even when the snippet contains no repeated URL.
        platform_field = f"contact_{platform}"
        details[platform_field] = details.get(platform_field) or url
        details["contact_social_urls"] = details.get("contact_social_urls") or url
        rows.append(
            {
                "captured_at": timestamp,
                "scraped_at": timestamp,
                "social_query": str(query or "")[:240],
                "title": title,
                "type": "social_property_lead",
                "url": url,
                "description": description,
                "source_channel": "social_search",
                "source_platform": platform,
                **details,
            }
        )
    return rows
