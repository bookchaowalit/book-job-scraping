"""Crash-safe file writes for the JSON stores under ``data/``.

Writing ``open(path, "w")`` truncates the target before the new content is
written, so a scheduled tick killed mid-write (Task Scheduler timeout,
``taskkill /T``, power loss) leaves an empty or half-written store. These
helpers write to a temporary file in the same directory, flush + fsync it,
then ``os.replace`` it over the target, which is atomic on both POSIX and
Windows (same volume). Readers see either the old file or the new one.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union


def write_text_atomic(path: Union[str, Path], text: str, encoding: str = "utf-8") -> None:
    """Atomically replace ``path`` with ``text``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_json_atomic(path: Union[str, Path], data: Any, **dump_kwargs: Any) -> None:
    """Serialize ``data`` fully in memory, then atomically replace ``path``.

    Serializing before touching the disk means a ``TypeError`` from an
    unserializable value also leaves the previous file intact.
    """
    write_text_atomic(path, json.dumps(data, **dump_kwargs))
