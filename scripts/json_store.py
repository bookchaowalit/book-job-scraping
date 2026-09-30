"""Read-modify-write helper for the JSON run logs under ``data/``.

The log writers used to do ``try: json.loads(...) except Exception: log = {}``
and then write ``log`` back, so a single failed read (a half-written file, a
bad byte, a concurrent writer) replaced the whole saved history with one new
entry. ``load_json_for_update`` moves an unreadable file aside first, so the
following write can never destroy it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def load_json_for_update(path: Path, default: Callable[[], Any], expected_type: type = dict) -> Any:
    """Return the parsed JSON at ``path``, or ``default()`` when it is absent.

    A file that exists but cannot be read, parsed, or is not ``expected_type``
    is renamed to ``<name>.corrupt-<UTC stamp>`` (kept for recovery) before the
    default is returned.
    """
    path = Path(path)
    if not path.exists():
        return default()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, expected_type):
            return data
    except (OSError, ValueError):
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    path.replace(backup)
    print(f"  WARNING: {path.name} was unreadable; kept it as {backup.name}")
    return default()
