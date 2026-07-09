# Book Scraping — Multi-Engine Web Data Platform

Hexagonal-architecture scraping platform with 5 engines, scheduled jobs, and MCP data-as-a-service.

**Location:** `domains/product/engineering/book-dev/book-scraping/`  
**Architecture:** Hexagonal (Ports & Adapters)  
**Engines:** httpx+BS4, Playwright, Selenium, Scrapy, RSS  
**Categories:** Jobs, E-commerce, Restaurants, Directories, News, Property  
**Output:** MCP server → sell data as a service to Thai SMEs

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
│   └── jobs.yaml               # 10 scheduled jobs with cron expressions
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

Jobs are defined in `config/jobs.yaml` and run via `main.py loop`:

| Job | Category | Engine | Schedule | Status |
|-----|----------|--------|----------|--------|
| `jobsdb_thai` | jobs | httpx | Daily 9:00 AM | enabled |
| `jobsdb_remote` | jobs | httpx | Daily 9:00 AM | enabled |
| `shopee_tech` | ecommerce | playwright | Every 6 hours | enabled |
| `wongnai_bangkok` | restaurants | playwright | Weekly Sunday | enabled |
| `thai_business_news` | news | rss | Every 2 hours | enabled |
| `thai_tech_news` | news | rss | Every 2 hours | enabled |
| `ddproperty_condos` | property | httpx | Daily 8:00 AM | disabled |
| `thai_yellow_pages` | directories | httpx | Weekly Monday | disabled |

### Data Freshness Strategy

| Data Type | Frequency | Reason |
|-----------|-----------|--------|
| Jobs | Daily | New postings every day |
| Products | Every 6h | Prices change frequently |
| Businesses | Weekly | Stable data, occasional updates |
| News | Every 2h | Time-sensitive content |
| Property | Daily | New listings appear daily |

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for JS-rendered pages)
playwright install chromium

# Copy config and edit
cp .env.example .env

# Run all due jobs now
python main.py run

# Run a specific job
python main.py run jobsdb_thai

# Run continuous scheduler loop
python main.py loop

# Check schedule status
python main.py status

# Enable/disable a job
python main.py enable ddproperty_condos
python main.py disable shopee_tech

# Run a category scraper directly
python -m categories.jobs.jobsdb_scraper
python -m categories.ecommerce.shopee_scraper

# Run MCP server
python -m mcp_server.server
```

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

The job scraping pipeline automates discovery, matching, and application tracking for remote dev jobs.

### Data Flow

```
scrape_job_postings.py
    → job_postings.csv (latest snapshot, all sources)
    → matched_jobs.csv (scored against skills, deduplicated)
    → apply_tracker.csv (via auto_seed_tracker.py, status-tracked)
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

Current data quality (as of 2026-07-05):
- `apply_tracker.csv`: 629 rows, 93 missing company (14.8%), 151 missing title (24.0%)
- `matched_jobs.csv`: 1104 rows, 219 missing company (19.8%)
- `job_postings.csv`: 1438 rows, 305 missing company (21.2%)

### Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scrape_job_postings.py` | Main scraper — fetches from 10+ job boards |
| `auto_seed_tracker.py` | Seeds `apply_tracker.csv` from `matched_jobs.csv` |
| `send_application_emails.py` | Sends application emails to recruiters |
| `auto_send_email.py` | Automated email sending with follow-ups |
| `find_recruiter_emails.py` | Discovers recruiter contacts from company data |

### Running the Pipeline

```bash
# Scrape fresh job postings
python3 domains/product/engineering/book-dev/book-scraping/scripts/scrape_job_postings.py

# Seed tracker with new matched jobs
python3 domains/product/engineering/book-dev/book-scraping/scripts/auto_seed_tracker.py

# Find recruiter emails for discovered jobs
python3 domains/product/engineering/book-dev/book-scraping/scripts/find_recruiter_emails.py

# Send application emails
python3 domains/product/engineering/book-dev/book-scraping/scripts/send_application_emails.py
```

---

## Related

- **Lead gen scrapers:** `domains/marketing/growth/book-sales/scripts/` (initial scrapers, being migrated)
- **Facebook scraper:** `domains/product/engineering/book-dev/book-client/scraping-facebook/` (client work)
- **Novel scraper:** `domains/product/engineering/book-dev/book-products/bookreading/ai-service/scrapers.py`
- **Scraping strategy:** `domains/marketing/growth/book-sales/web-scraping-strategy.md`
