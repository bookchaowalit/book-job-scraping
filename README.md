# Book Job Scraping — Multi-Engine Capture + Job Pipeline

International remote career changes and relocation now have separate review
lanes. See [Career workflow](CAREER-WORKFLOW.md) for public company discovery,
review packets, exact-document preparation and receipt-backed manual
submission tracking. Live automated ATS submission remains unverified.

Hexagonal-architecture scraping platform with 5 engines, scheduled jobs,
MCP search over local storage, and a **job application prep** pipeline.

**Canonical nested path:**  
`projects/product/engineering/book-dev/github/bookchaowalit/book-apps/tools/book-job-scraping/`  
**Architecture:** Hexagonal (Ports & Adapters)  
**Engines:** httpx+BS4, Playwright, Selenium, Scrapy, RSS  
**Categories:** Jobs, E-commerce, Restaurants, Directories, News, Property  

**Producer contract / safety:** see [`PRODUCT.md`](./PRODUCT.md) and
[`SAFETY.md`](./SAFETY.md). This repo is **collection + prep only** —
durable lake analytics live in sibling **`book-job-data`** (ingest capture
CSVs → Bronze `job.v1` → API `:8109`). Do not write Solo Empire SQLite or
another app DB from here.

---

## Architecture (Hexagonal)

```
book-scraping/
│
├── core/                       # Domain layer — zero external dependencies
│   ├── models.py               # ScrapedItem, JobListing, ProductListing, ScrapeJob...
│   ├── ports.py                # ScraperPort, ExporterPort, StoragePort, SchedulerPort
│   ├── use_cases.py            # ScrapeUseCase (pipeline), SearchUseCase (MCP)
│   └── pipeline/               # Data cleaning + deduplication
│       ├── cleaner.py          # Thai-specific normalization, contact extraction
│       └── deduplicator.py     # Content-hash dedup with persistent DB
│
├── adapters/                   # Implementation layer
│   ├── inbound/                # Drivers — things that call INTO the core
│   │   └── scheduler_adapter.py    # YAML-driven job scheduler + CLI
│   └── outbound/               # Driven — things the core calls OUT to
│       ├── engine_adapter.py   # Routes to correct engine by job.engine
│       ├── exporter_adapter.py # JSON, CSV, SQLite, Parquet export
│       ├── storage_adapter.py  # File-based storage by category
│       ├── engines/            # Actual scraping engines
│       │   ├── base.py         # BaseScraper (rate limit, cache, retry)
│       │   ├── httpx_bs4.py    # Static HTML — fast, lightweight
│       │   ├── playwright_engine.py  # JS-rendered SPAs
│       │   ├── selenium_engine.py    # Complex interactions (login, scroll)
│       │   ├── scrapy_engine.py      # Large-scale crawls (10K+ pages)
│       │   └── rss_engine.py         # RSS/Atom feeds
│       └── utils/              # Shared engine utilities
│           ├── user_agents.py      # UA pool rotation
│           ├── proxy_rotator.py    # Proxy pool + health check
│           ├── anti_detect.py      # Fingerprint randomization
│           ├── validators.py       # Data schema validation
│           └── exporters.py        # Legacy export helpers
│
├── categories/                 # Website-specific scrapers (inherit from engines)
│   ├── jobs/jobsdb_scraper.py      # Jobsdb Thailand
│   ├── ecommerce/shopee_scraper.py # Shopee Thailand
│   └── restaurants/wongnai_scraper.py  # Wongnai restaurants
│
├── mcp_server/                 # MCP data-as-a-service (inbound adapter)
│   └── server.py               # Uses SearchUseCase → StorageAdapter
│
├── config/
│   └── jobs.yaml               # 24 configured jobs; 19 enabled in this checkout
│
├── templates/                  # Copy-paste templates for new scrapers
│   ├── new_httpx_scraper.py
│   └── new_playwright_scraper.py
│
├── main.py                     # CLI entry point (composition root)
├── requirements.txt
└── data/                       # Scraped data (gitignored)
    ├── jobs/items.json
    ├── products/items.json
    ├── businesses/items.json
    ├── news/items.json
    └── ...
```

### Data Flow

```
CLI/Scheduler (inbound)
    → ScrapeUseCase (core)
        → EngineAdapter.scrape()     [outbound: engines/]
        → DataCleaner.clean()        [core: pipeline/]
        → Deduplicator.deduplicate() [core: pipeline/]
        → ExporterAdapter.export()   [outbound: exporters]
        → StorageAdapter.save()      [outbound: storage]
```

---

## Scheduled Jobs

Jobs are defined in `config/jobs.yaml`. The installed local cron invokes
`main.py run` every five minutes, so only jobs due at that moment are run.
The scheduler state is written to `data/schedule_state.json`.

| Job | Category | Engine | Schedule | Status |
|-----|----------|--------|----------|--------|
| `github_trending` | discovery | httpx | Daily 10:00 AM | enabled |
| `hackernews` | discovery | httpx | Daily 9:00 AM | enabled |
| `devto_articles` | discovery | httpx | Daily 10:00 AM | enabled |
| `producthunt_top` | discovery | httpx | Daily 11:00 AM | enabled |
| `ai_tools` | ai | Futurepedia HTML | Daily 11:00 AM | migrated to book-ai-tools-data |
| `property_listings` | property | firecrawl | Daily 9:00 AM | enabled |
| `notebookspec_tech` | news | RSS | Every 6 hours | migrated to book-news-scraping |
| `ddproperty_condos` | property | httpx + Thai `__NEXT_DATA__` | Daily 8:00 AM | blocked: httpx Cloudflare 403 |
| `crypto_prices` | finance | CoinGecko API | Every 4 hours | migrated to book-crypto-data |
| `exchange_rates` | finance | Frankfurter API | Every 6 hours | migrated to book-fx-data |
| `stock_prices` | finance | Yahoo Finance chart API | Daily 8:00 AM | migrated to book-stock-data |
| `defi_yields` | finance | DefiLlama pools API | Daily 7:00 AM | migrated to book-defi-data |
| `kaidee_classifieds` | marketplace | Kaidee HTML | Every 6 hours | migrated to book-ecommerce-scraping |
| `wongnai_bangkok` | businesses | Wongnai HTML | Weekly | migrated to book-restaurant-scraping |
| `wongnai_upcountry` | businesses | Wongnai HTML | Weekly | migrated to book-restaurant-scraping |
| `matichon_news` | news | Matichon RSS | Every 4 hours | migrated to book-news-scraping |
| `thai_business_news` | news | Bangkok Post Business RSS | Every 2 hours | migrated to book-news-scraping |
| `thai_tech_news` | news | Blognone Atom | Every 2 hours | migrated to book-news-scraping |
| `seo_rankings` | marketing | httpx public pages | Daily 8:00 AM | migrated to book-seo-data |
| `job_postings` | jobs | firecrawl+httpx | Every 6 hours | enabled |
| `job_match_filter` | jobs | local | Every 6 hours, after capture | enabled |
| `scraper_dashboard` | operations | local | 8:15, 11:15, 20:15 | enabled |

Two entries remain blocked in the coverage registry: `flight_prices` and
`ddproperty_condos` still need a permitted, trustworthy live adapter. The
former cross-source `money_opportunities` lane was retired with the shared
opportunity synthesis; it is no longer scheduled or a collection target.
`ddproperty_condos` has a Thai `__NEXT_DATA__` parser and fixture but live
collection hits a Cloudflare JS challenge. `seo_rankings` is enabled as a
public-page provenance check (no SERP ranks on the free path). News RSS jobs
are migrated to `book-news-scraping` (`scripts/run_feeds.py`, cron every 2
hours). `notebookspec_tech` was enabled after a
dedicated RSS adapter returned 20 attributed canonical articles.
`wongnai_upcountry` is enabled after a three-page live HTML smoke returned 28
unique restaurants across Khon Kaen, Korat, and Pattaya with city attribution.
`ai_tools` is enabled
after a six-page Futurepedia HTML smoke returned 62 unique tools with category
and canonical URL attribution. `wongnai_bangkok` is enabled after a three-page
live HTML smoke returned 161 unique Bangkok-attributed restaurants.
`crypto_prices` is enabled after the CoinGecko API smoke returned 20 validated
rows. `exchange_rates` is enabled after a Frankfurter smoke returned 10
validated rates, and `stock_prices` is enabled after Yahoo Finance returned 9
validated ticker rows. `kaidee_classifieds` is enabled after a live HTML smoke
returned 8 priced canonical listings. Re-enable other sources only after a
focused smoke test produces a trustworthy contract-compliant result.
`matichon_news` is enabled after its RSS smoke returned 50 attributed canonical
articles. `thai_business_news` is enabled after its RSS smoke returned 10
attributed canonical business articles. `thai_tech_news` is enabled after its
Blognone RSS smoke returned 10 attributed canonical technology articles.
`defi_yields` is migrated to `book-defi-data` after a Firefox-UA live smoke
returned 20 validated Ethereum pools with a provider timestamp within the
24-hour freshness bound. The domain cron uses the same five-chain production
bounds as the previous local job.

### Multi-business source coverage

`config/source_coverage.yaml` is the coverage registry for the shared
acquisition platform. It maps every scheduler job to a business lane, source,
acquisition channel, output contract, implementation status, and restoration
priority. The preferred acquisition order is API, CLI, RSS, then scraping;
`hybrid` entries may combine an API with bounded HTML fallback.

```bash
python scripts/source_coverage.py --check
python scripts/source_coverage.py
python scripts/source_coverage.py --json
```

The validator fails if coverage drifts from `config/jobs.yaml`, an enabled
adapter module is missing, or a source has no contract/next action. This keeps
business coverage broad without making every downstream application scrape
independently.

The DDproperty adapter writes its collection-only snapshot to
`data/exported/ddproperty_condos.csv` and reuses the shared property parser;
it does not own matching, alerts, or downstream business decisions.

The crypto adapter writes the validated raw response to
`data/exported/crypto_prices_raw.json` and the capture projections to
`data/exported/crypto_prices.csv` and `data/exported/crypto_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-crypto-data`.

The FX adapter writes the validated Frankfurter response to
`data/exported/exchange_rates_raw.json` and the capture projections to
`data/exported/exchange_rates.csv` and `data/exported/exchange_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-fx-data`.

The stock adapter writes the validated Yahoo Finance chart responses to
`data/exported/stock_prices_raw.json` and the capture projections to
`data/exported/stock_prices.csv` and `data/exported/stock_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-finance-data`.

The Kaidee adapter writes the validated embedded page payload to
`data/exported/kaidee_classifieds_raw.json` and the capture projections to
`data/exported/kaidee_classifieds.csv` and
`data/exported/kaidee_classifieds_history.csv`. It is collection-only; durable
marketplace lake/API ownership remains with the downstream marketplace data
product.

The Matichon adapter writes the raw RSS response to
`data/exported/matichon_news_raw.xml` and the capture projections to
`data/exported/matichon_news.csv` and
`data/exported/matichon_news_history.csv`. It is collection-only; durable news
lake/API ownership remains with the downstream news data product.

The Bangkok Post Business adapter writes the raw RSS response to
`data/exported/thai_business_news_raw.xml` and the capture projections to
`data/exported/thai_business_news.csv` and
`data/exported/thai_business_news_history.csv`. It is collection-only; durable
business-news lake/API ownership remains with the downstream news data
product.

The Blognone adapter writes the raw Atom-compatible response to
`data/exported/thai_tech_news_raw.xml` and the capture projections to
`data/exported/thai_tech_news.csv` and
`data/exported/thai_tech_news_history.csv`. It is collection-only; durable
technology-news lake/API ownership remains with the downstream news data
product.

The Wongnai adapter writes bounded raw HTML pages to
`data/exported/wongnai_bangkok_raw.json` and the capture projections to
`data/exported/wongnai_bangkok.csv` and
`data/exported/wongnai_bangkok_history.csv`. It reads the embedded
`window._wn` state, validates canonical restaurant URLs, and filters every row
to Bangkok city attribution before writing collection-only output.

The same adapter writes the upcountry capture to
`data/exported/wongnai_upcountry_raw.json`,
`data/exported/wongnai_upcountry.csv`, and
`data/exported/wongnai_upcountry_history.csv`. The enabled upcountry job uses
three bounded pages and keeps only rows attributed to `khonkaen`, `korat`, or
`pattaya` (including Chon Buri city labels for Pattaya).

The AI tools adapter writes bounded Futurepedia HTML pages to
`data/exported/ai_tools_raw.json` and the capture projections to
`data/exported/ai_tools.csv` and `data/exported/ai_tools_history.csv`. It
validates canonical `/tool/<slug>` URLs and preserves category, rating, pricing,
description, and source attribution for collection-only discovery output.

The DeFi adapter now runs from `book-defi-data`. It writes the validated
DefiLlama response to `book-defi-data/data/exported/defi_yields_raw.json`
and the capture projections to `defi_yields.csv` and
`defi_yields_history.csv`. It uses a Firefox User-Agent, normalizes the
`Optimism` configuration alias to DefiLlama's `OP Mainnet`, requires finite
APY/TVL and unique pool IDs, and rejects stale provider responses.

### Data Freshness Strategy

| Data Type | Frequency | Reason |
|-----------|-----------|--------|
| Discovery feeds | Daily | Trending and time-sensitive sources |
| Jobs | Every 6h | New postings expire quickly |
| Job matching | Daily | Refresh scored opportunities |
| Property | Daily | New listings appear frequently |
| Dashboard | 3 times daily | Keep operational view current |

---

## Quick Start

```bash
# Install dependencies in the repository venv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers (for JS-rendered pages)
playwright install chromium

# Copy config and edit
cp .env.example .env

# Run all due jobs now
python main.py run

# Run a specific configured job
python main.py run job_postings

# Install or inspect the five-minute local cron
bash setup_cron.sh install
bash setup_cron.sh status

# Check schedule status
python main.py status

# Run the direct job capture/matching path
python scripts/scrape_job_postings.py
python scripts/filter_job_matches.py

# Run MCP server
python -m mcp_server.server
```

### Collection health

The collection path is the authoritative default health mode. It checks the
four core artifacts and does not require optional AI enrichment or outbound
notifications:

```bash
python scripts/pipeline_runner.py --health
python scripts/pipeline_health_monitor.py
```

The cron entry runs `pipeline_health_monitor.py` after each collection run and
uses `flock` to prevent overlapping runs. Use `--send-telegram` only when an
operator has explicitly approved an external notification.

---

## Engine Decision Tree

| Engine | Best For | Speed | Complexity |
|--------|----------|-------|------------|
| **RSS/Atom** | Blogs, news, podcasts | Fastest | Lowest |
| **httpx + BS4** | Static HTML, APIs | Fast | Low |
| **Playwright** | SPAs, JS-rendered, screenshots | Medium | Medium |
| **Selenium** | Complex interactions, legacy sites | Slow | High |
| **Scrapy** | Large crawls (10K+ pages) | Fast | High |

1. Can you get data via RSS/API? → `rss`
2. Is the HTML in source (no JS needed)? → `httpx`
3. Does the page need JS to render? → `playwright`
4. Does the page need login/click/scroll? → `playwright` or `selenium`
5. Need to crawl 10,000+ pages? → `scrapy`

---

## MCP Data-as-a-Service

The `mcp_server/` exposes scraped data as MCP tools via `SearchUseCase`:

| Tool | Description | Data Source |
|------|-------------|-------------|
| `search_jobs` | Search jobs by keyword, location | jobs/ scrapers |
| `search_businesses` | Find businesses by category, area | directories/ scrapers |
| `get_product_prices` | Compare prices across platforms | ecommerce/ scrapers |
| `get_news` | Latest news by topic | news/ scrapers |

### Pricing Model

| Tier | Requests/month | Price | Target |
|------|---------------|-------|--------|
| Free | 100 | ฿0 | Test & demo |
| Starter | 1,000 | ฿499/mo | SMEs, freelancers |
| Pro | 10,000 | ฿2,999/mo | Agencies, startups |
| Enterprise | Unlimited | Custom | Large companies |

---

## Legal Guidelines

### OK to Scrape
- Public business directories (Yellow Pages, Google Maps listings)
- Job boards (public listings)
- RSS feeds
- Public real estate listings
- Product prices (for comparison)

### Be Careful
- Social media (check ToS, rate limit heavily)
- News sites (check robots.txt)
- Review sites (don't republish reviews verbatim)

### Don't Scrape
- Login-required content without permission
- Personal data (PDPA compliance)
- Content behind paywalls
- Anything that violates robots.txt + ToS

---

## Dependencies

See `requirements.txt`. Key packages:
- `httpx` — async HTTP client
- `beautifulsoup4` + `lxml` — HTML parsing
- `playwright` — browser automation
- `selenium` — legacy browser automation
- `scrapy` — large-scale crawling
- `feedparser` — RSS/Atom parsing
- `pydantic` — data validation
- `mcp` — MCP server framework
- `apscheduler` — job scheduling

---

## Job Application Automation Pipeline

> **Safety (2026-08):** Live send/apply is **disabled by default**. See [`SAFETY.md`](./SAFETY.md).
> Paths resolve to this repo’s `data/` directory (not the old monorepo `domains/book-dev/book-scraping` layout).
> `auto_apply.py` only **prepares** drafts (`status=prepared`); it does not submit applications.
> ATS/email live paths require explicit unlock env vars in addition to `--apply` / `--send`.

The job scraping pipeline automates discovery, matching, and application tracking for remote dev jobs.

The targeting policy also has a separate bridge-to-hire lane for
`Contract-to-hire`, `Paid trial`, `Apprenticeship`, `Fellowship`, `Internship`,
and `Volunteer` signals.  A bounded volunteer or open-source contribution is
useful for portfolio, maintainer references, and network—not proof of a job
offer—so it remains `VERIFY`/review-only.  Paid bridge programs can reach
`PASS` only after a human records compensation, scope/duration, mentor,
conversion/reference path, Thailand eligibility, compatible hours, and a
contractor boundary.  Upfront fees, income-share entry, and indefinite unpaid
production work are rejected.

### Data Flow

```
scrape_job_postings.py
    → job_postings.csv (latest snapshot, all sources)
    → config/job_targeting.yaml (contract-first + bridge PASS / VERIFY / REJECT)
    → matched_jobs.csv (PASS first, VERIFY review-only, REJECT excluded)
    → job_descriptions.csv (top matched descriptions, optional enrichment)
    → apply_tracker.csv (via auto_seed_tracker.py, discovered/prepared statuses)
    → resume_variants/ (local application-prep variants)
```

### Supported Job Boards

| Source | Method | Company Extraction |
|--------|--------|-------------------|
| WeWorkRemotely | HTML scrape | Regex + URL slug fallback |
| RemoteOK | API | API field |
| Remotive | API | API field |
| Himalayas | API | API field |
| Jobicy | API | API field |
| Landing.jobs | API | API field + URL slug fallback |
| Arc.dev | API | API field + URL slug fallback |
| Dice | HTML scrape | Regex + context analysis |
| Wellfound | API | API field |
| LinkedIn | Scrape | HTML parsing |

### Company Extraction Strategy

For sources where API/HTML parsing fails, the pipeline uses URL slug extraction as a fallback:

```python
# Example: weworkremotely.com/remote-jobs/proxify-ab-senior-fullstack-developer
# → Extracts "Proxify Ab" by splitting slug and stopping at job keywords
```

The `_extract_company_from_url()` function handles source-specific URL patterns and uses keyword-boundary detection to isolate company names from job titles.

### Data Quality & Backfill

The pipeline includes data quality recovery mechanisms:

- **Backfill from source files**: Missing company/title values are recovered from `matched_jobs.csv` and `job_postings.csv` by URL lookup
- **URL-based extraction**: For rows not in source files, company names are extracted from URL patterns
- **Status-aware recovery**: Rows with `notified` or `applying` status are prioritized for recovery

Latest verified runtime snapshot (2026-08-24; data is gitignored and will
change on the next run):
- `job_postings.csv`: 1,647 rows
- `matched_jobs.csv`: 118 rows
- `apply_tracker.csv`: 106 rows, all seeded as `discovered` (no submission)
- `job_descriptions.csv`: 10 rows
- `resume_variants/`: 5 configured variants

### Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scrape_job_postings.py` | Main scraper — fetches from 10+ job boards |
| `scrape_job_descriptions.py` | Fetches descriptions for top matched jobs |
| `filter_job_matches.py` | Scores and filters the latest postings |
| `auto_seed_tracker.py` | Seeds `apply_tracker.csv` from `matched_jobs.csv` |
| `multi_resume_manager.py` | Initializes and lists application-prep variants |
| `pipeline_runner.py` | Runs collection-mode health and optional pipeline steps |
| `pipeline_health_monitor.py` | Checks disk, scheduler, data freshness, and optional integrations |
| `send_application_emails.py` | Sends application emails to recruiters |
| `auto_send_email.py` | Automated email sending with follow-ups |
| `find_recruiter_emails.py` | Discovers recruiter contacts from company data |

The scheduled search uses international remote sources plus Fastwork,
PeoplePerHour, and Toptal. It includes contract-to-hire, paid-trial,
apprenticeship, fellowship, and volunteer discovery keywords without adding a
second scheduler or auto-application path. Generic JobThai/JobBKK full-time
collection is not scheduled. Downstream promotion and draft preparation accept `PASS` only;
live email/ATS submission additionally requires a human-recorded
`application_readiness=APPROVED` and the independent live-send unlock gates.
Each scheduled match refresh also seeds new `PASS` rows into the local tracker
as `discovered`; it does not notify or submit them.

### Running the Pipeline

```bash
# From this repo root, with project venv activated
python scripts/scrape_job_postings.py
python scripts/filter_job_matches.py
python scripts/scrape_job_descriptions.py --top 10
python scripts/auto_seed_tracker.py --min-score 5
python scripts/multi_resume_manager.py --init
python scripts/pipeline_runner.py --health

# Prepare drafts only (does not submit)
python scripts/auto_apply.py --dry-run

# Application emails — dry-run by default; live send is gated (see SAFETY.md)
python scripts/send_application_emails.py
```

---

## Related

- **Lead gen scrapers:** `domains/marketing/growth/book-sales/scripts/` (initial scrapers, being migrated)
- **Facebook scraper:** `domains/product/engineering/book-dev/book-client/scraping-facebook/` (client work)
- **Novel scraper:** `domains/product/engineering/book-dev/book-products/bookreading/ai-service/scrapers.py`
- **Scraping strategy:** `domains/marketing/growth/book-sales/web-scraping-strategy.md`
