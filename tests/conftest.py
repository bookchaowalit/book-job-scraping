"""Shared pytest setup.

Subprocess-based tests run repo scripts that print non-ASCII (Thai, ✓/✗).
Match the scheduled runtime, which sets PYTHONUTF8=1, so Windows consoles
using cp1252 do not raise UnicodeEncodeError in child processes.
"""
import os

os.environ.setdefault("PYTHONUTF8", "1")
