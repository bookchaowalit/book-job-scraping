#!/usr/bin/env python3
"""Capture bounded Kaidee marketplace listings from server-rendered HTML.

Kaidee does not expose a source-specific API in this workflow, so this adapter
uses the public HTML page and its embedded ``__NEXT_DATA__`` payload. This repo
is the collection producer; the downstream marketplace data product owns
durable lake ingestion and APIs.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - requirements.txt supplies both
    raise RuntimeError("httpx and beautifulsoup4 are required for Kaidee capture") from exc


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "exported"
SOURCE_URL = "https://www.kaidee.com/"
MAX_PAGES = 5
MAX_ROWS = 200
LISTING_ID_RE = re.compile(r"(?:product|ad)[-_](\d+)", re.IGNORECASE)
PRICE_RE = re.compile(r"\d+(?:[,.]\d+)*")
ALLOWED_HOST = re.compile(r"(?:[a-z0-9-]+\.)*kaidee\.com", re.IGNORECASE)
SNAPSHOT_FIELDS = [
    "captured_at",
    "listing_id",
    "title",
    "price_thb",
    "currency",
    "purpose",
    "category",
    "condition",
    "location",
    "url",
    "image_url",
    "seller_role",
    "first_approved_at",
    "source_url",
]
HISTORY_FIELDS = ["captured_at", "listing_id", "price_thb", "category", "location", "url"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_values(values: Iterable[str] | str | None, default: list[str]) -> list[str]:
    if values is None:
        values = default
    if isinstance(values, str):
        values = values.split(",")
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def canonical_url(value: str, base_url: str = SOURCE_URL) -> str:
    """Normalize a Kaidee listing URL and reject off-site destinations."""

    candidate = urljoin(base_url, str(value).strip())
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not ALLOWED_HOST.fullmatch(host):
        raise ValueError("Kaidee URL must remain on an HTTPS kaidee.com host")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def normalize_urls(urls: Iterable[str] | str | None) -> list[str]:
    normalized = [canonical_url(url) for url in _as_values(urls, [SOURCE_URL])]
    if not normalized or len(normalized) > MAX_PAGES:
        raise ValueError(f"urls must contain 1-{MAX_PAGES} Kaidee pages")
    return normalized


def _price_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = PRICE_RE.search(str(value).replace(" ", ""))
        if not match:
            return None
        try:
            number = float(match.group(0).replace(",", ""))
        except ValueError:
            return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _iso_datetime(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime string") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def _listing_id(value: Any) -> str:
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError("Kaidee listing ID is required")
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise ValueError("Kaidee listing ID must be a positive integer")
    return text


def _next_data(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("#__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("Kaidee page is missing __NEXT_DATA__")
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError as exc:
        raise ValueError("Kaidee __NEXT_DATA__ is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kaidee __NEXT_DATA__ must be a JSON object")
    return payload


def _href_by_id(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "")
        match = LISTING_ID_RE.search(href)
        if match:
            try:
                links.setdefault(match.group(1), canonical_url(href))
            except ValueError:
                continue
    return links


def _candidate_ads(page_props: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("latestAd", "latestAds"):
        values = page_props.get(key)
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, dict))
    homepage = page_props.get("homepageData")
    if isinstance(homepage, dict):
        for key in ("recommendListing", "latestCategoryAds", "recentlyViewAds"):
            values = homepage.get(key)
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
    return candidates


def parse_html(
    html: str,
    source_url: str = SOURCE_URL,
    categories: Iterable[str] | str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse embedded listing data, keeping only priced, canonical listings."""

    payload = _next_data(html)
    props = payload.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    if not isinstance(page_props, dict):
        raise ValueError("Kaidee page is missing pageProps")
    allowed_categories = {value.casefold() for value in _as_values(categories, [])}
    hrefs = _href_by_id(html)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _candidate_ads(page_props):
        listing_id = _listing_id(item.get("id"))
        if listing_id in seen:
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        category = str(item.get("categoryName") or "").strip()
        if allowed_categories and category.casefold() not in allowed_categories:
            continue
        price = _price_value(item.get("price"))
        if price is None:
            continue
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        url = hrefs.get(listing_id, canonical_url(f"/product-{listing_id}", source_url))
        seen.add(listing_id)
        rows.append(
            {
                "listing_id": listing_id,
                "title": title[:500],
                "price_thb": price,
                "currency": "THB",
                "purpose": str(item.get("purposeName") or "").strip(),
                "category": category,
                "condition": str(item.get("conditionName") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "url": url,
                "image_url": str(item.get("image") or "").strip(),
                "seller_role": str((item.get("member") or {}).get("role") or "").strip()
                if isinstance(item.get("member"), dict)
                else "",
                "first_approved_at": _iso_datetime(item.get("firstApprovedTime"), "firstApprovedTime"),
                "source_url": canonical_url(source_url),
            }
        )
        if len(rows) >= MAX_ROWS:
            break
    return payload, rows


def fetch_pages(urls: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_pages: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in urls:
        response = httpx.get(
            url,
            headers={"User-Agent": "book-job-scraping/1.0"},
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload, page_rows = parse_html(response.text, url)
        raw_pages[url] = payload
        for row in page_rows:
            if row["listing_id"] not in seen:
                seen.add(row["listing_id"])
                rows.append(row)
    if not rows:
        raise ValueError("Kaidee pages contained no priced listings")
    return {"pages": raw_pages}, rows[:MAX_ROWS]


def write_raw(raw: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "kaidee_classifieds_raw.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def write_snapshot(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "kaidee_classifieds.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "captured_at": captured_at})
    return path


def append_history(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "kaidee_classifieds_history.csv"
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({**row, "captured_at": captured_at})
    return path


class KaideeScraper:
    """Scheduler adapter for bounded Kaidee HTML capture."""

    def __init__(
        self,
        urls: Iterable[str] | str | None = None,
        categories: Iterable[str] | str | None = None,
        min_price: float | str | None = None,
        max_price: float | str | None = None,
        output_dir: str | Path | None = None,
        **_: Any,
    ) -> None:
        self.urls = normalize_urls(urls)
        self.categories = _as_values(categories, [])
        self.min_price = float(min_price) if min_price not in (None, "") else None
        self.max_price = float(max_price) if max_price not in (None, "") else None
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("min_price must be non-negative")
        if self.max_price is not None and self.max_price <= 0:
            raise ValueError("max_price must be greater than zero")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must not exceed max_price")
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

    async def run(self, **_: Any) -> list[dict[str, Any]]:
        raw, rows = fetch_pages(self.urls)
        captured_at = _utc_now()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if self.categories and row["category"].casefold() not in {value.casefold() for value in self.categories}:
                continue
            if self.min_price is not None and row["price_thb"] < self.min_price:
                continue
            if self.max_price is not None and row["price_thb"] > self.max_price:
                continue
            filtered.append(row)
        if not filtered:
            raise ValueError("Kaidee pages contained no listings after configured filters")
        raw_path = write_raw(raw, self.output_dir)
        snapshot_path = write_snapshot(filtered, captured_at, self.output_dir)
        history_path = append_history(filtered, captured_at, self.output_dir)
        print(f"[kaidee_classifieds] {len(filtered)} listings -> {snapshot_path}")
        return [
            {
                "source": "kaidee_classifieds",
                "count": len(filtered),
                "output": str(snapshot_path),
                "history": str(history_path),
                "raw": str(raw_path),
            }
        ]


if __name__ == "__main__":
    import asyncio

    asyncio.run(KaideeScraper().run())
