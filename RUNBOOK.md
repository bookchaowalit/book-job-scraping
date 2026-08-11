# Release / Runbook (BD-039) — book-job-scraping

**Date:** 2026-08-11  
**Tier:** A flagship  
**Status:** runbook stub — fill env values only in private secrets store, never commit secrets.

## Build

```bash
# Inspect README first for the authoritative flow.
# Common patterns:
#   npm ci && npm run build
#   docker compose build
#   flutter build apk   # mobile only
```

Detected: Docker marker=no; npm scripts sample=n/a

## Configure (names only)

| Variable class | Notes |
|---|---|
| Database URL | If backend present — never commit |
| JWT / SECRET_KEY | Backend auth — rotate if leaked |
| Public API base URL | Frontend `NEXT_PUBLIC_*` style |
| OAuth / third-party | Optional; leave disabled for demos |

Use `.env.example` when present. **Do not** commit `.env`.

## Run (local)

Prefer README. Typical:

```bash
# install deps → migrate DB if any → start API → start web
```

## Health check

see README /docs

## Rollback

1. Redeploy previous container image / previous git tag  
2. Keep DB migrations backward-compatible or document one-way migrations  
3. Feature flags: prefer observe-only / disabled bots (booktrading)

## Owner

Solo operator (bookchaowalit). No multi-person on-call.

## Non-claims

Not proof of production uptime. Nested work may still be dirty or unpushed.
