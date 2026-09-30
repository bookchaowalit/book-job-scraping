# Upgrade Plan

**Current state: 7/10** — broad, well-documented collection + prep pipeline
with a green offline suite (214 tests) and CI; many one-off scripts in
`scripts/` remain untested and carry unused imports.

## Backlog

### P0
- (none open)

### P1
- Add tests for `core/use_cases.py` (`ScrapeUseCase` / `SearchUseCase`) with
  fake ports, and for `adapters/outbound/storage_adapter.py` on a temp dir.
- `DataCleaner.clean()` mutates caller dicts when `normalize_text=False`;
  copy items before schema cleaning.
- `DataCleaner._normalize_date` is a stub: implement Thai month + Buddhist
  era parsing ("13 มิ.ย. 2569" → ISO) with tests.
- Add a Windows CI job (runtime host is Windows; see `ops/windows/`).

### P2
- `ruff check --select F401 --fix` across `core/`, `adapters/`, `scripts/`
  (≈40 unused imports), then widen the CI ruff rule set.
- Split `requirements.txt` into runtime vs. optional browser/AI extras so
  CI does not need Playwright/Selenium wheels.
- Deduplicator uses MD5 for content keys (fine for dedup, not security);
  document or switch to `sha256` with a migration for `data/hash_db.json`.

## Done in this pass (2026-09-30)
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
