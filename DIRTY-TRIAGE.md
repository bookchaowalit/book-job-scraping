# book-job-scraping — Dirty Tree Triage

**Snapshot:** 2026-08-11  
**~68 dirty paths** — mostly `scripts/` path/safety migration (large line churn, same theme).

## Top-level counts

| Path | Count | Notes |
|---|---:|---|
| `scripts/` | ~62 | Path rewrite + send gates |
| `tests/` | untracked | Safety/path unit tests |
| `core/`, `config/`, `requirements.txt` | few | Foundation |
| `README.md`, `SAFETY.md`, `PRODUCT.md` | docs | |

## High-risk scripts (review before any commit that enables automation)

- `scripts/send_application_emails.py`
- `scripts/auto_send_email.py`
- `scripts/send_followup_emails.py`
- `scripts/ats_auto_apply.py`
- `scripts/auto_apply.py`
- `scripts/cron_scheduler.py` / `setup_cron.sh`

Confirm they still call `safety` gates and never `pip install` at runtime.

## Suggested commit order

1. Foundation: `repo_paths.py`, `safety.py`, `core/config.py`, tests, SAFETY.md  
2. Bulk scripts path migration  
3. Docs: README + PRODUCT.md  

## Verification before commit

```bash
python3 -m unittest tests/test_paths_and_safety.py -v
# optional dry-runs
python scripts/pipeline_runner.py --dry-run
python scripts/auto_apply.py --dry-run
python scripts/ats_auto_apply.py --test
```

## Secrets

Never commit `.env`, tracker CSVs with personal data, or Telegram/API tokens.
`TELEGRAM_CHAT_ID` defaults in old scripts should not be reintroduced as
hardcoded production IDs.
