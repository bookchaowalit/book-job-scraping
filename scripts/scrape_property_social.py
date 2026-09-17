#!/usr/bin/env python3
"""Discover public property leads indexed from social platforms.

Only search-result metadata is used.  This command never logs into or crawls a
social account, bypasses a challenge, or sends a message.  Every row remains a
human-review candidate until the public source and contact signal are checked.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    # The scheduler loads environment variables before importing this module;
    # direct CLI use still works when python-dotenv is installed in the venv.
    pass

from property.social_leads import SOCIAL_FIELDNAMES, extract_social_leads  # noqa: E402


PLATFORM_DOMAINS = {
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "tiktok": "tiktok.com",
    "line": "line.me",
}
DEFAULT_QUERY = "อสังหา กรุงเทพ บ้าน คอนโด (รับ co-agent OR เจ้าของขายเอง OR นายหน้า)"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "exported"
BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_SEARCH_API_KEY_ENV = "BRAVE_SEARCH_API_KEY"
BRAVE_SEARCH_STORAGE_APPROVED_ENV = "BRAVE_SEARCH_STORAGE_APPROVED"
PROPERTY_SOCIAL_RETENTION_UNTIL_ENV = "PROPERTY_SOCIAL_RETENTION_UNTIL"
PROPERTY_SOCIAL_TERMS_BASIS_REF_ENV = "PROPERTY_SOCIAL_TERMS_BASIS_REF"


def _normalise_platforms(platforms: list[str] | str | None) -> list[str]:
    """Resolve platform input and fail closed on an unknown destination."""

    if platforms is None:
        values = list(PLATFORM_DOMAINS)
    elif isinstance(platforms, str):
        values = [platforms]
    else:
        values = platforms
    result: list[str] = []
    for value in values:
        platform = str(value).strip().lower()
        if platform not in PLATFORM_DOMAINS:
            raise ValueError(f"unknown social platform: {value}")
        if platform not in result:
            result.append(platform)
    return result or list(PLATFORM_DOMAINS)


def _storage_approved() -> bool:
    """Require an explicit owner gate before persisting search results."""

    return os.environ.get(BRAVE_SEARCH_STORAGE_APPROVED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _brave_search_api(query: str, limit: int = 20) -> list[dict]:
    """Query the official Brave Search API without scraping its HTML UI."""

    api_key = os.environ.get(BRAVE_SEARCH_API_KEY_ENV, "").strip()
    if not api_key:
        print(
            "[property_social_leads] held: BRAVE_SEARCH_API_KEY is not configured; "
            "HTML search fallback is disabled"
        )
        return []
    bounded_limit = max(1, min(int(limit), 20))
    try:
        response = httpx.get(
            BRAVE_SEARCH_API_URL,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            params={
                "q": query,
                "count": bounded_limit,
                "country": "TH",
                "search_lang": "th",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        print("[WARN] Brave Search API request failed; no social rows collected")
        return []

    results: list[dict] = []
    web = payload.get("web") if isinstance(payload, dict) else None
    web_results = web.get("results", []) if isinstance(web, dict) else []
    if not isinstance(web_results, list):
        return results
    for item in web_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or item.get("snippet") or "").strip()
        if url and title:
            results.append(
                {
                    "url": url,
                    "title": title[:200],
                    "description": description[:500],
                }
            )
        if len(results) >= bounded_limit:
            break
    return results


def _load_fixture(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Load a local synthetic result fixture grouped by supported platform.

    Fixture mode is deliberately separate from the live collector: it never
    calls the network and is intended only for parser/review-flow smoke tests.
    Invalid rows are skipped so one bad synthetic example cannot become a
    persisted lead; malformed fixture documents fail closed with a redacted
    error.
    """

    fixture_path = Path(path)
    try:
        with fixture_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("fixture could not be read as JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("fixture must be a JSON list")

    grouped: dict[str, list[dict[str, Any]]] = {
        platform: [] for platform in PLATFORM_DOMAINS
    }
    for item in payload:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or "").strip().lower()
        if platform not in PLATFORM_DOMAINS:
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        grouped[platform].append(
            {
                "url": url,
                "title": title[:200],
                "description": str(
                    item.get("description") or item.get("snippet") or ""
                ).strip()[:500],
            }
        )
    return grouped


def collect_social_leads(
    query: str = DEFAULT_QUERY,
    platforms: list[str] | str | None = None,
    limit: int = 50,
    fixture_path: str | Path | None = None,
) -> list[dict]:
    """Search selected public indexes and return deduplicated review rows.

    Passing ``fixture_path`` switches to a local, synthetic, offline input and
    intentionally bypasses the live storage/API gate.  Live collection still
    requires explicit storage approval before any network request.
    """

    selected = _normalise_platforms(platforms)
    fixture_rows = _load_fixture(fixture_path) if fixture_path is not None else None
    if fixture_rows is None and not _storage_approved():
        print(
            "[property_social_leads] held: result storage requires an approved "
            "Brave Search plan; set BRAVE_SEARCH_STORAGE_APPROVED=1 only after review"
        )
        return []
    bounded_limit = max(1, min(int(limit), 100))
    rows: list[dict] = []
    seen: set[str] = set()
    per_platform = max(1, math.ceil(bounded_limit / max(1, len(selected))))
    retention_until = os.environ.get(PROPERTY_SOCIAL_RETENTION_UNTIL_ENV, "").strip()
    terms_basis_ref = os.environ.get(PROPERTY_SOCIAL_TERMS_BASIS_REF_ENV, "").strip()
    for platform in selected:
        domain = PLATFORM_DOMAINS[platform]
        search_query = f"site:{domain} {query}".strip()
        if fixture_rows is not None:
            results = fixture_rows.get(platform, [])[:per_platform]
        else:
            results = _brave_search_api(search_query, limit=per_platform)
        for row in extract_social_leads(results, query=search_query):
            if retention_until:
                row["retention_until"] = retention_until
            if terms_basis_ref:
                row["terms_basis_ref"] = terms_basis_ref
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            rows.append(row)
    return rows[:bounded_limit]


def save_social_leads(rows: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "property_social_leads.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOCIAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in SOCIAL_FIELDNAMES} for row in rows)
    return path


class PropertySocialLeadScraper:
    """Scheduler wrapper for public, search-derived social lead discovery."""

    def __init__(
        self,
        query: str = DEFAULT_QUERY,
        platforms: list[str] | None = None,
        limit: int = 50,
        output_dir: str | Path | None = None,
        fixture_path: str | Path | None = None,
        **_: object,
    ) -> None:
        self.query = query
        self.platforms = _normalise_platforms(platforms)
        self.limit = limit
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.fixture_path = Path(fixture_path) if fixture_path else None

    async def run(self, **_: object) -> list[dict]:
        rows = collect_social_leads(
            self.query,
            self.platforms,
            self.limit,
            fixture_path=self.fixture_path,
        )
        path = save_social_leads(rows, self.output_dir)
        print(f"[property_social_leads] {len(rows)} public results -> {path}")
        return [{"source": "property_social_leads", "count": len(rows), "output": str(path)}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--platform", action="append", choices=sorted(PLATFORM_DOMAINS))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Read a local synthetic JSON fixture (offline smoke test; no network)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Search and report count without writing rows")
    args = parser.parse_args()

    rows = collect_social_leads(
        args.query,
        args.platform,
        args.limit,
        fixture_path=args.fixture,
    )
    if args.dry_run:
        print(f"Found {len(rows)} public social results requiring human review")
    else:
        print(f"Saved {len(rows)} public social results to {save_social_leads(rows, Path(args.output_dir))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
