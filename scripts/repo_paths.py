#!/usr/bin/env python3
"""Canonical paths for the book-job-scraping repository.

All scripts should resolve data/scripts relative to this repo root, not the
legacy monorepo layout (domains/book-dev/book-scraping).

Override with env if needed:
  BOOK_JOB_SCRAPING_ROOT  — absolute path to this repo
  PIPELINE_DATA_DIR       — absolute path to runtime data dir
"""

from __future__ import annotations

import os
from pathlib import Path

# This file lives at: <repo>/scripts/repo_paths.py
_SCRIPTS_DIR = Path(__file__).resolve().parent
_DEFAULT_ROOT = _SCRIPTS_DIR.parent


def get_repo_root() -> Path:
    override = os.environ.get("BOOK_JOB_SCRAPING_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_ROOT


REPO_ROOT = get_repo_root()
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR = Path(
    os.environ.get("PIPELINE_DATA_DIR", str(REPO_ROOT / "data"))
).expanduser().resolve()
CONFIG_DIR = REPO_ROOT / "config"


def ensure_data_dirs(*subdirs: str) -> Path:
    """Create data root (and optional subdirs) and return data root."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in subdirs:
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def load_env() -> None:
    """Load .env from repo root, then optional parent Solo Empire .env."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(REPO_ROOT / ".env")
    # Nested under solo-empire/.../book-job-scraping — walk up a few levels.
    for parent in list(REPO_ROOT.parents)[:8]:
        candidate = parent / ".env"
        if candidate.exists() and candidate != REPO_ROOT / ".env":
            # Parent may be infra/ or solo-empire root.
            load_dotenv(candidate, override=False)
            break
