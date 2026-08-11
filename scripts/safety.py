#!/usr/bin/env python3
"""Safety gates and application status semantics for job pipeline scripts.

Live network send/apply is DISABLED by default. Enabling requires:
  1. Explicit CLI flag (--send or --apply)
  2. Environment unlock: BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND

Status rules:
  prepared / draft  — materials ready; NOT submitted
  submitted         — actually sent or confirmed submitted
  Legacy aliases are mapped for reads but should not be written as "applied"
  when only a draft was created.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

# ── Live send unlock ──────────────────────────────────────────────────────────
SEND_UNLOCK_ENV = "BOOK_JOB_SEND_UNLOCK"
SEND_UNLOCK_VALUE = "I_UNDERSTAND_LIVE_SEND"

# Master kill switch: when true (default), live send/apply always blocked even
# if unlock env is set. Set BOOK_JOB_LIVE_SEND_ENABLED=1 to allow unlock path.
LIVE_SEND_ENABLED_ENV = "BOOK_JOB_LIVE_SEND_ENABLED"


def is_live_send_master_enabled() -> bool:
    """Hard switch — default off until P0 is complete and explicitly enabled."""
    return os.environ.get(LIVE_SEND_ENABLED_ENV, "").strip() in {"1", "true", "yes"}


def is_live_send_unlocked() -> bool:
    return (
        is_live_send_master_enabled()
        and os.environ.get(SEND_UNLOCK_ENV, "").strip() == SEND_UNLOCK_VALUE
    )


def require_live_send(action: str = "send") -> None:
    """Exit non-zero if live network send/apply is not fully authorized."""
    if is_live_send_unlocked():
        return

    reasons = []
    if not is_live_send_master_enabled():
        reasons.append(
            f"  • master switch off — set {LIVE_SEND_ENABLED_ENV}=1 only when ready"
        )
    if os.environ.get(SEND_UNLOCK_ENV, "").strip() != SEND_UNLOCK_VALUE:
        reasons.append(
            f"  • unlock missing — set {SEND_UNLOCK_ENV}={SEND_UNLOCK_VALUE}"
        )
    reasons.append("  • pass the explicit CLI flag (--send or --apply)")

    print(
        f"\nBLOCKED: live {action} is disabled (safety gate).\n"
        + "\n".join(reasons)
        + "\n\nDefault mode is dry-run / prepare-only. Do not enable until explicitly approved.\n",
        file=sys.stderr,
    )
    raise SystemExit(2)


# ── Application status vocabulary ─────────────────────────────────────────────
STATUS_PREPARED = "prepared"
STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# Written by draft generators (auto_apply, tailor, etc.)
PREPARE_STATUSES = frozenset({STATUS_PREPARED, STATUS_DRAFT})

# Actually sent / confirmed submitted
SUBMITTED_STATUSES = frozenset({STATUS_SUBMITTED, "applied", "sent"})

# Legacy values that mean "materials ready" not "submitted"
LEGACY_PREPARED_ALIASES = frozenset({"auto_applied", "ready", "prepared_draft"})

# Anything that should block re-prepare as already handled for apply attempts
TERMINAL_OR_IN_FLIGHT = PREPARE_STATUSES | SUBMITTED_STATUSES | LEGACY_PREPARED_ALIASES | frozenset(
    {"interview", "offer", "rejected", "withdrawn", "no-response", "screening"}
)


def normalize_status(status: str | None) -> str:
    """Map legacy status strings to the current vocabulary."""
    if not status:
        return ""
    s = status.strip().lower()
    if s in LEGACY_PREPARED_ALIASES or s == "auto_applied":
        return STATUS_PREPARED
    if s in {"applied", "sent"}:
        return STATUS_SUBMITTED
    return s


def is_prepared(status: str | None) -> bool:
    return normalize_status(status) in PREPARE_STATUSES


def is_submitted(status: str | None) -> bool:
    return normalize_status(status) in SUBMITTED_STATUSES


def is_already_handled(status: str | None) -> bool:
    """True if job should not be re-prepared/re-applied by automation."""
    return normalize_status(status) in {
        normalize_status(x) for x in TERMINAL_OR_IN_FLIGHT
    } or (status or "").strip().lower() in TERMINAL_OR_IN_FLIGHT


def assert_no_network_send_without_flag(
    *,
    want_send: bool,
    action: str = "send",
) -> None:
    """Call at CLI entry: if user asked to send, enforce unlock; else continue dry-run."""
    if want_send:
        require_live_send(action)


def missing_dependency_message(package: str) -> str:
    return (
        f"Missing dependency '{package}'. "
        "Use the project venv and install requirements:\n"
        "  python3 -m venv .venv && . .venv/bin/activate\n"
        "  pip install -r requirements.txt\n"
        "Scripts must not pip-install packages at runtime."
    )


def require_import(module_name: str, package_name: str | None = None):
    """Import a module or exit with a clear install hint (no auto-pip)."""
    pkg = package_name or module_name
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise SystemExit(missing_dependency_message(pkg)) from exc
