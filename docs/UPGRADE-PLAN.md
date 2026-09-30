# Upgrade Plan

**Current state: 8/10** (pass 1: 7; pass 2: 7 -> 7.5; pass 3: 7.5, core
ports now covered; pass 4: 7.5 -> 8, stores written atomically) — broad, well-documented collection + prep pipeline with a
green offline suite (243 tests), Linux CI plus a Windows scheduler job; many
one-off scripts in `scripts/` remain untested and carry unused imports.

## Backlog

### P0
- (none open)

### P1
- Remaining in-place JSON writers (`core/pipeline/cleaner.py` output,
  `adapters/outbound/exporter_adapter.py`, `utils/exporters.py`,
  `engines/base.py`) are regenerable exports; move them to
  `core.atomic_io.write_json_atomic` if any becomes a source of truth.
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

## Done in this pass (pass 3)
- Bug: `DataCleaner._normalize_date` truncated ISO datetimes for news
  `published` to `YYYY-MM-DD` (dropping time and timezone) despite its
  no-loss docstring. ISO / RFC 2822 values are now returned unchanged; only
  Thai month names and Buddhist-era years are normalized, and a trailing
  Thai time ("14:30", "14.30 น.") is preserved as `YYYY-MM-DDTHH:MM:SS`.
- `ScrapeUseCase.execute`: duration recorded on every path (early returns
  used to report 0 s), errors appended instead of overwritten.
- `SearchUseCase`: `max_price=0` is now a real filter; negative limits
  clamp to 0.
- `StorageAdapter`: range filters coerce display prices ("1,299",
  "฿1,299.50") instead of raising `TypeError` (MCP `search_products` crash
  on exported data); `load()` returns a copy of the cache; `exists()` skips
  corrupt/non-list files; news records load as `NewsArticle`.
- New `tests/test_use_cases_and_storage.py` (19 tests, fake ports + temp
  dirs); date tests cover ISO/timezone/RFC 2822 preservation. Suite 243
  passed; ruff 0.16.9 CI gate (`E9,F63,F7,F82`) clean.

## Done in this pass (pass 4)
- New `core/atomic_io.py` (`write_text_atomic` / `write_json_atomic`):
  serialize in memory, write a same-directory temp file, fsync, `os.replace`;
  the temp file is removed on any exception.
- `StorageAdapter.save()` (`data/<collection>/items.json`), the
  `Deduplicator` hash DB (`data/hash_db.json`) and the scheduler state file
  now use it, so a tick killed mid-write keeps the previous store instead of
  truncating it.
- New `tests/test_atomic_writes.py` (5 tests): round trip, unserializable
  payload, interrupted `os.replace`, and a real crash test that hard-kills a
  child process inside `save()` and checks `items.json` is unchanged. Added
  to the `windows-latest` CI job. Suite 248 passed; ruff 0.15.8 and 0.16.9
  CI gate clean.
- Cross-repo bug-pattern sweep (`tests/test_bug_pattern_sweep.py`, 7 tests):
  `scrape_property_listings.persist()` detects price drops *before*
  appending the run to history (it compared each price with itself, so no
  drop ever fired); ddproperty `_price_value` rejects NaN/inf (NaN slipped
  past `max_price`); `find_contact_emails` matches ATS/job-board hosts by
  exact host/subdomain, not substring; `parse_fb_search_results` keeps
  first-seen email order (`emails[0]` depended on set order); HN and
  Himalayas epochs are rendered in UTC, not host-local time.
- JSON run logs (`cron_log`, follow-up, company-intel, weekly-report) no
  longer replace the whole history with one entry after a failed read: new
  `scripts/json_store.load_json_for_update` moves an unreadable file aside as
  `<name>.corrupt-<UTC>` first (`tests/test_json_log_recovery.py`, 5 tests).
- Same fix for `networking_event_tracker` events and `multi_resume_manager`
  registry; `send_followup_emails.load_followup_log` now refuses to run on an
  unreadable log (treating it as empty re-sent every follow-up and then
  overwrote the history) and keeps `sent` entries of logs without `runs`.
- `scrape_discovered_jobs` (extractor routing + URL-slug parsing) and
  `prepare_applications` (ATS score bonus / apply URL) match ATS and board
  hosts exactly (`_host_is`), not by substring (`clever.com` was `lever.co`).
- Regression fix: `followup_tracker` no longer passes the shared
  `data/followup_log.json` through `load_json_for_update`. That renamed the
  legacy list-format log (which `send_followup_emails` accepts) to
  `.corrupt-*`, so the sender then saw no log and would re-send every
  follow-up. The tracker now normalizes a list to `{"runs": [], "sent": list}`
  like the sender, leaves an unreadable log in place (the sender refuses to
  run on it) and skips logging, and writes the log atomically. Tests: the
  tracker keeps a legacy list log and the sender still skips people already
  followed up; an unreadable log is left untouched.
