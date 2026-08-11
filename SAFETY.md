# book-job-scraping — Safety & P0 Status

**Status:** code present, **not production-ready** for live applications.  
**Last updated:** 2026-08-07

## Correct operating statement

- Solo Empire root cron may still be active for other systems.
- There is **no active cron/process** for this legacy book-job-scraping pipeline unless explicitly installed from this repo.
- Live email/ATS send paths exist but are **blocked by default**.

## P0 fixes applied

1. **Paths** — scripts resolve `REPO_ROOT` / `data/` / `scripts/` from this repo (`scripts/repo_paths.py`), not `domains/book-dev/book-scraping`.
2. **Dependencies** — use project venv + `requirements.txt`; scripts must not `pip install` at runtime.
3. **Send gates** — live send/apply requires:
   - CLI flag (`--send` or `--apply`)
   - `BOOK_JOB_LIVE_SEND_ENABLED=1`
   - `BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND`
4. **`--test` safety** — `ats_auto_apply.py --test` is preview-only (never opens Chrome / never submits).
5. **Status semantics** — draft generators write `prepared` (legacy `auto_applied` is treated as prepared on read). `submitted` is for real sends only.

## Do not do (until explicitly ordered)

- Do not run `send_application_emails.py --send`
- Do not run `auto_send_email.py --send`
- Do not run `send_followup_emails.py --send`
- Do not run `ats_auto_apply.py --apply`
- Do not install `cron_scheduler.py` / `setup_cron.sh` for this pipeline
- Do not set the unlock env vars casually

## Local setup

```bash
cd path/to/book-job-scraping
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# optional lighter test deps only:
# pip install httpx pyyaml

# smoke
python scripts/pipeline_runner.py --dry-run
python scripts/auto_apply.py --dry-run
python scripts/ats_auto_apply.py --test
python -m unittest tests/test_paths_and_safety.py -v
```

Runtime data lives in `./data/` (gitignored except `.gitkeep`).

## Tracker dual-write note (P1)

| Tracker | Role |
|---|---|
| `data/apply_tracker.csv` | Legacy nested pipeline tracker |
| Solo Empire `docs/opportunities/JOB-TRACKER.md` | Canonical submitted-applications record |

Bridge or retire the legacy tracker before relying on automation for inventory.
