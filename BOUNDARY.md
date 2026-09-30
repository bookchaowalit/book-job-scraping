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

## Status (2026-09-30)

- Scraping repo: collection scheduler active (Windows Task Scheduler, 2026-09-30); health monitor green; live send/apply remains gated.
- `crypto_prices`: CoinGecko API capture is active after a bounded smoke; lake-first ingestion and the read-only API remain in `book-crypto-data`.
- `exchange_rates`: Frankfurter API capture is active after a bounded smoke; lake-first ingestion and the read-only API remain in `book-fx-data`.
- `stock_prices`: Yahoo Finance chart API capture is active after all nine configured tickers passed a bounded smoke; lake-first ingestion and the read-only API remain in `book-finance-data`.
- `ai_tools`: Futurepedia HTML capture is active after a six-page bounded smoke returned 62 unique tools with category and canonical URL attribution; durable AI discovery lake/API ownership remains downstream of this producer.
- `defi_yields`: DefiLlama pools API capture is migrated after a Firefox-UA live smoke returned validated pools with a fresh provider timestamp; collection now runs from `book-defi-data`, and lake/API ownership remains in that product.
- News RSS, Kaidee classifieds, and Wongnai restaurants are migrated and their
  code was removed on 2026-09-30 (byte-identical copies live in
  `book-news-scraping`, `book-ecommerce-scraping`, and `book-restaurant-scraping`,
  which own their crons). Property remains here until `book-property-scraping`
  has the demand/lead workflows added in f80bea7.
- `ddproperty_condos`: Thai `/เช่าคอนโด` `__NEXT_DATA__` parser is ready, but
  httpx collection is still Cloudflare 403, so the scheduler job stays disabled.
- `book-job-data`: present as first-party parent-tracked path (catalog guard exception).
- BD-011 / BD-026: boundary documented; selective commit of scraping dirty still per DIRTY-TRIAGE.
