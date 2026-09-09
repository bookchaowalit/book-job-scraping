# book-job-scraping — Safety & P0 Status

**Status:** collection scheduler active; **not production-ready** for live applications.
**Last updated:** 2026-08-31

**Career workflow update (2026-09-07):** See [CAREER-WORKFLOW.md](CAREER-WORKFLOW.md).
The onsite/Thailand/concurrent-employment exclusions below apply to the
`remote_contract` lane. Career changes have separate source-backed eligibility
and transition checks. New packets support reviewed manual ATS submission and
receipt metadata handoff; they do not certify or unlock the legacy senders.

## Correct operating statement

- This repository's collection cron is explicitly installed and active every
  five minutes via `setup_cron.sh`.
- The cron runs only due collection jobs, then the health monitor, under a
  `flock` lock. It does not send applications or write the Solo Empire DB.
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
6. **Scheduler safety** — cron uses the repository `.venv`, prevents overlap
   with `flock`, and runs `pipeline_health_monitor.py` after collection.
7. **Contract-first qualification** — `config/job_targeting.yaml` classifies
   every match as `PASS`, `VERIFY`, or `REJECT`. Thai full-time, geo-ineligible,
   onsite/hybrid, exclusivity, and explicit Thai employee/social-security
   listings cannot reach promotion or preparation.
8. **Submission approval** — live email/ATS paths additionally require
   `qualification_status=PASS` and `application_readiness=APPROVED`. The
   existing CLI + two environment unlock gates still apply after that check.
9. **Bridge-to-hire safety** — volunteer/internship signals remain
   `VERIFY`/review-only; paid bridge programs require human evidence for
   compensation, bounded scope/duration, mentor, and conversion/reference path.
   Upfront-fee, income-share-entry, and indefinite unpaid production signals
   are rejected.

## Do not do (until explicitly ordered)

- Do not run `send_application_emails.py --send`
- Do not run `email_application.py --send` or batch `--no-dry-run`
- Do not run `auto_send_email.py --send`
- Do not run `send_followup_emails.py --send`
- Do not run `ats_auto_apply.py --apply`
- Do not enable live send/apply or set the unlock env vars casually.
- Do not mark `application_readiness=APPROVED` until contract, current-employer
  conflict, hours/timezone, IP/confidentiality, tax, and payroll/EOR terms have
  been reviewed.
- `setup_cron.sh` is collection-only; use `setup_cron.sh remove` to pause this
  repository's scheduler.

## Local setup

```bash
cd path/to/book-job-scraping
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# optional lighter test deps only:
# pip install httpx pyyaml

# smoke
.venv/bin/python scripts/pipeline_runner.py --dry-run
.venv/bin/python scripts/pipeline_runner.py --health
.venv/bin/python scripts/auto_apply.py --dry-run
.venv/bin/python scripts/ats_auto_apply.py --test
.venv/bin/python -m unittest tests/test_paths_and_safety.py -v
.venv/bin/python -m unittest tests/test_job_target_policy.py -v
```

## Current verification

On 2026-08-24, the collection health check passed with fresh core artifacts:
`job_postings.csv`, `matched_jobs.csv`, `apply_tracker.csv`, and
`job_descriptions.csv`. Optional OpenRouter enrichment and Telegram alerts are
not required for collection health and remain disabled unless explicitly
configured.

Runtime data lives in `./data/` (gitignored except `.gitkeep`).

## Tracker dual-write note (P1)

| Tracker | Role |
|---|---|
| `data/apply_tracker.csv` | Legacy nested pipeline tracker |
| Solo Empire `opportunities/applications/JOB-TRACKER.md` | Canonical submitted-applications record |

Use `application_review.py` and the parent's `import_job_applications.py` for
the confirmed-receipt handoff. The legacy tracker is not automatically migrated;
old `applied`/`sent` labels alone are not confirmed submission evidence.
