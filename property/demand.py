"""Parse first-person property demand from public Pantip HTML pages.

This module is intentionally source-specific and review-only. It extracts the
first post from a public topic page, never follows author profiles, and does
not infer a person's identity or consent to be contacted.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


PANTIP_HOSTS = {"pantip.com", "www.pantip.com"}
TOPIC_PATH_RE = re.compile(r"^/topic/(?P<topic_id>\d+)(?:/|$)")
TOPIC_HREF_RE = re.compile(r"(?:^|/)topic/\d+(?:[/\?#]|$)")
MAX_DEMAND_TEXT = 10000
MAX_FIELD_TEXT = 240

THAI_MONTHS = {
    "ม.ค.": 1,
    "ก.พ.": 2,
    "มี.ค.": 3,
    "เม.ย.": 4,
    "พ.ค.": 5,
    "มิ.ย.": 6,
    "ก.ค.": 7,
    "ส.ค.": 8,
    "ก.ย.": 9,
    "ต.ค.": 10,
    "พ.ย.": 11,
    "ธ.ค.": 12,
}

DEMAND_PATTERNS = (
    ("search_property", r"(?:หา|ตามหา)\s*(?:บ้าน|คอนโด|ห้อง|ที่พัก|อพาร์ตเมนต์|ทาวน์เฮาส์)"),
    ("want_to_rent", r"(?:ต้องการ|อยาก|กำลัง)\s*(?:หา|เช่า)\s*(?:บ้าน|คอนโด|ห้อง|ที่พัก|ห้องพัก)"),
    ("want_to_buy", r"(?:ต้องการ|อยาก|กำลัง)\s*(?:ซื้อ|หาซื้อ)\s*(?:บ้าน|คอนโด|ห้อง|ที่ดิน)"),
    ("rental_request", r"(?:ขอ|รบกวน)\s*(?:คำแนะนำ|สอบถาม).*?(?:เช่า|บ้าน|คอนโด|ห้อง)"),
    ("budgeted_search", r"(?:งบ|ไม่เกิน|เดือนละ|ย้ายเข้า|เข้าอยู่).*?(?:บ้าน|คอนโด|ห้อง|ที่พัก|เช่า)"),
)

SUPPLY_PATTERNS = (
    r"(?:ให้เช่า|ปล่อยเช่า|ปล่อยขาย|ขายเอง|เจ้าของ(?:ห้อง|บ้าน|ทรัพย์)?|owner)",
    r"(?:มีห้อง|มีบ้าน|มีคอนโด).*?(?:ขาย|เช่า|ปล่อย)",
    r"(?:รับ\s*co\s*[- ]?agent|รับ\s*นายหน้า|นายหน้า|เอเจนต์|โบรกเกอร์|\bagent\b|\bbroker\b)",
    r"(?:สนใจติดต่อ|ติดต่อเพื่อดูห้อง|พร้อมโอน)",
)

PERMISSION_PATTERNS = (
    r"(?:ใครมี|ใครพอมี).*?(?:แนะนำ|เสนอ)",
    r"(?:ทัก|ติดต่อ).*?(?:ได้|มาได้)",
    r"(?:คอมเมนต์|หลังไมค์).*?(?:ได้|มาได้)",
)

PROPERTY_TYPES = (
    ("condo", r"คอนโด(?:มิเนียม)?|condo(?:minium)?"),
    ("house", r"บ้านเดี่ยว|บ้าน"),
    ("townhouse", r"ทาวน์เฮาส์|ทาวน์โฮม|townhouse"),
    ("apartment", r"อพาร์ตเมนต์|apartment"),
    ("room", r"ห้องพัก|ห้องเช่า|room"),
    ("land", r"ที่ดิน|land"),
)


def _clean_text(value: Any, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def canonical_topic_url(value: str) -> str:
    """Return a canonical HTTPS Pantip topic URL or raise ``ValueError``."""

    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in PANTIP_HOSTS:
        raise ValueError("source URL must be an HTTPS Pantip topic")
    match = TOPIC_PATH_RE.match(parsed.path)
    if not match:
        raise ValueError("source URL must point to a Pantip topic")
    return urlunsplit(("https", "pantip.com", f"/topic/{match.group('topic_id')}", "", ""))


def search_url(query: str) -> str:
    """Build a Pantip HTML search URL without using a search browser."""

    from urllib.parse import quote_plus

    query_text = _clean_text(query, 160)
    if not query_text:
        raise ValueError("search query must not be empty")
    return f"https://pantip.com/search?q={quote_plus(query_text)}"


def extract_topic_links(html: str, base_url: str = "https://pantip.com/search") -> list[str]:
    """Extract canonical Pantip topic links from a public HTML search page."""

    soup = BeautifulSoup(html or "", "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not TOPIC_HREF_RE.search(href):
            continue
        candidate = urljoin(base_url, href)
        try:
            canonical = canonical_topic_url(candidate)
        except ValueError:
            continue
        if canonical not in seen:
            seen.add(canonical)
            links.append(canonical)
    return links


def _meta_value(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if node and node.get("content"):
            return _clean_text(node.get("content"))
    return ""


def _topic_title(soup: BeautifulSoup) -> str:
    title = _meta_value(soup, "og:title", "twitter:title")
    heading = soup.find("h1")
    if heading:
        title = _clean_text(heading.get_text(" ", strip=True)) or title
    if not title and soup.title:
        title = _clean_text(soup.title.get_text(" ", strip=True))
    title = re.sub(r"\s*[|\-–—]\s*Pantip\s*$", "", title, flags=re.IGNORECASE)
    return _clean_text(title, MAX_FIELD_TEXT)


def _first_post_text(soup: BeautifulSoup) -> str:
    selectors = (
        ".display-post-story",
        ".display-post-story-inner",
        "[data-testid='topic-content']",
        "article",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            for child in node.select("script, style, nav, footer, aside"):
                child.decompose()
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text[:MAX_DEMAND_TEXT]
    description = _meta_value(soup, "description", "og:description")
    if description:
        return description[:MAX_DEMAND_TEXT]
    body = soup.body
    return _clean_text(body.get_text(" ", strip=True) if body else "", MAX_DEMAND_TEXT)


def _parse_timestamp(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, OverflowError):
            parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    thai_match = re.search(r"(\d{1,2})\s+([^\s]+)\s+(\d{4})", candidate)
    if thai_match:
        month = THAI_MONTHS.get(thai_match.group(2))
        if month:
            year = int(thai_match.group(3)) - 543
            try:
                return datetime(year, month, int(thai_match.group(1)), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                return ""
    return ""


def _posted_at(soup: BeautifulSoup) -> str:
    value = _meta_value(
        soup,
        "article:published_time",
        "datePublished",
        "lead:published_at",
        "date",
    )
    if not value:
        time_node = soup.find("time", datetime=True)
        value = str(time_node.get("datetime") or "") if time_node else ""
    return _parse_timestamp(value)


def _first_match(text: str, patterns: tuple[str, ...]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _extract_property_type(text: str) -> str:
    for property_type, pattern in PROPERTY_TYPES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return property_type
    return "unknown"


def _extract_location(text: str, title: str) -> str:
    location_match = re.search(
        r"(?:แถว|ย่าน|โซน|บริเวณ|ใกล้|เขต|อำเภอ|จังหวัด)\s*[:：]?\s*([^,|.;!?]{2,80})",
        text,
        flags=re.IGNORECASE,
    )
    if location_match:
        location = re.split(
            r"\s+(?:งบ(?:ประมาณ)?|ราคา|ค่าเช่า|เดือนละ|ไม่เกิน|พอดี|กำลัง|ต้องการ|อยาก|หา|เน้น|และ)",
            location_match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        location = re.split(r"(?<!\d)\s*[-–—]\s*|\s+(?:ครับ|คับ|ค่ะ|คะ)", location, maxsplit=1)[0]
        return _clean_text(location, MAX_FIELD_TEXT)
    combined = f"{title} {text}"
    known_pattern = (
        r"(คลอง\s*\d+(?:\s*[-–]\s*\d+)?(?:\s*ธัญบุรี)?|"
        r"กรุงเทพ(?:มหานคร)?|กทม\.?|เชียงใหม่|พัทยา|ภูเก็ต|รังสิต|ธัญบุรี|"
        r"ราม\s*2|พระราม\s*2|คลอง\s*หลวง)"
    )
    known = re.search(known_pattern, combined, flags=re.IGNORECASE)
    if known:
        return _clean_text(known.group(1), MAX_FIELD_TEXT)
    known = re.search(
        r"(กรุงเทพ(?:มหานคร)?|กทม\.?|เชียงใหม่|พัทยา|ภูเก็ต|รังสิต|ธัญบุรี|ราม\s*2|พระราม\s*2|คลอง\s*หลวง)",
        f"{title} {text}",
        flags=re.IGNORECASE,
    )
    return _clean_text(known.group(1), MAX_FIELD_TEXT) if known else ""


def _extract_budget(text: str) -> str:
    amount = r"(?:฿\s*)?[\d,.]+(?:\s*[-–]\s*[\d,.]+)?\s*(?:บาท|บ\.?|k|พัน|หมื่น|แสน|ล้าน|ต่อเดือน|/\s*เดือน)"
    patterns = (
        rf"(?:งบ(?:ประมาณ)?|เดือนละ|ค่าเช่า)\s*[:：]?\s*(?:ไม่เกิน\s*)?{amount}",
        rf"ไม่เกิน\s*{amount}",
        r"฿\s*[\d,.]+\s*(?:/\s*เดือน|ต่อเดือน|บาท)?",
        r"[\d,.]+\s*(?:บาท\s*/\s*เดือน|บาทต่อเดือน|บาท|ต่อเดือน|/\s*เดือน)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(0), MAX_FIELD_TEXT)
    return ""


def _extract_timing(text: str) -> str:
    patterns = (
        r"(?:เดือนหน้า|ต้นเดือนหน้า|ปลายเดือนนี้|เร็ว ๆ นี้|เร็วๆนี้|ภายใน\s*\d+\s*(?:วัน|เดือน)|พร้อมเข้าอยู่|ย้ายเข้า[^,|.;!?]{0,40})",
        r"(?:เริ่มเช่า|เริ่มอยู่|เข้าอยู่)\s*(?:ได้ตั้งแต่)?\s*[^,|.;!?]{0,40}",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(0), MAX_FIELD_TEXT)
    return ""


def _demand_signal(text: str) -> tuple[str, re.Match[str] | None]:
    for label, pattern in DEMAND_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return label, match
    return "", None


def _is_stale(posted_at: str, observed_at: str, max_age_days: int | None) -> bool:
    if max_age_days is None or not posted_at:
        return False
    try:
        posted = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return observed - posted > timedelta(days=max(0, max_age_days))


def parse_topic(
    html: str,
    source_url: str,
    *,
    observed_at: str | None = None,
    max_age_days: int | None = 120,
) -> dict[str, Any]:
    """Parse one public Pantip topic into the property-demand contract."""

    canonical_url = canonical_topic_url(source_url)
    observed = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    soup = BeautifulSoup(html or "", "html.parser")
    title = _topic_title(soup)
    text = _first_post_text(soup)
    demand_label, demand_match = _demand_signal(f"{title} {text}".strip())
    supply_match = _first_match(f"{title} {text}", SUPPLY_PATTERNS)
    has_demand = bool(demand_match)
    classification = "not_demand" if supply_match or not has_demand else "demand"
    posted_at = _posted_at(soup)
    stale = _is_stale(posted_at, observed, max_age_days)
    property_text = f"{title} {text}".strip()
    property_type = _extract_property_type(property_text)
    location = _extract_location(property_text, title)
    budget = _extract_budget(property_text)
    timing = _extract_timing(property_text)
    permission = "public_reply_invited" if _first_match(text, PERMISSION_PATTERNS) else "not_stated"
    if classification == "not_demand":
        review_status = "not_demand"
        next_action = "exclude_from_demand_lane"
        confidence = "low"
        exact_text = ""
    elif stale or not posted_at:
        review_status = "needs_more_evidence"
        next_action = "verify_freshness_before_contact"
        confidence = "medium"
        exact_text = text[:MAX_DEMAND_TEXT]
    else:
        review_status = "permission_needed"
        next_action = "human_review_and_request_permission"
        detail_count = sum(bool(value) for value in (property_type != "unknown", location, budget, timing))
        confidence = "high" if detail_count >= 3 else "medium"
        exact_text = text[:MAX_DEMAND_TEXT]

    lead_id = "pantip-" + hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": "property-demand.v1",
        "lead_id": lead_id,
        "source_url": canonical_url,
        "source_platform": "pantip",
        "source_channel": "public_forum",
        "source_access_method": "httpx_public_html",
        "source_visibility": "public",
        "title": title,
        "exact_demand_text": exact_text,
        "demand_signal": demand_label,
        "observed_at": observed,
        "posted_at": posted_at,
        "property_type": property_type,
        "location": location,
        "budget": budget,
        "timing": timing,
        "public_contact_path": canonical_url,
        "contact_permission": permission,
        "confidence": confidence,
        "review_status": review_status,
        "next_action": next_action,
        "retention_until": "",
        "terms_basis_ref": "",
    }
