"""Extract contact signals from publicly published property text.

This module deliberately works on text already obtained from an approved public
source.  It never logs in, bypasses an access control, or fetches a social
profile.  The returned provenance and confidence fields make it possible to
review a lead before any human outreach.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SOCIAL_HOSTS = {
    "facebook.com": "facebook",
    "fb.me": "facebook",
    "m.me": "facebook",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "line.me": "line",
    "lin.ee": "line",
}

CONTACT_FIELDS = [
    "contact_name",
    "contact_role",
    "co_agent_status",
    "contact_phone",
    "contact_email",
    "contact_line",
    "contact_facebook",
    "contact_instagram",
    "contact_tiktok",
    "contact_social_urls",
    "contact_source_url",
    "contact_evidence",
    "contact_confidence",
    "contact_public",
    "lead_review_status",
    "review_decision",
    "reviewed_at",
    "reviewer_id",
    "outreach_status",
    "retention_until",
    "terms_basis_ref",
]


_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+66|0)(?:[\s().-]*\d){8,10}(?!\d)", re.IGNORECASE
)
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
_SOCIAL_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:facebook\.com|fb\.me|m\.me|instagram\.com|"
    r"tiktok\.com|line\.me|lin\.ee)/[^\s<>\"']+",
    re.IGNORECASE,
)

_OWNER_TERMS = (
    r"เจ้าของ(?:ห้อง|บ้าน|ทรัพย์)?",
    r"ขายเอง",
    r"ปล่อยเอง",
    r"direct\s+owner",
    r"\bowner\b",
)
_AGENT_TERMS = (
    r"นายหน้า",
    r"เอเจ(?:น(?:ต์|ท์)?|้น)",
    r"โบรกเกอร์",
    r"\bagent\b",
    r"\bbroker\b",
    r"\bagency\b",
)
_CO_AGENT_YES = (
    r"รับ\s*(?:co\s*[- ]?agent|co\s*[- ]?broker)",
    r"รับ\s*(?:เอเจ(?:น(?:ต์|ท์)?|้น)|นายหน้า)",
    r"ยินดีรับ\s*(?:เอเจ(?:น(?:ต์|ท์)?|้น)|นายหน้า)",
    r"(?:co\s*[- ]?agent|co\s*[- ]?broker)\s*(?:welcome|ยินดี)",
    r"(?:ร่วมงาน|แชร์คอม|แบ่งค่าคอม|แบ่งคอม)",
)
_CO_AGENT_NO = (
    r"ไม่รับ\s*(?:co\s*[- ]?agent|co\s*[- ]?broker|เอเจ(?:น(?:ต์|ท์)?|้น)|นายหน้า)",
    r"\bno\s*co\s*[- ]?(?:agent|broker)\b",
    r"\bco\s*[- ]?(?:agent|broker)\s*not\s*accepted\b",
)


def _clean_url(value: str) -> str:
    value = (value or "").strip().rstrip(".,;:)]}>")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    platform = SOCIAL_HOSTS.get(host)
    if not platform:
        return ""
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _public_source_url(value: str) -> str:
    """Return only an explicit HTTP(S) source URL for provenance."""

    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate


def _normalise_phone(value: str) -> str:
    compact = re.sub(r"\D", "", value or "")
    if compact.startswith("66") and not compact.startswith("0"):
        compact = "0" + compact[2:]
    if not compact.startswith("0") or len(compact) not in {9, 10}:
        return ""
    return compact


def _first_match(text: str, patterns: tuple[str, ...]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _contact_name(text: str) -> str:
    match = re.search(
        r"(?:contact|ติดต่อ|ผู้ติดต่อ|listing\s+agent|agent|นายหน้า|เจ้าของ)"
        r"\s*[:：=-]\s*([^\n|]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    value = re.split(
        r"\s+(?:โทร|tel(?:ephone)?|phone|line|ไลน์|email|อีเมล)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"https?://\S+", "", value).strip(" -,:;")
    return value[:100]


def _evidence(text: str, matches: list[re.Match[str] | None]) -> str:
    snippets: list[str] = []
    for match in matches:
        if not match:
            continue
        start = max(0, match.start() - 45)
        end = min(len(text), match.end() + 75)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip(" -|,;")
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    return " | ".join(snippets)[:320]


def extract_contact_details(text: str, source_url: str = "") -> dict[str, Any]:
    """Return public contact and cooperation signals found in *text*.

    Values are intentionally limited to explicit text and URLs from the source
    page or search result.  An absent signal is represented as ``unknown`` or
    an empty value, never inferred from a listing title alone.
    """

    text = str(text or "")
    # The word "agent" in "co-agent" describes cooperation, not the
    # publisher's role.  Mask that phrase before classifying the contact.
    # Contact addresses and URLs can contain words such as ``agent`` or
    # ``owner`` in a username/slug.  They are contact paths, not evidence of
    # the publisher's role, so remove them before applying role terms.
    # Keep replacement lengths aligned with the original text so evidence
    # snippets can still use match offsets safely.
    role_text = re.sub(_EMAIL_RE, lambda match: " " * len(match.group(0)), text)
    role_text = re.sub(
        r"https?://\S+",
        lambda match: " " * len(match.group(0)),
        role_text,
        flags=re.IGNORECASE,
    )
    role_text = re.sub(
        r"co\s*[- ]?agent|co\s*[- ]?broker",
        lambda match: " " * len(match.group(0)),
        role_text,
        flags=re.IGNORECASE,
    )
    owner_match = _first_match(role_text, _OWNER_TERMS)
    agent_match = _first_match(role_text, _AGENT_TERMS)
    if owner_match and not agent_match:
        role = "owner"
    elif agent_match and not owner_match:
        role = "agent"
    elif owner_match and agent_match:
        role = "owner_or_agent"
    else:
        role = "unknown"

    no_co_match = _first_match(text, _CO_AGENT_NO)
    yes_co_match = _first_match(text, _CO_AGENT_YES)
    if no_co_match:
        co_agent_status = "no"
    elif yes_co_match:
        co_agent_status = "yes"
    else:
        co_agent_status = "unknown"

    phone = ""
    for match in _PHONE_RE.finditer(text):
        phone = _normalise_phone(match.group(0))
        if phone:
            break
    email_match = _EMAIL_RE.search(text)
    email = email_match.group(0).lower() if email_match else ""

    social: dict[str, str] = {}
    for raw_url in _SOCIAL_URL_RE.findall(text):
        url = _clean_url(raw_url)
        if not url:
            continue
        host = (urlsplit(url).hostname or "").removeprefix("www.").lower()
        platform = SOCIAL_HOSTS.get(host)
        if platform and platform not in social:
            social[platform] = url

    line_match = re.search(
        r"(?:line|ไลน์)\s*(?:id|ไอดี)?\s*[:：=@]\s*"
        r"(@?[A-Za-z0-9._-]{3,64})",
        text,
        flags=re.IGNORECASE,
    )
    line_id = line_match.group(1) if line_match else social.get("line", "")

    contact_name = _contact_name(text)
    has_contact = bool(contact_name or phone or email or line_id or social)
    has_signal = bool(owner_match or agent_match or no_co_match or yes_co_match)
    if has_contact and has_signal:
        confidence = "high"
    elif has_contact or has_signal:
        confidence = "medium"
    else:
        confidence = "low"
    if has_contact and co_agent_status == "yes":
        review_status = "co_agent_candidate"
    elif has_contact or has_signal:
        review_status = "needs_human_review"
    else:
        review_status = "unqualified"

    public_source_url = _public_source_url(source_url)
    details: dict[str, Any] = {field: "" for field in CONTACT_FIELDS}
    details.update(
        {
            "contact_name": contact_name,
            "contact_role": role,
            "co_agent_status": co_agent_status,
            "contact_phone": phone,
            "contact_email": email,
            "contact_line": line_id,
            "contact_facebook": social.get("facebook", ""),
            "contact_instagram": social.get("instagram", ""),
            "contact_tiktok": social.get("tiktok", ""),
            "contact_social_urls": ";".join(social.values()),
            "contact_source_url": _clean_url(source_url) or public_source_url,
            "contact_evidence": _evidence(
                text, [owner_match, agent_match, no_co_match, yes_co_match]
            ),
            "contact_confidence": confidence,
            "contact_public": bool(public_source_url),
            "lead_review_status": review_status,
            "review_decision": "pending",
            "reviewed_at": "",
            "reviewer_id": "",
            "outreach_status": "not_contacted",
            "retention_until": "",
            "terms_basis_ref": "",
        }
    )
    return details


def enrich_listing(
    listing: dict[str, Any],
    text: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Copy a listing and attach reviewable public contact fields."""

    enriched = dict(listing)
    source = str(source_url or listing.get("url") or "")
    if text is None:
        text = " ".join(
            str(listing.get(field) or "")
            for field in (
                "title",
                "description",
                "publisher",
                "contact",
                "contact_text",
            )
        )
    enriched.update(extract_contact_details(text, source))
    return enriched
