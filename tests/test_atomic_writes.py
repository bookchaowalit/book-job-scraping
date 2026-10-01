"""Crash-safety tests: stores under data/ are replaced atomically.

A scheduled tick can be killed mid-write (Task Scheduler timeout, taskkill).
The previous store must survive intact instead of being truncated.
"""
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from adapters.outbound.storage_adapter import StorageAdapter
from core import atomic_io
from core.atomic_io import write_json_atomic
from core.models import JobListing
from core.pipeline.deduplicator import Deduplicator

ROOT = Path(__file__).resolve().parent.parent


def _job(n):
    return JobListing(title=f"Job {n}", url=f"https://example.test/jobs/{n}", source="test")


def _leftover_temps(directory: Path):
    return [p.name for p in directory.iterdir() if p.name.endswith(".tmp")]


def test_write_json_atomic_roundtrip_and_no_temp(tmp_path):
    target = tmp_path / "nested" / "store.json"
    write_json_atomic(target, {"ข้อมูล": [1, 2]}, ensure_ascii=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"ข้อมูล": [1, 2]}
    assert _leftover_temps(target.parent) == []


def test_unserializable_payload_leaves_previous_file(tmp_path):
    target = tmp_path / "store.json"
    target.write_text('["old"]', encoding="utf-8")
    with pytest.raises(TypeError):
        write_json_atomic(target, [object()])
    assert target.read_text(encoding="utf-8") == '["old"]'
    assert _leftover_temps(tmp_path) == []


def test_interrupted_replace_keeps_store_and_cleans_temp(tmp_path, monkeypatch):
    storage = StorageAdapter(data_dir=tmp_path)
    storage.save([_job(1), _job(2)], "jobs")
    store = tmp_path / "jobs" / "items.json"
    before = store.read_text(encoding="utf-8")

    def interrupted(src, dst):
        raise KeyboardInterrupt("tick stopped")

    monkeypatch.setattr(atomic_io.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        StorageAdapter(data_dir=tmp_path).save([_job(3)], "jobs")

    assert store.read_text(encoding="utf-8") == before
    assert len(json.loads(before)) == 2
    assert _leftover_temps(store.parent) == []


def test_storage_survives_process_killed_mid_write(tmp_path):
    """Hard-kill a child while it is inside save(); items.json stays valid."""
    storage = StorageAdapter(data_dir=tmp_path)
    storage.save([_job(n) for n in range(3)], "jobs")
    store = tmp_path / "jobs" / "items.json"
    before = store.read_text(encoding="utf-8")
    marker = tmp_path / "writing.flag"

    child = textwrap.dedent(
        f"""
        import os, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from core import atomic_io
        from core.models import JobListing
        from adapters.outbound.storage_adapter import StorageAdapter

        def slow_fsync(fd):
            Path({str(marker)!r}).write_text("1")
            time.sleep(60)  # killed here: temp file written, target untouched

        atomic_io.os.fsync = slow_fsync
        items = [JobListing(title="New %d" % n, url="https://example.test/new/%d" % n,
                            source="test") for n in range(500)]
        StorageAdapter(data_dir=Path({str(tmp_path)!r})).save(items, "jobs")
        """
    )
    proc = subprocess.Popen([sys.executable, "-c", child])
    try:
        deadline = time.monotonic() + 30
        while not marker.exists():
            assert proc.poll() is None, "child exited before reaching the write"
            assert time.monotonic() < deadline, "child never reached the write"
            time.sleep(0.05)
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert store.read_text(encoding="utf-8") == before
    assert len(StorageAdapter(data_dir=tmp_path).load("jobs")) == 3


def test_deduplicator_hash_db_written_atomically(tmp_path, monkeypatch):
    db = tmp_path / "hash_db.json"
    dedup = Deduplicator(hash_db=db)
    dedup.seen_hashes = {"abc": {"first_seen": "2026-01-01"}}
    dedup.save()
    before = db.read_text(encoding="utf-8")

    dedup.seen_hashes["def"] = {"first_seen": "2026-01-02"}
    monkeypatch.setattr(atomic_io.os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        dedup.save()
    assert db.read_text(encoding="utf-8") == before
    assert _leftover_temps(tmp_path) == []
    assert not os.path.exists(str(db) + ".tmp")
