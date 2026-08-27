# Release / Runbook (BD-039) — book-job-scraping

**Date:** 2026-08-25
**Tier:** A flagship  
**Status:** local collection scheduler active; live application send/apply remains gated.
Fill env values only in a private secrets store; never commit secrets.

## Install / build

```bash
cd projects/product/engineering/book-dev/github/bookchaowalit/book-apps/tools/book-job-scraping
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

For browser-backed scrapers, install the Playwright browser if needed:

```bash
.venv/bin/playwright install chromium
```

## Configure

| Variable | Required for collection | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | No | Optional AI enrichment; health remains green when absent |
| `TELEGRAM_*` | No | Optional health notification; never required for collection |
| `FIRECRAWL_API_KEY` | For Firecrawl jobs | Resolve from the private secret store; never commit |

Use `.env.example` when present. **Do not** commit `.env`, tracker CSVs,
browser profiles, or raw PII.

## Run collection

Run due jobs once:

```bash
.venv/bin/python main.py run
```

Install/inspect the local five-minute scheduler:

```bash
bash setup_cron.sh install
bash setup_cron.sh status
```

The installed command runs `main.py run` and then
`scripts/pipeline_health_monitor.py` under the same `flock` lock.

## Review source coverage

Before enabling a new business source, validate the registry and inspect its
restoration queue:

```bash
.venv/bin/python scripts/source_coverage.py --check
.venv/bin/python scripts/source_coverage.py
```

Add a source to `config/source_coverage.yaml` and `config/jobs.yaml` together.
Prefer an official API, CLI/export, or RSS feed before implementing a scraper;
every scraper adapter needs a source-specific contract, rate-limit/terms
review, and a focused smoke test.

For `ddproperty_condos`, run the focused checks before enabling the schedule:

```bash
.venv/bin/python -m unittest tests/test_ddproperty_scraper.py -v
.venv/bin/python main.py run ddproperty_condos
```

The adapter may fall back to bounded search when DDproperty rejects direct
requests. Treat zero priced rows as a blocked smoke result; do not enable the
job until the snapshot contains trustworthy rental prices.

For `crypto_prices`, the scheduler uses the bounded public CoinGecko API
capture. Verify the adapter contract and output before changing its coin or
currency list:

```bash
.venv/bin/python -m unittest tests/test_crypto_prices.py -v
.venv/bin/python main.py run crypto_prices
```

The job is enabled only when the API returns every requested coin/currency
pair with finite positive prices. A partial or malformed response fails closed.

For `exchange_rates`, the adapter preserves the provider date and validates
the configured base plus every requested symbol:

```bash
.venv/bin/python -m unittest tests/test_exchange_rates.py -v
.venv/bin/python main.py run exchange_rates
```

Raw JSON and CSV projections are local producer artifacts; lake/API ownership
remains with `book-fx-data`.

For `stock_prices`, the adapter calls Yahoo Finance's bounded chart endpoint
once per configured ticker and fails closed on symbol mismatch, unsupported
intervals, unordered timestamps, missing closes, or missing previous close:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_stock_prices.py' -v
.venv/bin/python main.py run stock_prices
```

Raw JSON and CSV projections are local producer artifacts; lake/API ownership
remains with `book-finance-data`.

For `kaidee_classifieds`, the adapter uses one bounded public HTML page and
parses the embedded `__NEXT_DATA__` listing payload. It keeps only priced
listings, deduplicates by listing ID, canonicalizes HTTPS Kaidee URLs, and
fails closed when the page has no contract-compliant rows:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_kaidee_scraper.py' -v
.venv/bin/python main.py run kaidee_classifieds
```

Review source terms and rate limits before adding more pages or categories.
The raw payload and CSV projections remain local producer artifacts for the
downstream marketplace data product.

For `matichon_news`, the adapter uses the public RSS feed, keeps only entries
with a title, canonical Matichon URL, and normalized publication date, and
preserves feed/source attribution:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_matichon_scraper.py' -v
.venv/bin/python main.py run matichon_news
```

The raw XML and CSV projections remain local producer artifacts for the
downstream news data product.

For `thai_tech_news`, the adapter uses Blognone's current
`/atom.xml` feed (the legacy `/atom` path returns 404), preserves Blognone
article IDs, and keeps only canonical technology articles with publication
dates:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_thai_tech_scraper.py' -v
.venv/bin/python main.py run thai_tech_news
```

The raw XML and CSV projections remain local producer artifacts for the
downstream news data product.

For `thai_business_news`, the adapter uses only the Bangkok Post Business RSS
feed, normalizes source timestamps to UTC using the Bangkok timezone when the
feed omits an offset, and keeps only attributed canonical business articles:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_thai_business_scraper.py' -v
.venv/bin/python main.py run thai_business_news
```

The raw XML and CSV projections remain local producer artifacts for the
downstream news data product.

For `wongnai_bangkok`, the adapter reads Wongnai's public restaurant HTML and
the embedded `window._wn` state. It requests at most three pages of 100
records, validates canonical restaurant URLs, and keeps only rows whose
embedded address is attributed to Bangkok:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_wongnai_scraper.py' -v
.venv/bin/python main.py run wongnai_bangkok
```

The bounded raw pages and CSV projections remain local producer artifacts for
the downstream restaurant data product. Review Wongnai terms and the 4-second
rate limit before increasing page count or page size.

The `wongnai_upcountry` schedule reuses the same parser with the explicit
`locationKey=6` source URL and the `khonkaen`, `korat`, and `pattaya` matchers.
Its three-page smoke returned 28 unique rows, including the Chon Buri city label
used by the Pattaya matcher:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_wongnai_scraper.py' -v
.venv/bin/python main.py run wongnai_upcountry
```

For `ai_tools`, the adapter uses Futurepedia's public HTML directory across the
configured `ai-agents`, `productivity`, and `code` categories. It requests at
most two pages per category, keeps only canonical `/tool/<slug>` URLs, and
preserves category, description, rating, pricing, and source attribution:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_ai_tools.py' -v
.venv/bin/python main.py run ai_tools
```

The bounded raw pages and CSV projections remain local producer artifacts for
the downstream AI discovery data product. Review Futurepedia terms and the
4-second rate limit before increasing category/page bounds.

For `defi_yields`, collection is migrated to `book-defi-data`. The adapter
still lives here for tests, but the local scheduler job is disabled. The
domain cron calls DefiLlama's public pools API with a Firefox User-Agent
(python-httpx UAs return a non-JSON Allow body), maps configured `Optimism`
to the provider's `OP Mainnet`, keeps only the configured chains with APY at
least 5% and TVL at least $1M, caps the snapshot at 200 pools, and rejects
responses older than 24 hours:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_defi_yields.py' -v
# live collection: book-defi-data/scripts/run_defi.py
```

The raw response and CSV projections remain producer artifacts in
`book-defi-data/data/exported`. Review DefiLlama freshness, pool/APY/TVL
validation, source terms, and the 1-second rate limit before changing chain
or threshold bounds.

## Health check

```bash
.venv/bin/python scripts/pipeline_runner.py --health
.venv/bin/python scripts/pipeline_health_monitor.py
```

Healthy collection requires fresh `job_postings.csv`, `matched_jobs.csv`,
`apply_tracker.csv`, and `job_descriptions.csv`. The default health mode does
not require optional AI, notification, or live-application steps.

## Rollback

1. Remove only this repository's scheduler entry:
   `bash setup_cron.sh remove`
2. Keep `data/` intact for review; it is ignored runtime output.
3. Do not enable live email/ATS paths. They require the explicit gates in
   `SAFETY.md`.

## Verified state (2026-08-24)

- Cron service active; scraper entry installed every five minutes.
- Collection health: `All systems healthy`.
- Safety tests: 17 passed; no live send/apply executed.
- Runtime snapshot: 1,647 postings, 118 matches, 106 discovered tracker rows,
  10 descriptions, and 5 resume variants.

## Owner

Solo operator (bookchaowalit). No multi-person on-call.

## Non-claims

This is not proof of production uptime. Nested work may still be dirty or
unpushed, and absent source adapters remain intentionally disabled.
