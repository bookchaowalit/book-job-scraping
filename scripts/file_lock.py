#!/usr/bin/env python3
"""Cross-platform exclusive file lock (fcntl on POSIX, msvcrt on Windows)."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class LockBusy(RuntimeError):
    """Raised when a non-blocking lock is already held by another process."""


def _acquire(handle, blocking: bool) -> None:
    if os.name == "nt":
        handle.seek(0)
        mode = msvcrt.LK_NBLCK
        while True:
            try:
                msvcrt.locking(handle.fileno(), mode, 1)
                return
            except OSError:
                if not blocking:
                    raise LockBusy(handle.name)
                time.sleep(0.1)
    flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        fcntl.flock(handle, flags)
    except BlockingIOError:
        raise LockBusy(handle.name)


def _release(handle) -> None:
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def exclusive_lock(path: Path | str, *, blocking: bool = True) -> Iterator[None]:
    """Hold an exclusive lock on ``path`` for the duration of the block."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        _acquire(handle, blocking)
        try:
            yield
        finally:
            _release(handle)
