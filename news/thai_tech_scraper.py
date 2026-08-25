#!/usr/bin/env python3
"""Capture Thai technology news from Blognone's public Atom-compatible feed."""

from __future__ import annotations

import csv
import html as html_lib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import feedparser
    import httpx
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - requirements.txt supplies dependencies
    raise RuntimeError("feedparser, httpx, and beautifulsoup4 are required for Blognone capture") from exc


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "exported"
FEED_URL = "https://www.blognone.com/atom.xml"
SOURCE_NAME = "Blognone"
MAX_ENTRIES = 100
ALLOWED_HOST = re.compile(r"(?:[a-z0-9-]+\.)*blognone\.com", re.IGNORECASE)
SNAPSHOT_FIELDS = [
    "captured_at",
    "article_id",
    "title",
    "url",
    "summary",
    "author",
    "section",
    "topics",
    "published_at",
    "updated_at",
    "image_url",
    "source",
    "source_url",
    "feed_title",
]
HISTORY_FIELDS = ["captured_at", "article_id", "title", "url", "published_at", "source"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_url(value: str) -> str:
    parts = urlsplit(str(value).strip())
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not ALLOWED_HOST.fullmatch(host):
        raise ValueError("Blognone article URL must use an HTTPS blognone.com host")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def normalize_feed_url(value: str) -> str:
    url = canonical_url(value)
    if url.rstrip("/") not in {"https://www.blognone.com/atom.xml", "https://www.blognone.com/node/feed"}:
        raise ValueError("Blognone feed URL must be /atom.xml or /node/feed")
    return url


def _clean_text(value: Any, limit: int) -> str:
    text = html_lib.unescape(str(value or ""))
    if "<" in text or ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _published_at(entry: Any) -> str:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return ""


def _topics(entry: Any) -> str:
    values = entry.get("tags")
    if not isinstance(values, list):
        return ""
    topics: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        topic = _clean_text(value.get("term"), 80)
        if topic and topic not in topics:
            topics.append(topic)
    return ",".join(topics[:10])


def _image_url(entry: Any) -> str:
    for key in ("media_content", "media_thumbnail", "enclosures"):
        values = entry.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict) and value.get("url"):
                return str(value["url"]).strip()
    return ""


def _article_id(entry: Any, url: str) -> str:
    match = re.search(r"/node/(\d+)(?:/|$)", url)
    if match:
        return match.group(1)
    return _clean_text(entry.get("id") or url, 300) or url


def parse_feed(raw: bytes | str, feed_url: str = FEED_URL, limit: int = 50) -> tuple[Any, list[dict[str, Any]]]:
    normalized_feed_url = normalize_feed_url(feed_url)
    parsed = feedparser.parse(raw)
    if not parsed.entries:
        raise ValueError("Blognone technology feed contains no entries")
    feed_title = _clean_text(parsed.feed.get("title"), 240)
    if not feed_title:
        raise ValueError("Blognone technology feed title is missing")

    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for entry in parsed.entries[:limit]:
        title = _clean_text(entry.get("title"), 300)
        link = str(entry.get("link") or entry.get("id") or "").strip()
        if not title or not link:
            continue
        try:
            url = canonical_url(link)
        except ValueError:
            continue
        if url in seen_urls:
            continue
        published_at = _published_at(entry)
        if not published_at:
            continue
        rows.append(
            {
                "article_id": _article_id(entry, url),
                "title": title,
                "url": url,
                "summary": _clean_text(entry.get("summary") or entry.get("description"), 1000),
                "author": _clean_text(entry.get("author") or entry.get("dc_creator"), 160),
                "section": "technology",
                "topics": _topics(entry),
                "published_at": published_at,
                "updated_at": _published_at({"updated": entry.get("updated")}),
                "image_url": _image_url(entry),
                "source": SOURCE_NAME,
                "source_url": normalized_feed_url,
                "feed_title": feed_title,
            }
        )
        seen_urls.add(url)
        if len(rows) >= limit:
            break
    if not rows:
        raise ValueError("Blognone technology feed contains no contract-compliant entries")
    return parsed, rows


def fetch_feed(feed_url: str) -> bytes:
    response = httpx.get(
        normalize_feed_url(feed_url),
        headers={
            "User-Agent": "book-job-scraping/1.0",
            "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
        },
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    if not response.content:
        raise ValueError("Blognone technology feed response is empty")
    return response.content


def write_raw(raw: bytes, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "thai_tech_news_raw.xml"
    path.write_bytes(raw)
    return path


def write_snapshot(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "thai_tech_news.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "captured_at": captured_at})
    return path


def append_history(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "thai_tech_news_history.csv"
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({**row, "captured_at": captured_at})
    return path


class ThaiTechNewsScraper:
    """Scheduler adapter for bounded Blognone technology RSS capture."""

    def __init__(
        self,
        feed_url: str = FEED_URL,
        limit: int = 50,
        output_dir: str | Path | None = None,
        **_: Any,
    ) -> None:
        self.feed_url = normalize_feed_url(feed_url)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ENTRIES:
            raise ValueError(f"limit must be an integer from 1 to {MAX_ENTRIES}")
        self.limit = limit
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

    async def run(self, **_: Any) -> list[dict[str, Any]]:
        raw = fetch_feed(self.feed_url)
        _, rows = parse_feed(raw, self.feed_url, self.limit)
        captured_at = _utc_now()
        raw_path = write_raw(raw, self.output_dir)
        snapshot_path = write_snapshot(rows, captured_at, self.output_dir)
        history_path = append_history(rows, captured_at, self.output_dir)
        print(f"[thai_tech_news] {len(rows)} articles -> {snapshot_path}")
        return [
            {
                "source": "thai_tech_news",
                "count": len(rows),
                "output": str(snapshot_path),
                "history": str(history_path),
                "raw": str(raw_path),
            }
        ]


if __name__ == "__main__":
    import asyncio

    asyncio.run(ThaiTechNewsScraper().run())
