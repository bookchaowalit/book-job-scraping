#!/usr/bin/env python3
"""Validate a property.v1 owner/co-agent capture without printing payloads."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from property.lead_extraction import SOCIAL_HOSTS  # noqa: E402
from scripts.import_property_leads import IMPORT_FIELDNAMES, canonical_source_url  # noqa: E402


ROLE_VALUES = {"owner", "agent", "owner_or_agent", "unknown"}
CO_AGENT_VALUES = {"yes", "no", "unknown"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
LEAD_REVIEW_VALUES = {"co_agent_candidate", "needs_human_review", "unqualified"}
REVIEW_DECISIONS = {"pending", "approved", "rejected", "needs_more_evidence"}
OUTREACH_STATUSES = {"not_contacted", "approved_to_contact", "contacted", "opt_out"}
SOCIAL_PLATFORMS = set(SOCIAL_HOSTS.values())
REQUIRED_FIELDS = {
    "scraped_at",
    "captured_at",
    "title",
    "type",
    "listing_type",
    "url",
    "source_channel",
    "source_platform",
    "contact_source_url",
    "contact_role",
    "co_agent_status",
    "contact_confidence",
    "contact_public",
    "lead_review_status",
    "review_decision",
    "outreach_status",
}


def _error(row: int, code: str) -> dict[str, Any]:
    return {"row": row, "code": code}


def _timestamp(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes"}


def validate_capture_rows(
    rows: Iterable[dict[str, Any]],
    *,
    min_rows: int = 1,
    max_rows: int = 500,
    require_governance: bool = False,
) -> dict[str, Any]:
    """Return stable, redacted validation codes for property.v1 rows."""

    materialised = list(rows)
    errors: list[dict[str, Any]] = []
    if len(materialised) < max(0, int(min_rows)):
        errors.append(_error(0, "too_few_rows"))
    if len(materialised) > max(0, int(max_rows)):
        errors.append(_error(0, "too_many_rows"))

    seen_urls: set[str] = set()
    for row_number, row in enumerate(materialised, start=2):
        missing = REQUIRED_FIELDS - set(row)
        for field in sorted(missing):
            errors.append(_error(row_number, f"missing_{field}"))
        if missing:
            continue

        url = str(row.get("url") or "").strip()
        try:
            canonical, platform = canonical_source_url(url)
        except ValueError:
            canonical, platform = "", ""
        if not canonical or canonical != url:
            errors.append(_error(row_number, "invalid_source_url"))
        elif url in seen_urls:
            errors.append(_error(row_number, "duplicate_source_url"))
        else:
            seen_urls.add(url)

        if str(row.get("source_platform") or "").strip() != platform:
            errors.append(_error(row_number, "source_platform_mismatch"))
        expected_channel = "social_search" if platform in SOCIAL_PLATFORMS else "listing"
        if str(row.get("source_channel") or "").strip() != expected_channel:
            errors.append(_error(row_number, "source_channel_mismatch"))
        if str(row.get("contact_source_url") or "").strip() != url:
            errors.append(_error(row_number, "source_url_mismatch"))
        if not _truthy(row.get("contact_public")):
            errors.append(_error(row_number, "not_public_source"))

        for field, allowed in (
            ("contact_role", ROLE_VALUES),
            ("co_agent_status", CO_AGENT_VALUES),
            ("contact_confidence", CONFIDENCE_VALUES),
            ("lead_review_status", LEAD_REVIEW_VALUES),
            ("review_decision", REVIEW_DECISIONS),
            ("outreach_status", OUTREACH_STATUSES),
        ):
            if str(row.get(field) or "").strip() not in allowed:
                errors.append(_error(row_number, f"invalid_{field}"))
        for field in ("scraped_at", "captured_at"):
            if not _timestamp(row.get(field)):
                errors.append(_error(row_number, f"invalid_{field}"))

        decision = str(row.get("review_decision") or "").strip()
        if decision != "pending":
            if not str(row.get("reviewer_id") or "").strip():
                errors.append(_error(row_number, "reviewer_required"))
            if not _timestamp(row.get("reviewed_at")):
                errors.append(_error(row_number, "reviewed_at_required"))
        outreach = str(row.get("outreach_status") or "").strip()
        if outreach in {"approved_to_contact", "contacted"} and decision != "approved":
            errors.append(_error(row_number, "outreach_not_approved"))
        if require_governance:
            if not _timestamp(row.get("retention_until")):
                errors.append(_error(row_number, "retention_until_required"))
            if not str(row.get("terms_basis_ref") or "").strip():
                errors.append(_error(row_number, "terms_basis_ref_required"))

    return {"ok": not errors, "row_count": len(materialised), "errors": errors}


def validate_capture_file(
    path: Path,
    *,
    min_rows: int = 1,
    max_rows: int = 500,
    require_governance: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "row_count": 0, "errors": [_error(0, "missing_file")]}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            errors: list[dict[str, Any]] = []
            if headers != IMPORT_FIELDNAMES:
                errors.append(_error(1, "headers_do_not_match_property_v1"))
            report = validate_capture_rows(
                reader,
                min_rows=min_rows,
                max_rows=max_rows,
                require_governance=require_governance,
            )
    except (OSError, UnicodeError, csv.Error):
        return {"ok": False, "row_count": 0, "errors": [_error(0, "unreadable_file")]}
    report["errors"] = errors + report["errors"]
    report["ok"] = not report["errors"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--require-governance", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print a redacted JSON report")
    args = parser.parse_args(argv)
    report = validate_capture_file(
        args.path,
        min_rows=args.min_rows,
        max_rows=args.max_rows,
        require_governance=args.require_governance,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"property_capture: {status} ({report['row_count']} rows, {len(report['errors'])} errors)")
        for error in report["errors"]:
            print(f"  row {error['row']}: {error['code']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
