"""Bounded public HTML adapters for major property listing portals.

This module is a supply/listing producer.  It never emits property-seeker
demand rows and does not authenticate to a portal or bypass an access gate.
Each source has an explicit parser because generic text extraction can turn
navigation, IDs, or years into false property facts.
"""

from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from property.lead_extraction import CONTACT_FIELDS, enrich_listing
from property.listing_config import build_page_url, property_source_platform


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "data" / "exported"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SoloEmpirePropertyResearch/1.0"
MAX_RESPONSE_BYTES = 4_000_000


@dataclass(frozen=True)
class PortalSource:
    platform: str
    url: str
    listing_type: str
    path_pattern: str


PORTAL_SOURCES = {
    "ennxo": PortalSource(
        "ennxo",
        "https://www.ennxo.com/condo/for-sale",
        "condo_sale_thailand",
        r"^/product/\d+$",
    ),
    "propertyhub": PortalSource(
        "propertyhub",
        "https://propertyhub.in.th/เช่าคอนโด",
        "condo_rent_thailand",
        r"^/listings/[^/]+$",
    ),
    "livinginsider": PortalSource(
        "livinginsider",
        "https://www.livinginsider.com/condo-rent",
        "condo_rent_thailand",
        r"^/detail/[^/]+$",
    ),
    "zmyhome": PortalSource(
        "zmyhome",
        "https://zmyhome.com/rent/condo?maxPriceFilter=10000",
        "condo_rent_thailand",
        r"^/property/[A-Za-z0-9_-]+$",
    ),
}

PORTAL_FIELDNAMES = [
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

_PRICE_RE = re.compile(
    r"(?:(?:฿|THB)\s*(?P<currency>\d[\d,]*(?:\.\d+)?)\s*(?P<currency_unit>[KkMm]|ล้าน)?|"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>[KkMm]|ล้าน)?\s*"
    r"(?P<hint>บาท|บ/ด|/\s*(?:เดือน|ด\.? )|per\s*month))",
    re.IGNORECASE,
)


def _number(value: str, unit: str = "") -> float:
    amount = float(value.replace(",", ""))
    unit = unit.casefold()
    if unit == "k":
        return amount * 1_000
    if unit == "m" or unit == "ล้าน":
        return amount * 1_000_000
    return amount


def _prices(text: str) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for match in _PRICE_RE.finditer(text):
        amount = match.group("currency") or match.group("amount")
        unit = match.group("currency_unit") or match.group("unit") or ""
        if not amount:
            continue
        value = _number(amount, unit)
        if value > 0:
            values.append((match.group(0).strip(), value))
    return values


def _select_price(text: str, listing_type: str) -> tuple[str, float] | None:
    """Choose the price whose nearby text matches the listing lane."""

    prices = _prices(text)
    if not prices:
        return None
    if "rent" not in listing_type.casefold():
        return prices[0]

    rental_markers = re.compile(
        r"(?:เช่า|rent|/\s*(?:ด\.?|เดือน|month)|per\s*month|บ\s*/\s*ด)",
        flags=re.IGNORECASE,
    )
    matches = list(_PRICE_RE.finditer(text))
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else match.end() + 60
        nearby = text[match.end() : min(next_start, match.end() + 60)]
        if rental_markers.search(nearby):
            amount = match.group("currency") or match.group("amount")
            unit = match.group("currency_unit") or match.group("unit") or ""
            if amount:
                return match.group(0).strip(), _number(amount, unit)
    return prices[0]


def canonical_listing_url(value: str, source_platform: str) -> str:
    """Return a same-source detail URL without query or fragment tracking."""

    value = urldefrag(str(value or "").strip())[0]
    parsed = urlsplit(value)
    source = PORTAL_SOURCES.get(source_platform)
    if source is None:
        return ""
    if not parsed.netloc:
        base = urlsplit(source.url)
        parsed = urlsplit(urlunsplit((base.scheme, base.netloc, parsed.path, parsed.query, "")))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        return ""
    if property_source_platform(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))) != source_platform:
        return ""
    if not re.match(source.path_pattern, parsed.path):
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def _card_text(node: Any) -> str:
    return " ".join(str(node.get_text(" ", strip=True)).split())[:2000]


def _attributes(text: str) -> dict[str, str]:
    fields = {"bedrooms": "", "bathrooms": "", "area_sqm": ""}
    bedroom = re.search(r"(\d+(?:\.\d+)?)\s*(?:bed(?:room)?s?|ห้องนอน|นอน)\b", text, re.I)
    bathroom = re.search(r"(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ห้องน้ำ|น้ำ)\b", text, re.I)
    area = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sqm|sq\.?\s*m|ตร\.?\s*ม|ม\s*2)\b", text, re.I)
    if bedroom:
        fields["bedrooms"] = bedroom.group(1)
    if bathroom:
        fields["bathrooms"] = bathroom.group(1)
    if area:
        fields["area_sqm"] = area.group(1).replace(",", ".")
    return fields


def _title_from_text(text: str, source_platform: str) -> str:
    title = re.sub(r"^พิเศษ\s+\d+\s*/\s*\d+\s*", "", text, flags=re.I).strip()
    prices = _prices(title)
    if prices:
        title = title[: title.find(prices[0][0])].strip(" -|,")
    if source_platform == "zmyhome":
        title = re.sub(r"\s+Updated\b.*$", "", title, flags=re.I)
    return title[:200]


def _row(
    *,
    source_platform: str,
    listing_type: str,
    url: str,
    title: str,
    card_text: str,
    price_raw: str,
    price: float,
) -> dict[str, Any] | None:
    canonical = canonical_listing_url(url, source_platform)
    title = " ".join(title.split()).strip(" -|,")
    if not canonical or not title or price <= 0:
        return None
    row: dict[str, Any] = {
        "title": title,
        "type": listing_type,
        "listing_type": listing_type,
        "url": canonical,
        "price_raw": price_raw,
        "price": price,
        "location": "",
        "description": card_text[:500],
        "source_channel": "listing",
        "source_platform": source_platform,
        **_attributes(card_text),
    }
    row = enrich_listing(row, text=card_text, source_url=canonical)
    row["source_channel"] = "listing"
    row["source_platform"] = source_platform
    return row


def _parse_ennxo(soup: BeautifulSoup, listing_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for anchor in soup.select('a[href*="/product/"]'):
        url = anchor.get("href", "")
        text = _card_text(anchor)
        price = _select_price(text, listing_type)
        if not price:
            continue
        row = _row(
            source_platform="ennxo",
            listing_type=listing_type,
            url=url,
            title=_title_from_text(text, "ennxo"),
            card_text=text,
            price_raw=price[0],
            price=price[1],
        )
        if row:
            rows.append(row)
    return rows


def _parse_propertyhub(soup: BeautifulSoup, listing_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    anchors = soup.select('a[data-za-nav="Listing Card"], a[href*="/listings/"]')
    for anchor in anchors:
        url = anchor.get("href", "")
        card = anchor.find_parent(class_=re.compile(r"sc-15whpuu-2")) or anchor
        text = _card_text(card)
        price = _select_price(text, listing_type)
        if not price:
            continue
        row = _row(
            source_platform="propertyhub",
            listing_type=listing_type,
            url=url,
            title=_card_text(anchor),
            card_text=text,
            price_raw=price[0],
            price=price[1],
        )
        if row:
            rows.append(row)
    return rows


def _parse_livinginsider(soup: BeautifulSoup, listing_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for anchor in soup.select('a[href*="/detail/"]'):
        card = anchor.find_parent(class_=re.compile(r"card-item-wrap")) or anchor
        text = _card_text(card)
        price = _select_price(text, listing_type)
        if not price:
            continue
        title = anchor.get("title") or _title_from_text(text, "livinginsider")
        row = _row(
            source_platform="livinginsider",
            listing_type=listing_type,
            url=anchor.get("href", ""),
            title=title,
            card_text=text,
            price_raw=price[0],
            price=price[1],
        )
        if row:
            rows.append(row)
    return rows


def _parse_zmyhome(soup: BeautifulSoup, listing_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for anchor in soup.select('a[href*="/property/"]'):
        card = anchor.find_parent("article") or anchor
        text = _card_text(card)
        price = _select_price(text, listing_type)
        if not price:
            continue
        heading = card.find(["h2", "h3", "h4"])
        title = _card_text(heading) if heading else _title_from_text(text, "zmyhome")
        row = _row(
            source_platform="zmyhome",
            listing_type=listing_type,
            url=anchor.get("href", ""),
            title=title,
            card_text=text,
            price_raw=price[0],
            price=price[1],
        )
        if row:
            rows.append(row)
    return rows


def parse_portal_html(
    html: str,
    source_platform: str,
    listing_type: str | None = None,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    """Parse one bounded source page into priced supply rows."""

    source = PORTAL_SOURCES.get(source_platform)
    if source is None:
        raise ValueError(f"unsupported portal source: {source_platform}")
    soup = BeautifulSoup(html or "", "html.parser")
    resolved_type = listing_type or source.listing_type
    parsers = {
        "ennxo": _parse_ennxo,
        "propertyhub": _parse_propertyhub,
        "livinginsider": _parse_livinginsider,
        "zmyhome": _parse_zmyhome,
    }
    rows = parsers[source_platform](soup, resolved_type)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if max_price is not None and float(row.get("price") or 0) > max_price:
            continue
        key = row["url"]
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _robots_allowed(client: httpx.Client, url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        response = client.get(robots_url)
    except httpx.HTTPError:
        return True
    if response.status_code != 200:
        return True
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def fetch_portal_html(
    url: str,
    *,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> str:
    """Fetch public HTML with same-source, robots, and size bounds."""

    platform = property_source_platform(url)
    if not platform or platform not in PORTAL_SOURCES:
        raise ValueError(f"unsupported portal URL: {url}")
    owns_client = client is None
    http_client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        follow_redirects=True,
        timeout=max(1.0, min(float(timeout), 30.0)),
    )
    try:
        if not _robots_allowed(http_client, url):
            raise PermissionError(f"robots.txt disallows {platform}")
        response = http_client.get(url)
        response.raise_for_status()
        if property_source_platform(str(response.url)) != platform:
            raise ValueError(f"redirect left source host: {response.url}")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        return response.text
    finally:
        if owns_client:
            http_client.close()


def _write_snapshot(rows: list[dict[str, Any]], output_dir: Path, output_stem: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_stem}.csv"
    scraped_at = datetime.now(timezone.utc).isoformat()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PORTAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["scraped_at"] = scraped_at
            writer.writerow({field: row.get(field, "") for field in PORTAL_FIELDNAMES})
    return path


class PortalPropertyScraper:
    """Scheduler adapter for one explicitly configured listing portal."""

    def __init__(
        self,
        source: str,
        type: str | None = None,
        max_pages: int = 1,
        max_price: float | None = None,
        output_dir: str | Path | None = None,
        output_stem: str | None = None,
        delay: float = 1.0,
        timeout: float = 20.0,
        **_: Any,
    ) -> None:
        if source not in PORTAL_SOURCES:
            raise ValueError(f"unsupported portal source: {source}")
        self.source = PORTAL_SOURCES[source]
        self.listing_type = type or self.source.listing_type
        self.max_pages = max(1, min(int(max_pages or 1), 5))
        self.max_price = float(max_price) if max_price not in (None, "") else None
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.output_stem = output_stem or f"property_{source}_listings"
        self.delay = max(0.0, min(float(delay), 30.0))
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def collect(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=True,
            timeout=self.timeout,
        ) as client:
            for page in range(1, self.max_pages + 1):
                page_url = build_page_url(self.source.url, page)
                try:
                    html = fetch_portal_html(page_url, timeout=self.timeout, client=client)
                except (httpx.HTTPError, OSError, PermissionError, ValueError):
                    continue
                rows.extend(
                    parse_portal_html(
                        html,
                        self.source.platform,
                        self.listing_type,
                        self.max_price,
                    )
                )
                if page < self.max_pages and self.delay:
                    time.sleep(self.delay)
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            deduped.append(row)
        return deduped

    async def run(self, **_: Any) -> list[dict[str, Any]]:
        rows = self.collect()
        path = _write_snapshot(rows, self.output_dir, self.output_stem)
        print(f"[{self.source.platform}] {len(rows)} listings -> {path}")
        return [{"source": self.output_stem, "count": len(rows), "output": str(path)}]