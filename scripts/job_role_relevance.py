#!/usr/bin/env python3
"""Shared role relevance helpers for contract-first job matching."""

from __future__ import annotations

import re
from typing import Any


TECH_ROLE_PATTERN = re.compile(
    r"\b(?:software|web|full[\s-]?stack|front[\s-]?end|back[\s-]?end|platform|cloud|devops|sre|data (?:engineer|scientist|analyst|architect)|machine learning|ml|ai|automation|integration|api|python|react|next\.js|node\.js)\b"
    r"|\b(?:developer|engineer|architect|programmer|ebpf)\b"
    r"|โปรแกรมเมอร์|นักพัฒนา|วิศวกร|ซอฟต์แวร์|เว็บไซต์",
    re.IGNORECASE,
)

NON_TARGET_ROLE_PATTERN = re.compile(
    r"\b(?:writer|copywriter|editor|reviewer|office assistant|optometrist|physician|nurse|teacher|recruiter|talent acquisition)\b",
    re.IGNORECASE,
)

COMMERCIAL_ROLE_PATTERN = re.compile(
    r"\b(?:account executive|sales development|business development|partnerships?|solutions engineer|sales engineer|implementation consultant|implementation specialist|customer success|technical account manager|onboarding specialist)\b",
    re.IGNORECASE,
)

TECH_BUSINESS_CONTEXT_PATTERN = re.compile(
    r"\b(?:saas|software|technology|tech|api|cloud|fintech|travel[\s-]?tech|e-?sim|logistics|hospitality tech|ai|automation|developer tools?)\b",
    re.IGNORECASE,
)


def contains_term(text: str, term: str) -> bool:
    """Match a skill as a token/phrase, not inside unrelated words."""
    clean_term = str(term or "").strip().lower()
    if not clean_term:
        return False
    pattern = re.escape(clean_term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![\w]){pattern}(?![\w])", str(text or "").lower()) is not None


def evidence_tags(job: dict[str, Any]) -> str:
    """Remove the collector search phrase when a source echoed it into tags."""
    tags = str(job.get("tags") or "")
    keyword = str(job.get("keyword") or "").strip()
    if keyword:
        tags = re.sub(re.escape(keyword), " ", tags, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", tags).strip(" ,")


def is_relevant_role(job: dict[str, Any]) -> bool:
    title = str(job.get("title") or job.get("job_title") or "").strip()
    if not title:
        return False
    if NON_TARGET_ROLE_PATTERN.search(title):
        return False
    if TECH_ROLE_PATTERN.search(title):
        return True
    # Contribution programs often title the role simply "Contributor" or
    # "Fellow".  Keep the title gate, but allow an explicit open-source /
    # fellowship / apprenticeship / volunteer signal when the surrounding
    # evidence names a technical role.  Search-keyword echoes are removed by
    # evidence_tags before this check.
    context = " ".join(
        [
            str(job.get("title") or ""),
            str(job.get("company") or ""),
            evidence_tags(job),
            str(job.get("description") or ""),
            str(job.get("notes") or ""),
            str(job.get("category") or ""),
        ]
    )
    bridge_signal = re.search(
        r"\bopen[\s-]?source\b|\bfellowship\b|\bapprenticeship\b|\bvolunteer(?:ing)?\b|\bintern(?:ship)?\b",
        context,
        re.IGNORECASE,
    )
    if bridge_signal and TECH_ROLE_PATTERN.search(context):
        return True
    if not COMMERCIAL_ROLE_PATTERN.search(title):
        return False
    return TECH_BUSINESS_CONTEXT_PATTERN.search(context) is not None
