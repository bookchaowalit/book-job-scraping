#!/usr/bin/env python3
"""Record a human review decision for a property.v1 capture.

This command is deliberately local and review-only.  It updates selected
pending rows, keeps ``outreach_status=not_contacted``, and appends a redacted
audit event containing hashes instead of contact values.  It never opens a
source URL, writes a CRM record, or sends outreach.

Examples::

    python scripts/review_property_leads.py \
        --input data/exported/property_owner_coagent_leads.csv \
        --rows 1,3-4 --decision approved --reviewer-id owner-1 \
        --in-place

    python scripts/review_property_leads.py \
        --input data/exported/property_owner_coagent_leads.csv \
        --list-pending
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_property_capture import validate_capture_rows  # noqa: E402
from scripts.import_property_leads import IMPORT_FIELDNAMES, MAX_INPUT_BYTES  # noqa: E402


REVIEW_DECISIONS = {"approved", "rejected", "needs_more_evidence"}
AUDIT_FIELDNAMES = [
    "reviewed_at",
    "row_number",
    "decision",
    "reviewer_id",
    "prior_decision",
    "source_url_sha256",
    "input_sha256",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _safe_reviewer_id(value: Any) -> str:
    raw = str(value or "")
    if any(ord(char) < 32 for char in raw):
        raise ValueError("reviewer_id_contains_control_character")
    reviewer_id = re.sub(r"\s+", " ", raw).strip()
    if not reviewer_id or len(reviewer_id) > 100:
        raise ValueError("reviewer_id_required_and_bounded")
    return reviewer_id


def _review_timestamp(value: Any = "") -> str:
    stamp = str(value or "").strip() or _utc_now()
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at_must_be_iso8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at_requires_timezone")
    return stamp


def load_capture(path: Path) -> tuple[bytes, list[dict[str, str]]]:
    """Read and validate one property.v1 snapshot without printing payloads."""

    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        reader = csv.DictReader(raw.decode("utf-8-sig").splitlines(keepends=True))
    except UnicodeDecodeError as exc:
        raise ValueError("input must be UTF-8 CSV") from exc
    if reader.fieldnames != IMPORT_FIELDNAMES:
        raise ValueError("headers_do_not_match_property_v1")
    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"malformed_csv_row_{row_number}")
        rows.append({str(key): str(value) for key, value in row.items()})
    if not rows:
        raise ValueError("capture_has_no_rows")
    report = validate_capture_rows(rows)
    if not report["ok"]:
        raise ValueError("capture_validation_failed")
    return raw, rows


def parse_row_numbers(value: str, row_count: int) -> list[int]:
    """Parse one-based data row numbers such as ``1,3-5``."""

    selected: set[int] = set()
    for token in str(value or "").split(","):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", token)
        if not match:
            raise ValueError("rows_must_be_one_based_numbers_or_ranges")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start or end > row_count:
            raise ValueError("rows_out_of_range")
        selected.update(range(start, end + 1))
    if not selected:
        raise ValueError("at_least_one_row_is_required")
    return sorted(selected)


def apply_review(
    rows: Iterable[dict[str, Any]],
    *,
    row_numbers: Iterable[int],
    decision: str,
    reviewer_id: str,
    reviewed_at: str | None = None,
    input_sha256: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, int]]:
    """Apply one decision to pending rows and return redacted audit events."""

    if decision not in REVIEW_DECISIONS:
        raise ValueError("invalid_review_decision")
    reviewer = _safe_reviewer_id(reviewer_id)
    stamp = _review_timestamp(reviewed_at)
    materialised = [dict(row) for row in rows]
    selected = sorted({int(number) for number in row_numbers})
    if not selected:
        raise ValueError("at_least_one_row_is_required")
    if any(number < 1 or number > len(materialised) for number in selected):
        raise ValueError("rows_out_of_range")
    for number in selected:
        row = materialised[number - 1]
        if str(row.get("review_decision") or "").strip() != "pending":
            raise ValueError(f"row_{number}_already_reviewed")
        if str(row.get("outreach_status") or "not_contacted").strip() != "not_contacted":
            raise ValueError(f"row_{number}_outreach_state_invalid")

    audit: list[dict[str, str]] = []
    for number in selected:
        row = materialised[number - 1]
        prior_decision = str(row.get("review_decision") or "pending").strip()
        row["review_decision"] = decision
        row["reviewed_at"] = stamp
        row["reviewer_id"] = reviewer
        row["outreach_status"] = "not_contacted"
        source_hash = hashlib.sha256(str(row.get("url") or "").encode("utf-8")).hexdigest()
        audit.append(
            {
                "reviewed_at": stamp,
                "row_number": str(number),
                "decision": decision,
                "reviewer_id": reviewer,
                "prior_decision": prior_decision,
                "source_url_sha256": source_hash,
                "input_sha256": str(input_sha256 or ""),
            }
        )

    pending_remaining = sum(
        str(row.get("review_decision") or "").strip() == "pending"
        for row in materialised
    )
    stats = {
        "selected": len(selected),
        "updated": len(selected),
        "pending_remaining": pending_remaining,
    }
    return materialised, audit, stats


def _atomic_write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        temp_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temp_path, path)


def write_review_outputs(
    output_path: Path,
    rows: list[dict[str, Any]],
    audit: list[dict[str, str]],
) -> dict[str, str]:
    """Write the reviewed snapshot and append redacted audit events."""

    _atomic_write_csv(output_path, rows, IMPORT_FIELDNAMES)
    audit_path = output_path.parent / "property_owner_coagent_review_history.csv"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    exists = audit_path.exists()
    with audit_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDNAMES)
        if not exists:
            writer.writeheader()
        for event in audit:
            writer.writerow({field: event.get(field, "") for field in AUDIT_FIELDNAMES})
    return {"snapshot": str(output_path), "audit": str(audit_path)}


def _print_pending(rows: list[dict[str, str]]) -> None:
    counts = Counter(str(row.get("review_decision") or "unknown") for row in rows)
    pending = [str(index) for index, row in enumerate(rows, start=1) if row.get("review_decision") == "pending"]
    print(
        "property_review: "
        f"rows={len(rows)} pending={counts.get('pending', 0)} "
        f"approved={counts.get('approved', 0)} rejected={counts.get('rejected', 0)} "
        f"needs_more_evidence={counts.get('needs_more_evidence', 0)}"
    )
    print(f"pending_rows={','.join(pending) if pending else '(none)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Reviewed CSV path; defaults to a sibling *_reviewed.csv")
    parser.add_argument("--in-place", action="store_true", help="Replace the input CSV atomically")
    parser.add_argument("--reviewer-id", help="Short human reviewer identifier")
    parser.add_argument("--decision", choices=sorted(REVIEW_DECISIONS))
    parser.add_argument("--rows", help="One-based data rows, for example 1,3-5")
    parser.add_argument("--all-pending", action="store_true", help="Apply the decision to every pending row")
    parser.add_argument("--reviewed-at", default="", help="ISO-8601 timestamp with timezone (optional)")
    parser.add_argument("--list-pending", action="store_true", help="Print redacted row status counts")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing files")
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"input file does not exist: {args.input}")
    if args.list_pending and any((args.decision, args.rows, args.all_pending, args.reviewer_id, args.output, args.in_place)):
        parser.error("--list-pending cannot be combined with review options")
    if not args.list_pending:
        if not args.decision or not args.reviewer_id:
            parser.error("--reviewer-id and --decision are required for a review")
        if args.rows and args.all_pending:
            parser.error("choose --rows or --all-pending")
        if not args.rows and not args.all_pending:
            parser.error("choose --rows or --all-pending")
        if args.output and args.in_place:
            parser.error("choose --output or --in-place")

    try:
        raw, rows = load_capture(args.input)
        if args.list_pending:
            _print_pending(rows)
            return 0
        selected = (
            [index for index, row in enumerate(rows, start=1) if row.get("review_decision") == "pending"]
            if args.all_pending
            else parse_row_numbers(args.rows or "", len(rows))
        )
        if not selected:
            raise ValueError("no_pending_rows_selected")
        reviewed, audit, stats = apply_review(
            rows,
            row_numbers=selected,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewed_at=args.reviewed_at,
            input_sha256=hashlib.sha256(raw).hexdigest(),
        )
        print(
            "property_review: "
            f"selected={stats['selected']} updated={stats['updated']} "
            f"pending_remaining={stats['pending_remaining']}"
        )
        if args.dry_run:
            return 0
        output_path = args.input if args.in_place else args.output or args.input.with_name(
            f"{args.input.stem}_reviewed{args.input.suffix}"
        )
        paths = write_review_outputs(output_path, reviewed, audit)
        print(f"snapshot={paths['snapshot']}")
        print(f"audit={paths['audit']}")
        return 0
    except (OSError, ValueError, UnicodeError, csv.Error) as exc:
        print(f"property_review: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
