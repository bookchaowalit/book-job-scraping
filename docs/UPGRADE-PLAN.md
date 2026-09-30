# Upgrade Plan

**Current state: 7.5/10** (pass 1: 7; pass 2: 7 -> 7.5) — broad,
well-documented collection + prep pipeline with a green offline suite (~230
tests), Linux CI plus a Windows scheduler job; many one-off scripts in
`scripts/` remain untested and carry unused imports.

## Backlog

### P0
- (none open)

### P1
- Add tests for `core/use_cases.py` (`ScrapeUseCase` / `SearchUseCase`) with
  fake ports, and for `adapters/outbound/storage_adapter.py` on a temp dir.

- Widen the Windows CI job from the scheduler tests to the full offline
  suite once it is known to pass on Windows (needs a first green run).
- `ops/windows/scheduled-task.ps1`: confirm on the host that a `-Once`
  trigger without `-RepetitionDuration` repeats indefinitely on its Windows
  build (behaviour differs across versions); add it explicitly if not.

### P2
- `ruff check --select F401 --fix` across `core/`, `adapters/`, `scripts/`
  (≈40 unused imports), then widen the CI ruff rule set.
- Split `requirements.txt` into runtime vs. optional browser/AI extras so
  CI does not need Playwright/Selenium wheels.
- Deduplicator uses MD5 for content keys (fine for dedup, not security);
  document or switch to `sha256` with a migration for `data/hash_db.json`.

## Done in this pass (pass 1, 2026-09-30)
- Fixed `DataCleaner` bugs: job/news titles truncated at any hyphen
  ("Front-End Developer" → "Front"); salary/price parsing crashed on a bare
  comma ("Negotiable, DOE") and on decimals; Thai phone regex cut the last
  digit of hyphenated mobiles.
- `Deduplicator`: UTF-8 file I/O (Windows cp1252 safety), `keep="last"`
  now counts repeats like `keep="first"`.
- `scripts/interview_question_bank.py` crashed on import (`os` and Telegram
  names undefined); now imports cleanly and skips Telegram when unset.
- `requests` added to `requirements.txt` (imported by 15 modules).
- `pytest.ini` scopes collection to `tests/` (the live ATS probe in
  `scripts/` broke collection).
- New `tests/test_core_pipeline.py` (17 tests) for cleaner + deduplicator.
- CI workflow: ruff syntax/undefined-name gate + offline pytest.
- README dependency list corrected; test instructions added.

## Done in this pass (pass 2)
- `scripts/scheduled_run.py` Windows assumptions: per-step timeouts (45 + 5
  min, under the 1 h task limit) that kill the whole process tree
  (`taskkill /T` / process group), since Windows leaves children running when
  Task Scheduler stops the tick and the next tick could overlap them;
  `cron.log` rotation at 5 MB (no logrotate on Windows).
- New `tests/test_scheduled_run.py` (order/exit codes, busy-lock skip,
  grandchild killed on timeout, rotation) and a `windows-latest` CI job
  running the file-lock and scheduler tests.
- `DataCleaner.clean()` no longer mutates caller dicts; `_normalize_date`
  parses Thai month names / Buddhist-era years to ISO dates (with tests).
