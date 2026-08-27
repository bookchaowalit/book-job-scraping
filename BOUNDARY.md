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

## Status (2026-08-25)

- Scraping repo: collection cron active; health monitor green; live send/apply remains gated.
- `crypto_prices`: CoinGecko API capture is active after a bounded smoke; lake-first ingestion and the read-only API remain in `book-crypto-data`.
- `exchange_rates`: Frankfurter API capture is active after a bounded smoke; lake-first ingestion and the read-only API remain in `book-fx-data`.
- `stock_prices`: Yahoo Finance chart API capture is active after all nine configured tickers passed a bounded smoke; lake-first ingestion and the read-only API remain in `book-finance-data`.
- `kaidee_classifieds`: Kaidee HTML capture is active after a bounded smoke returned eight priced canonical listings; durable marketplace lake/API ownership remains downstream of this producer.
- `matichon_news`: Matichon RSS capture is active after a bounded smoke returned fifty attributed canonical articles; durable news lake/API ownership remains downstream of this producer.
- `thai_business_news`: Bangkok Post Business RSS capture is active after a bounded smoke returned ten attributed canonical business articles; durable news lake/API ownership remains downstream of this producer.
- `thai_tech_news`: Blognone Atom-compatible capture is active after a bounded smoke returned ten attributed canonical technology articles; durable news lake/API ownership remains downstream of this producer.
- `wongnai_bangkok`: Wongnai HTML capture is active after a three-page bounded smoke returned 161 unique Bangkok-attributed restaurants; durable restaurant lake/API ownership remains downstream of this producer.
- `wongnai_upcountry`: Wongnai HTML capture is active after a three-page bounded smoke returned 28 unique restaurants across Khon Kaen, Korat, and Pattaya with city attribution; durable restaurant lake/API ownership remains downstream of this producer.
- `ai_tools`: Futurepedia HTML capture is active after a six-page bounded smoke returned 62 unique tools with category and canonical URL attribution; durable AI discovery lake/API ownership remains downstream of this producer.
- `defi_yields`: DefiLlama pools API capture is migrated after a Firefox-UA live smoke returned validated pools with a fresh provider timestamp; collection now runs from `book-defi-data`, and lake/API ownership remains in that product.
- News RSS (`notebookspec_tech`, `matichon_news`, `thai_business_news`,
  `thai_tech_news`) is migrated: local scheduler jobs are disabled; collection
  runs from `book-news-scraping`.
- `notebookspec_tech`: dedicated RSS adapter is active after a bounded live
  smoke returned 20 attributed canonical articles; durable news lake/API
  ownership remains downstream in `book-news-scraping`.
- `ddproperty_condos`: Thai `/เช่าคอนโด` `__NEXT_DATA__` parser is ready, but
  httpx collection is still Cloudflare 403, so the scheduler job stays disabled.
- `book-job-data`: present as first-party parent-tracked path (catalog guard exception).
- BD-011 / BD-026: boundary documented; selective commit of scraping dirty still per DIRTY-TRIAGE.
