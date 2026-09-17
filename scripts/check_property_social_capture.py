#!/usr/bin/env python3
"""Validate a persisted public property-social capture before review or ingest.

The validator reports row numbers and stable error codes only. It never prints
contact values, descriptions, or other captured payload fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from property.lead_extraction import SOCIAL_HOSTS, _clean_url  # noqa: E402
from property.social_leads import SOCIAL_FIELDNAMES  # noqa: E402


ALLOWED_PLATFORMS = set(SOCIAL_HOSTS.values())
ROLE_VALUES = {"owner", "agent", "owner_or_agent", "unknown"}
CO_AGENT_VALUES = {"yes", "no", "unknown"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
LEAD_REVIEW_VALUES = {"co_agent_candidate", "needs_human_review", "unqualified"}
REVIEW_DECISIONS = {"pending", "approved", "rejected", "needs_more_evidence"}
OUTREACH_STATUSES = {"not_contacted", "approved_to_contact", "contacted", "opt_out"}
REQUIRED_ROW_FIELDS = {
    "captured_at",
    "scraped_at",
    "title",
    "type",
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
    """Return a redacted, stable validation error."""

    return {"row": row, "code": code}


def _timestamp_is_valid(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _truthy_csv(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def validate_capture_rows(
    rows: Iterable[dict[str, Any]],
    *,
    min_rows: int = 1,
    max_rows: int = 100,
    require_governance: bool = False,
) -> dict[str, Any]:
    """Validate social capture rows without returning captured values."""

    materialised = list(rows)
    errors: list[dict[str, Any]] = []
    if len(materialised) < max(0, int(min_rows)):
        errors.append(_error(0, "too_few_rows"))
    if len(materialised) > max(0, int(max_rows)):
        errors.append(_error(0, "too_many_rows"))

    seen_urls: set[str] = set()
    for row_number, row in enumerate(materialised, start=2):
        missing = REQUIRED_ROW_FIELDS - set(row)
        for field in sorted(missing):
            errors.append(_error(row_number, f"missing_{field}"))
        if missing:
            continue

        url = str(row.get("url") or "").strip()
        canonical_url = _clean_url(url)
        if (
            not canonical_url
            or canonical_url != url
            or urlsplit(url).scheme.lower() != "https"
        ):
            errors.append(_error(row_number, "invalid_source_url"))
        elif url in seen_urls:
            errors.append(_error(row_number, "duplicate_source_url"))
        else:
            seen_urls.add(url)

        if str(row.get("source_platform") or "").strip().lower() not in ALLOWED_PLATFORMS:
            errors.append(_error(row_number, "invalid_source_platform"))
        if str(row.get("source_channel") or "").strip() != "social_search":
            errors.append(_error(row_number, "invalid_source_channel"))
        if str(row.get("type") or "").strip() != "social_property_lead":
            errors.append(_error(row_number, "invalid_type"))
        if str(row.get("contact_source_url") or "").strip() != url:
            errors.append(_error(row_number, "source_url_mismatch"))
        if not _truthy_csv(row.get("contact_public")):
            errors.append(_error(row_number, "not_public_source"))

        enum_checks = (
            ("contact_role", ROLE_VALUES),
            ("co_agent_status", CO_AGENT_VALUES),
            ("contact_confidence", CONFIDENCE_VALUES),
            ("lead_review_status", LEAD_REVIEW_VALUES),
            ("review_decision", REVIEW_DECISIONS),
            ("outreach_status", OUTREACH_STATUSES),
        )
        for field, allowed in enum_checks:
            if str(row.get(field) or "").strip() not in allowed:
                errors.append(_error(row_number, f"invalid_{field}"))

        for field in ("captured_at", "scraped_at"):
            if not _timestamp_is_valid(str(row.get(field) or "")):
                errors.append(_error(row_number, f"invalid_{field}"))

        decision = str(row.get("review_decision") or "").strip()
        if decision != "pending":
            if not str(row.get("reviewer_id") or "").strip():
                errors.append(_error(row_number, "reviewer_required"))
            if not _timestamp_is_valid(str(row.get("reviewed_at") or "")):
                errors.append(_error(row_number, "reviewed_at_required"))

        outreach = str(row.get("outreach_status") or "").strip()
        if outreach in {"approved_to_contact", "contacted"} and decision != "approved":
            errors.append(_error(row_number, "outreach_not_approved"))

        if require_governance:
            if not _timestamp_is_valid(str(row.get("retention_until") or "")):
                errors.append(_error(row_number, "retention_until_required"))
            if not str(row.get("terms_basis_ref") or "").strip():
                errors.append(_error(row_number, "terms_basis_ref_required"))

    return {
        "ok": not errors,
        "row_count": len(materialised),
        "errors": errors,
    }


def validate_capture_file(
    path: Path,
    *,
    min_rows: int = 1,
    max_rows: int = 100,
    require_governance: bool = False,
) -> dict[str, Any]:
    """Validate CSV headers and rows while keeping payload values private."""

    if not path.exists():
        return {"ok": False, "row_count": 0, "errors": [{"row": 0, "code": "missing_file"}]}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            errors: list[dict[str, Any]] = []
            if len(headers) != len(set(headers)):
                errors.append(_error(1, "duplicate_header"))
            for field in sorted(set(SOCIAL_FIELDNAMES) - set(headers)):
                errors.append(_error(1, f"missing_header_{field}"))
            report = validate_capture_rows(
                reader,
                min_rows=min_rows,
                max_rows=max_rows,
                require_governance=require_governance,
            )
    except (OSError, UnicodeError, csv.Error):
        return {"ok": False, "row_count": 0, "errors": [{"row": 0, "code": "unreadable_file"}]}

    report["errors"] = errors + report["errors"]
    report["ok"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument(
        "--require-governance",
        action="store_true",
        help="Require retention_until and terms_basis_ref on every row",
    )
    parser.add_argument("--json", action="store_true", help="Print redacted JSON report")
    args = parser.parse_args()
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
        print(f"property_social_capture: {status} ({report['row_count']} rows, {len(report['errors'])} errors)")
        for error in report["errors"]:
            print(f"  row {error['row']}: {error['code']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
