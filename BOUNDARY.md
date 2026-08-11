# Boundary: book-job-scraping ↔ book-job-data

## Roles

| Repo | Role | Git |
|---|---|---|
| `book-job-scraping` | **Producer** — scrape, normalize, write collection artifacts | Nested Git under Book Dev |
| `book-job-data` | **Data product / lake boundary** — durable datasets, contracts, projections | Parent-tracked compatibility mirror under tools (**no nested `.git`**) |

## Allowed flow

```text
External job boards
    → book-job-scraping (collect + validate + local data/)
    → optional handoff / publish into lake-first product paths
    → book-job-data (schemas, fixtures, product contract if present)
```

## Rules

1. Scrapers **must not** embed Solo Empire monorepo secrets or absolute machine paths in commits.
2. `book-job-data` is **not** a second place to reinvent scrapers — it holds product/data contracts.
3. Large dirty sets in scraping stay inside the nested scraping repo; do not copy into parent monorepo.
4. Never commit raw credential files, browser profiles, or PII dumps.
5. Interview claims: producer depth lives in scraping PRODUCT/README; lake claims need data-product evidence.

## Status (2026-08-11)

- Scraping repo: active dirty tree + PRODUCT.md present.
- `book-job-data`: present as first-party parent-tracked path (catalog guard exception).
- BD-011 / BD-026: boundary documented; selective commit of scraping dirty still per DIRTY-TRIAGE.
