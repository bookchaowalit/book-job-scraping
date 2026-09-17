#!/usr/bin/env python3
"""Capture TG Condo's public condo-rental RSS feed.

The RSS endpoint is the default acquisition path: it returns public listing
metadata without an API key and without crawling the site's search UI.  Contact
details are optional and deliberately gated because a public page can still
contain personal data.  This adapter never submits the site's contact form,
logs in, follows private links, or sends outreach.
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import feedparser
    import httpx
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - requirements.txt supplies dependencies
    raise RuntimeError(
        "feedparser, httpx, and beautifulsoup4 are required for TG Condo capture"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from property.lead_extraction import CONTACT_FIELDS, enrich_listing, extract_contact_details

DEFAULT_OUTPUT_DIR = ROOT / "data" / "exported"
FEED_URL = "https://www.tgcondo.com/Property-Types/condo-for-rent?format=feed&type=rss"
MAX_ENTRIES = 100
MAX_CONTACT_PAGES = 5
MAX_FEED_BYTES = 2_000_000
CONTACT_APPROVED_ENV = "TGCONDO_CONTACT_STORAGE_APPROVED"
CONTACT_RETENTION_ENV = "TGCONDO_RETENTION_UNTIL"
CONTACT_TERMS_ENV = "TGCONDO_TERMS_BASIS_REF"
REQUEST_HEADERS = {
    "User-Agent": "book-job-scraping/1.0 (+public RSS capture)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

FIELDNAMES = [
    "scraped_at",
    "title",
    "type",
    "listing_type",
    "url",
    "price_raw",
    "price",
    "bedrooms",
    "bathrooms",
    "area_sqm",
    "location",
    "description",
    "source_channel",
    "source_platform",
    *CONTACT_FIELDS,
]
HISTORY_FIELDS = FIELDNAMES

_PRICE_PATTERNS = (
    re.compile(
        r"(?P<value>[\d][\d,]*(?:\.\d+)?)\s*(?:฿|THB|บาท)"
        r"(?:\s*/\s*(?:month|mo|เดือน)|\s*per\s*month)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>[\d][\d,]*(?:\.\d+)?)\s*(?:/\s*(?:month|mo|เดือน)|per\s*month)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:฿|THB)\s*(?P<value>[\d][\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
)
_ROOM_VALUE = r"(?:\d+(?:\.\d+)?|one|two|three|four|five)"
_BEDROOM_RE = re.compile(
    rf"(?<![\d.])(?P<value>{_ROOM_VALUE})\s*(?:bedrooms?|beds?|ห้องนอน)",
    re.IGNORECASE,
)
_BATHROOM_RE = re.compile(
    rf"(?<![\d.])(?P<value>{_ROOM_VALUE})\s*(?:bathrooms?|baths?|ห้องน้ำ)",
    re.IGNORECASE,
)
_AREA_RE = re.compile(
    r"(?<![\d.])(?P<value>\d+(?:\.\d+)?)\s*(?:sq\.?\s*m\.?|sqm|m²|ตารางเมตร)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+66|0)(?:[\s().-]*\d){8,10}(?!\d)")
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _is_tgcondo_host(host: str) -> bool:
    normalized = (host or "").lower().removeprefix("www.")
    return normalized == "tgcondo.com" or normalized.endswith(".tgcondo.com")


def normalize_feed_url(value: str = FEED_URL) -> str:
    """Accept only TG Condo's documented condo-rent RSS endpoint."""

    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme.lower() != "https" or not _is_tgcondo_host(parsed.hostname or ""):
        raise ValueError("TG Condo feed URL must use an HTTPS tgcondo.com host")
    if parsed.path.rstrip("/").lower() != "/property-types/condo-for-rent":
        raise ValueError("TG Condo feed URL must target the condo-for-rent feed")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if sorted(query) != [("format", "feed"), ("type", "rss")]:
        raise ValueError("TG Condo feed URL must include format=feed&type=rss")
    return urlunsplit(
        (
            "https",
            (parsed.hostname or "").lower(),
            "/Property-Types/condo-for-rent",
            urlencode({"format": "feed", "type": "rss"}),
            "",
        )
    )


def canonical_listing_url(value: str) -> str:
    """Keep only canonical HTTPS TG Condo listing URLs."""

    parsed = urlsplit(str(value or "").strip())
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme.lower() != "https"
        or not _is_tgcondo_host(parsed.hostname or "")
        or not path.lower().startswith("/property/")
        or len(path.split("/", 2)[-1]) < 2
    ):
        raise ValueError("TG Condo listing URL must be an HTTPS /Property/<slug> URL")
    return urlunsplit(("https", (parsed.hostname or "").lower(), path, "", ""))


def _clean_text(value: Any, limit: int) -> str:
    text = html_lib.unescape(str(value or ""))
    if "<" in text or ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _number(match: re.Match[str] | None) -> float | int | None:
    if not match:
        return None
    raw = match.group("value").lower()
    value = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.get(raw)
    if value is None:
        value = float(raw)
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _price(text: str) -> tuple[str, float] | tuple[str, None]:
    """Return the last explicit currency/month price, avoiding room counts."""

    for pattern in _PRICE_PATTERNS:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        match = matches[-1]
        raw = re.sub(r"\s+", " ", match.group(0)).strip()
        return raw, float(match.group("value").replace(",", ""))
    return "", None


def _location(description: str) -> str:
    for pattern in (
        r"(?:located\s+(?:(?:at|in|on)\s+)?|address\s*:)\s*"
        r"(.+?(?:\bBangkok\b(?:\s+\d{5})?|กรุงเทพ[^,.\n]*|\.|$))",
        r"(?:ที่อยู่|ตั้งอยู่)\s*[:：]?\s*"
        r"(.+?(?:\bBangkok\b(?:\s+\d{5})?|กรุงเทพ[^,.\n]*|\.|$))",
    ):
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1), 240).rstrip(".")
            if value:
                return value
    for line in re.split(r"[\n.]", description):
        line = _clean_text(line, 240)
        if line and ("bangkok" in line.lower() or "กรุงเทพ" in line):
            return line
    return "Bangkok"


def parse_feed(
    raw: bytes | str,
    feed_url: str = FEED_URL,
    limit: int = 40,
) -> tuple[Any, list[dict[str, Any]]]:
    """Parse priced, attributed RSS entries into property.v1 rows."""

    normalize_feed_url(feed_url)
    bounded_limit = max(1, min(int(limit), MAX_ENTRIES))
    parsed = feedparser.parse(raw)
    if not parsed.entries:
        raise ValueError("TG Condo RSS feed contains no entries")
    if not _clean_text(parsed.feed.get("title"), 200):
        raise ValueError("TG Condo RSS feed title is missing")

    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for entry in parsed.entries:
        title = _clean_text(entry.get("title"), 240)
        link = str(entry.get("link") or entry.get("id") or "").strip()
        if not title or not link:
            continue
        try:
            url = canonical_listing_url(link)
        except ValueError:
            continue
        if url in seen_urls:
            continue

        description = _clean_text(
            entry.get("description") or entry.get("summary") or "", 2000
        )
        price_raw, price = _price(title)
        if price is None:
            price_raw, price = _price(description)
        if price is None or price <= 0:
            continue
        text = f"{title} {description}".strip()
        row: dict[str, Any] = {
            "title": title,
            "type": "condo_rent_bkk",
            "listing_type": "condo_rent_bkk",
            "url": url,
            "price_raw": price_raw,
            "price": price,
            "bedrooms": _number(_BEDROOM_RE.search(text)),
            "bathrooms": _number(_BATHROOM_RE.search(text)),
            "area_sqm": _number(_AREA_RE.search(text)),
            "location": _location(description),
            "description": description,
            "source_channel": "listing",
            "source_platform": "tgcondo",
        }
        row = enrich_listing(row, text=text, source_url=url)
        rows.append(row)
        seen_urls.add(url)
        if len(rows) >= bounded_limit:
            break

    if not rows:
        raise ValueError("TG Condo RSS feed contains no priced listing entries")
    return parsed, rows


def fetch_feed(feed_url: str = FEED_URL) -> bytes:
    """Fetch one bounded public RSS response and reject empty/oversized data."""

    normalized_feed_url = normalize_feed_url(feed_url)
    response = httpx.get(
        normalized_feed_url,
        headers=REQUEST_HEADERS,
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    content = response.content
    if not content:
        raise ValueError("TG Condo RSS response is empty")
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("TG Condo RSS response exceeds the bounded size limit")
    final_url = getattr(response, "url", None)
    if final_url:
        normalize_feed_url(str(final_url))
    return content


def _contact_storage_approved() -> bool:
    return (
        os.environ.get(CONTACT_APPROVED_ENV, "").strip().lower()
        in {"1", "true", "yes"}
        and bool(os.environ.get(CONTACT_RETENTION_ENV, "").strip())
        and bool(os.environ.get(CONTACT_TERMS_ENV, "").strip())
    )


def parse_public_agent_contact(html: str, source_url: str) -> dict[str, Any]:
    """Extract explicit, visible agent-card contact signals from one listing.

    The parser reads text and ``mailto:`` links already present in the public
    document.  It does not execute the site's contact form or decode private
    account data.
    """

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    names: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/agent-properties/" not in href.lower():
            continue
        name = _clean_text(anchor.get_text(" ", strip=True), 100)
        if name and name not in names:
            names.append(name)

    nodes = soup.select(
        ".sidecol-cell, .sidecol-email, [class*='agent'], [id*='agent']"
    )
    parts = [f"Agent: {name}" for name in names]
    visible_parts: list[str] = []
    for node in nodes:
        node_text = _clean_text(node.get_text(" ", strip=True), 500)
        for name in names:
            node_text = node_text.replace(name, " ")
        node_text = re.sub(r"\s+", " ", node_text).strip()
        if node_text:
            visible_parts.append(node_text)
    visible = " ".join(visible_parts)
    if visible:
        parts.append(visible)

    phone_match = _PHONE_RE.search(visible)
    if phone_match:
        parts.append(f"Mobile: {phone_match.group(0)}")
    line_match = re.search(
        r"(?:line\s*id|ไลน์\s*ไอดี)\s*[:：=@]?\s*([@A-Za-z0-9._-]{3,64})",
        visible,
        flags=re.IGNORECASE,
    )
    if line_match:
        parts.append(f"Line ID: {line_match.group(1)}")

    emails: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not href.lower().startswith("mailto:"):
            continue
        match = _EMAIL_RE.search(href[7:])
        if match and match.group(0).lower() not in emails:
            emails.append(match.group(0).lower())
    parts.extend(f"Email: {email}" for email in emails)

    context = " ".join(part for part in parts if part).strip()
    if not context:
        return {}
    details = extract_contact_details(context, source_url)
    if not any(
        details.get(field)
        for field in ("contact_name", "contact_phone", "contact_email", "contact_line")
    ):
        return {}
    return details


def fetch_public_agent_contact(url: str) -> dict[str, Any]:
    """Fetch one allowlisted listing page for its visible agent card only."""

    listing_url = canonical_listing_url(url)
    try:
        response = httpx.get(
            listing_url,
            headers={"User-Agent": REQUEST_HEADERS["User-Agent"], "Accept": "text/html"},
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
        final_url = getattr(response, "url", None)
        if final_url:
            canonical_listing_url(str(final_url))
        return parse_public_agent_contact(response.text, listing_url)
    except (httpx.HTTPError, ValueError, TypeError):
        print("[WARN] TG Condo public contact page failed; listing retained without contact")
        return {}


def collect_listings(
    feed_url: str = FEED_URL,
    limit: int = 40,
    include_agent_contact: bool = False,
    max_contacts: int = MAX_CONTACT_PAGES,
    contact_delay_seconds: float = 1.0,
) -> tuple[bytes, list[dict[str, Any]]]:
    """Fetch the RSS feed and optionally enrich a very small contact sample."""

    raw = fetch_feed(feed_url)
    _, rows = parse_feed(raw, feed_url=feed_url, limit=limit)
    if not include_agent_contact:
        return raw, rows
    if not _contact_storage_approved():
        print(
            f"[tgcondo_condo_rent] contact enrichment held: set {CONTACT_APPROVED_ENV}=1 "
            f"with {CONTACT_RETENTION_ENV} and {CONTACT_TERMS_ENV} after review"
        )
        return raw, rows

    retention_until = os.environ[CONTACT_RETENTION_ENV].strip()
    terms_basis_ref = os.environ[CONTACT_TERMS_ENV].strip()
    bounded_contacts = max(0, min(int(max_contacts), MAX_CONTACT_PAGES))
    delay = max(1.0, float(contact_delay_seconds))
    for index, row in enumerate(rows[:bounded_contacts]):
        if index:
            time.sleep(delay)
        details = fetch_public_agent_contact(row["url"])
        if details:
            row.update(details)
            row["retention_until"] = retention_until
            row["terms_basis_ref"] = terms_basis_ref
    return raw, rows


def write_raw(raw: bytes, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tgcondo_condo_rent_raw.xml"
    path.write_bytes(raw)
    return path


def write_snapshot(rows: list[dict[str, Any]], scraped_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tgcondo_condo_rent.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: row.get(field, "") for field in FIELDNAMES} | {"scraped_at": scraped_at}
            )
    return path


def append_history(rows: list[dict[str, Any]], scraped_at: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tgcondo_condo_rent_history.csv"
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: row.get(field, "") for field in HISTORY_FIELDS}
                | {"scraped_at": scraped_at}
            )
    return path


class TGCondoRSSScraper:
    """Scheduler adapter for bounded TG Condo condo-rental RSS capture."""

    def __init__(
        self,
        feed_url: str = FEED_URL,
        limit: int = 40,
        output_dir: str | Path | None = None,
        include_agent_contact: bool = False,
        max_contacts: int = MAX_CONTACT_PAGES,
        contact_delay_seconds: float = 1.0,
        **_: Any,
    ) -> None:
        self.feed_url = normalize_feed_url(feed_url)
        self.limit = max(1, min(int(limit), MAX_ENTRIES))
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.include_agent_contact = bool(include_agent_contact)
        self.max_contacts = max_contacts
        self.contact_delay_seconds = contact_delay_seconds

    async def run(self, **_: Any) -> list[dict[str, Any]]:
        raw, rows = collect_listings(
            feed_url=self.feed_url,
            limit=self.limit,
            include_agent_contact=self.include_agent_contact,
            max_contacts=self.max_contacts,
            contact_delay_seconds=self.contact_delay_seconds,
        )
        scraped_at = _utc_now()
        raw_path = write_raw(raw, self.output_dir)
        snapshot_path = write_snapshot(rows, scraped_at, self.output_dir)
        history_path = append_history(rows, scraped_at, self.output_dir)
        print(
            f"[tgcondo_condo_rent] {len(rows)} listings -> {snapshot_path} "
            f"(raw: {raw_path}, history: {history_path})"
        )
        return [
            {
                "source": "tgcondo_condo_rent",
                "count": len(rows),
                "output": str(snapshot_path),
                "raw": str(raw_path),
                "history": str(history_path),
            }
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed-url", default=FEED_URL)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--include-agent-contact",
        action="store_true",
        help="Opt in to at most five public agent-card pages; requires governance env vars",
    )
    parser.add_argument("--max-contacts", type=int, default=MAX_CONTACT_PAGES)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse live RSS, print count, and do not write files",
    )
    args = parser.parse_args()
    raw, rows = collect_listings(
        feed_url=args.feed_url,
        limit=args.limit,
        include_agent_contact=args.include_agent_contact,
        max_contacts=args.max_contacts,
    )
    if args.dry_run:
        print(f"Found {len(rows)} TG Condo listings from {len(raw)} RSS bytes")
        return 0
    scraped_at = _utc_now()
    raw_path = write_raw(raw, Path(args.output_dir))
    snapshot_path = write_snapshot(rows, scraped_at, Path(args.output_dir))
    history_path = append_history(rows, scraped_at, Path(args.output_dir))
    print(f"Saved {len(rows)} listings to {snapshot_path}")
    print(f"Raw RSS: {raw_path}; history: {history_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
