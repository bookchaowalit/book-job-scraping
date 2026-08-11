#!/usr/bin/env python3
"""One-shot path + runtime-pip migration helper (run from repo root).

Rewrites legacy monorepo path roots and removes silent pip installs.
Safe to re-run (idempotent for already-migrated files).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

PATH_BLOCK_REPLACEMENTS = [
    # Path segment style: ROOT / "domains" / "book-dev" / "book-scraping" / "data"
    (
        re.compile(
            r'(\w+)\s*/\s*"domains"\s*/\s*"book-dev"\s*/\s*"book-scraping"\s*/\s*"data"'
        ),
        r'\1 / "data"',
    ),
    (
        re.compile(
            r'(\w+)\s*/\s*"domains"\s*/\s*"book-dev"\s*/\s*"book-scraping"\s*/\s*"scripts"'
        ),
        r'\1 / "scripts"',
    ),
    (
        re.compile(
            r'(\w+)\s*/\s*"domains"\s*/\s*"book-dev"\s*/\s*"book-scraping"\s*/\s*"opportunities"\s*/\s*"data"'
        ),
        r'\1 / "data" / "opportunities"',
    ),
    # String path docs / absolute legacy
    (
        re.compile(
            r"domains/product/engineering/book-dev/book-scraping"
        ),
        "scripts (book-job-scraping)",
    ),
    (
        re.compile(
            r"domains/book-dev/book-scraping"
        ),
        "data",
    ),
    (
        re.compile(
            r"/home/bookchaowalit/book-everything/solo-empire/domains/product/engineering/book-dev/book-scraping"
        ),
        str(REPO),
    ),
]

# ROOT = Path(__file__).resolve().parents[N]  where N >= 2 and file is under scripts/
ROOT_ASSIGN_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>ROOT|PROJECT_ROOT)\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(?P<n>\d+)\]\s*$",
    re.M,
)

# dotenv _root = Path(...).parents[N]
DOTENV_ROOT_RE = re.compile(
    r"(?P<indent>\s*)_root\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*",
)

# Runtime pip install blocks (several styles)
PIP_INSTALL_PATTERNS = [
    # try import X except: subprocess pip install ... import X
    re.compile(
        r"try:\n"
        r"(?P<body>(?:[ \t]+.+\n)+?)"
        r"except ImportError:\n"
        r"(?:[ \t]+import subprocess\n)?"
        r"[ \t]+subprocess\.check_call\(\[[^\]]*(?:pip[^\]]*install|\"pip\")[^\]]*\][^\)]*\)\n"
        r"(?:[ \t]+.+\n)*?",
        re.M,
    ),
]


def fix_root_assignments(text: str, path: Path) -> str:
    """Point ROOT/PROJECT_ROOT at book-job-scraping repo root when under scripts/."""

    def repl(m: re.Match) -> str:
        n = int(m.group("n"))
        name = m.group("name")
        indent = m.group("indent")
        # scripts/*.py → parents[1] is repo root
        if path.parent.name == "scripts" and n >= 2:
            return f"{indent}{name} = Path(__file__).resolve().parents[1]"
        return m.group(0)

    return ROOT_ASSIGN_RE.sub(repl, text)


def fix_dotenv_root(text: str, path: Path) -> str:
    if path.parent.name != "scripts":
        return text

    def repl(m: re.Match) -> str:
        indent = m.group("indent")
        return f"{indent}_root = Path(__file__).resolve().parents[1]\n"

    return DOTENV_ROOT_RE.sub(repl, text)


def fix_path_segments(text: str) -> str:
    for pattern, repl in PATH_BLOCK_REPLACEMENTS:
        text = pattern.sub(repl, text)
    return text


def fix_runtime_pip(text: str) -> str:
    """Replace silent pip install with a clear SystemExit message."""

    # Pattern A: except ImportError:\n    import subprocess\n    subprocess.check_call([...pip install...])\n    import X
    pattern_a = re.compile(
        r"except ImportError:\n"
        r"(?P<indent>[ \t]+)(?:import subprocess\n(?P=indent))?"
        r"subprocess\.check_call\(\[(?P<args>[^\]]+)\](?P<extra>[^\)]*)\)\n"
        r"(?P=indent)import (?P<mod>\w+)\n",
        re.M,
    )

    def repl_a(m: re.Match) -> str:
        indent = m.group("indent")
        mod = m.group("mod")
        args = m.group("args")
        # Guess package name from pip args
        pkg = mod
        for token in re.findall(r'["\']([^"\']+)["\']', args):
            if token not in {
                "sys.executable",
                "-m",
                "pip",
                "install",
                "-q",
                "--break-system-packages",
                "--user",
            } and not token.startswith("-"):
                pkg = token
                break
        return (
            f"except ImportError:\n"
            f"{indent}raise SystemExit(\n"
            f"{indent}    \"Missing dependency '{pkg}'. \"\n"
            f"{indent}    \"Install via project venv: pip install -r requirements.txt \"\n"
            f"{indent}    \"(scripts must not pip-install at runtime)\"\n"
            f"{indent})\n"
        )

    text = pattern_a.sub(repl_a, text)

    # Pattern B: bare subprocess.check_call pip install after print ERROR
    # Leave print ERROR lines; remove only check_call install lines that follow import failure paths.
    # Safer: replace any remaining subprocess.check_call with pip install
    pattern_b = re.compile(
        r"(?P<indent>[ \t]+)subprocess\.check_call\(\[[^\]]*pip[^\]]*install[^\]]*\][^\)]*\)\n",
        re.M,
    )

    def repl_b(m: re.Match) -> str:
        indent = m.group("indent")
        return (
            f"{indent}raise SystemExit(\n"
            f"{indent}    \"Missing dependency. Install via project venv: \"\n"
            f"{indent}    \"pip install -r requirements.txt (no runtime pip install)\"\n"
            f"{indent})\n"
        )

    text = pattern_b.sub(repl_b, text)
    return text


def migrate_file(path: Path) -> bool:
    if path.name in {"_migrate_p0_paths.py", "repo_paths.py", "safety.py"}:
        return False
    original = path.read_text(encoding="utf-8")
    text = original
    text = fix_root_assignments(text, path)
    text = fix_dotenv_root(text, path)
    text = fix_path_segments(text)
    text = fix_runtime_pip(text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def migrate_jobs_yaml() -> bool:
    path = REPO / "config" / "jobs.yaml"
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    text = original.replace(
        "domains/book-dev/book-scraping/data/", "data/"
    )
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if migrate_file(path):
            changed.append(path.relative_to(REPO).as_posix())
    if migrate_jobs_yaml():
        changed.append("config/jobs.yaml")
    print(f"Migrated {len(changed)} file(s):")
    for c in changed:
        print(f"  • {c}")


if __name__ == "__main__":
    main()
