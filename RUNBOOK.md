# Release / Runbook (BD-039) — book-job-scraping

**Date:** 2026-09-14
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
| `BRAVE_SEARCH_API_KEY` | No while social job is disabled | Required only after an approved Brave Search plan is provisioned |
| `BRAVE_SEARCH_STORAGE_APPROVED` | No while social job is disabled | Keep `0`; set `1` only after storage-rights, terms/PDPA, retention, and human-review approval |
| `PROPERTY_SOCIAL_RETENTION_UNTIL` | No while social job is disabled | Set the approved deletion deadline before a governed capture |
| `PROPERTY_SOCIAL_TERMS_BASIS_REF` | No while social job is disabled | Internal decision/terms reference; never store raw legal text in the capture |
| `TGCONDO_CONTACT_STORAGE_APPROVED` | No for RSS-only capture | Keep `0`; set `1` only after public-contact storage and terms/PDPA review |
| `TGCONDO_RETENTION_UNTIL` | No for RSS-only capture | Required with contact opt-in; approved deletion deadline |
| `TGCONDO_TERMS_BASIS_REF` | No for RSS-only capture | Required with contact opt-in; internal source/terms decision reference |

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

For `property_social_leads`, the collector uses only Brave's official Search
API and public-index metadata for Facebook, Instagram, TikTok, and LINE. It
does not authenticate to a social account, crawl a private page, scrape the
search UI, or send outreach. Keep the job disabled until the subscribed plan
explicitly permits result storage and the terms/PDPA purpose, retention,
deletion, and human-review owner are recorded:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_property_social_leads.py' -v
mkdir -p /tmp/property-social-fixture
.venv/bin/python scripts/scrape_property_social.py \
  --fixture tests/fixtures/property_social_results.json \
  --limit 20 --output-dir /tmp/property-social-fixture
.venv/bin/python scripts/check_property_social_capture.py \
  /tmp/property-social-fixture/property_social_leads.csv --json
BRAVE_SEARCH_STORAGE_APPROVED=1 .venv/bin/python scripts/scrape_property_social.py \
  --platform facebook --limit 5 --dry-run
```

The `--fixture` run is a synthetic, offline smoke test for extraction,
deduplication, review defaults, and the capture validator. It never contacts a
social platform or search API and cannot authorize enabling the scheduled
job. Use the Brave command only after the storage-rights and terms/PDPA gates
above are recorded.

For owner/co-agent research without a paid search API, use the manual browser
export lane.  Load `chrome-extension/` as an unpacked extension, open a public
listing or public search page yourself, click **Capture public property lead**,
review the visible text, and export the CSV.  The extension only reads the
active rendered tab; it does not log in, follow private links, read cookies, or
send data to a server.  Do not use it for private groups or to bypass a source
permission gate.

Normalize and filter that export locally:

```bash
.venv/bin/python scripts/import_property_leads.py \
  --input ~/Downloads/property_owner_coagent_export.csv \
  --output-dir /tmp/property-owner-coagent
```

The importer accepts CSV or JSON, allows only HTTPS hosts recorded in its
source allowlist (`zmyhome.com`, `meezub.com`, `ennxo.com`,
`livinginsider.com`, the configured property portals, and public social URLs),
strips tracking parameters, deduplicates by canonical URL and listing
fingerprint, and quarantines invalid or non-owner/co-agent rows.  It writes a
property.v1 snapshot, history, a redacted quarantine CSV, a checksum manifest,
and a local raw-input copy.  Every accepted row remains pending human review;
the importer never contacts a seller or co-agent.
DDproperty is intentionally excluded because its current source terms do not
permit automated scan/copy/index; keep that lane blocked unless a separate
permission decision changes.

For Facebook Groups, use the free rendered-tab bridge in the extension.  Open
the Group yourself, click **Capture Facebook Group posts**, confirm the
visibility, select posts with a permalink, and export **Facebook Group CSV**.
The content script reads only `[role="article"]` nodes already rendered in the
active tab; it does not scroll, call an API, read cookies, or follow links.
Scroll another page manually and press **Capture next rendered page**.  Do not use this lane to enter
a private Group or bypass an access control you are not authorised to use.

Use **Export current capture CSV** when you want the current draft immediately
without adding its rows to the saved-posts store.  Use **Save selected group
posts** followed by **Export Facebook Group CSV** for the durable local saved
set.  The current-capture export is named `facebook_group_current_capture.csv`.

Normalise and validate the export locally:

```bash
.venv/bin/python scripts/import_facebook_group_posts.py \
  --input ~/Downloads/facebook_group_posts_export.csv \
  --output-dir /tmp/facebook-group
.venv/bin/python scripts/check_facebook_group_capture.py \
  /tmp/facebook-group/facebook_group_posts.csv --json
```

After checking each source tab, record a redacted review decision.  This does
not approve outreach:

```bash
.venv/bin/python scripts/review_facebook_group_posts.py \
  --input /tmp/facebook-group/facebook_group_posts.csv \
  --all-pending --decision approved --reviewer-id owner-1 \
  --output /tmp/facebook-group/facebook_group_posts_reviewed.csv
```

Chrome may close the extension popup when you return to the tab to scroll.  The
extension therefore keeps a bounded local draft (up to 500 posts, expiring
after 24 hours); reopen it and press **Capture next rendered page** after each
viewport.  Captures merge by canonical `post_url`; duplicate posts are retained
once and the more complete visible copy is kept.  Use **Clear capture draft** to
start over.  The popup never scrolls, opens a post, calls an API, or reads
cookies.

Run this synthetic smoke before a real export.  It is offline and uses only
fake fixture values:

```bash
.venv/bin/python scripts/import_facebook_group_posts.py \
  --input tests/fixtures/facebook_group_posts_export.csv \
  --output-dir /tmp/facebook-group-fixture
.venv/bin/python scripts/check_facebook_group_capture.py \
  /tmp/facebook-group-fixture/facebook_group_posts.csv --json
```

The validator's JSON `quality` block shows visibility, complete/incomplete text,
duplicate URL/ID, candidate, and pending-review counts.  Add
`--require-complete` for a strict downstream gate; it fails on any row marked
`text_complete=false`.

`facebook.group-post.v1` keeps the Group/post permalink, visible author/time,
bounded text, visibility label, completeness flag, contact evidence, and
hash-only quarantine.  Public rows are retained for search and review; use
`--candidates-only` to discard posts without explicit owner/co-agent wording.
Private or unknown rows fail closed unless the operator supplies the matching
`--allow-private`/`--allow-unknown` gate plus `--retention-until` and
`--terms-basis-ref`.  No row can advance to outreach from this importer.

For a background run without the extension, use the dedicated Playwright
profile runner.  Keep the profile outside the repository; it is an
authentication boundary even though the script never reads or exports cookie
values.  Seed it manually once, then run a bounded headless capture:

On Debian/Ubuntu, install `python3.14-venv` if `python3 -m venv` says that
`ensurepip` is unavailable, then recreate `.venv` with
`python3 -m venv --clear .venv`.  The runner itself only needs Playwright;
install the full requirements file when other scrapers need it.

```bash
sudo apt update
sudo apt install python3.14-venv
python3 -m venv --clear .venv
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install-deps chromium
.venv/bin/playwright install chromium
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --profile-dir ~/.local/share/solo-empire/facebook-playwright \
  --login-only --headed
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --groups-file /tmp/facebook-groups.txt \
  --profile-dir ~/.local/share/solo-empire/facebook-playwright \
  --output /tmp/facebook-group-background.csv \
  --rounds 3 --pause-ms 1500 --visibility public
```

Run the offline browser smoke before pointing the runner at a real Group.  The
fixture is served locally by Playwright and all non-document requests are
aborted, so this command does not contact Facebook:

```bash
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --group-url https://facebook.com/groups/demo \
  --profile-dir /tmp/facebook-background-fixture-profile \
  --fixture tests/fixtures/facebook_group_background.html \
  --output /tmp/facebook-group-background-fixture.csv \
  --rounds 1 --visibility public
```

If a user-level timer is appropriate after review, copy and edit the example
units under [`ops/systemd/`](ops/systemd/).  They are intentionally not
installed by `setup_cron.sh` or by this runner.

The runner is not installed by `setup_cron.sh`; schedule it only after a
separate source/terms decision.  It limits the run to 20 Groups, 10 rounds,
500 posts, and a 500–10000 ms pause.  It skips pages whose Group identity does
not match the requested URL, never follows post links, and exits without an
output when no permitted posts were captured.  Use `--allow-unknown` only
after checking the Group yourself, or use `--visibility public` when every
listed Group has been checked as public.  Private captures require the same
retention and terms-basis flags as the importer.

Record a human decision after opening and checking each selected source page.
Rows are numbered from 1 after the CSV header.  The command refuses a second
decision on a reviewed row and leaves outreach locked:

```bash
.venv/bin/python scripts/review_property_leads.py \
  --input /tmp/property-owner-coagent/property_owner_coagent_leads.csv \
  --rows 1,3-4 --decision approved --reviewer-id owner-1 \
  --output /tmp/property-owner-coagent/property_owner_coagent_leads_reviewed.csv
.venv/bin/python scripts/check_property_capture.py \
  /tmp/property-owner-coagent/property_owner_coagent_leads_reviewed.csv --json
```

`--list-pending` prints only redacted counts and row numbers.  Use
`--all-pending` when the same decision applies to every remaining row.  Review
events append to `property_owner_coagent_review_history.csv` with the reviewer,
timestamp, and URL/input hashes; contact values are excluded.  `approved` does
not set `approved_to_contact`; any outreach requires a separate explicit
approval and a compatible source-terms/PDPA decision.

Run the synthetic, no-network check before using a real export:

```bash
.venv/bin/python -m unittest tests/test_property_owner_coagent_import.py -v
.venv/bin/python scripts/import_property_leads.py \
  --input tests/fixtures/property_owner_coagent_export.csv \
  --output-dir /tmp/property-owner-coagent-fixture
.venv/bin/python scripts/check_property_capture.py \
  /tmp/property-owner-coagent-fixture/property_owner_coagent_leads.csv --json
```

For `tgcondo_condo_rent`, use the public RSS feed for a live, no-key listing
sample. The adapter stores the bounded RSS response and CSV projection, keeps
the scheduler disabled pending source-terms/retention review, and does not
infer an owner or co-agent from a listing title:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_tgcondo_rss.py' -v
mkdir -p /tmp/tgcondo-live-sample
.venv/bin/python scripts/scrape_tgcondo_rss.py \
  --limit 5 --output-dir /tmp/tgcondo-live-sample
```

Contact enrichment is opt-in, capped at five public listing pages, and held
unless `TGCONDO_CONTACT_STORAGE_APPROVED=1` plus the approved retention and
terms-reference variables are present. It reads visible agent-card fields and
never submits TG Condo's contact form or sends outreach. Review every contact
row before any follow-up; rows start with `review_decision=pending` and
`outreach_status=not_contacted`.

Use the smoke only after the storage-rights approval. Review every returned
row for an allowlisted HTTPS source URL, correct platform, explicit contact
evidence, and `contact_role`/`co_agent_status` agreement. For a persisted
capture, run the redacted validator before lake ingest:

```bash
.venv/bin/python scripts/check_property_social_capture.py \
  data/exported/property_social_leads.csv --json --require-governance
```

Do not enable the schedule from a count-only result; require a human sign-off
on the sampled rows, record `review_decision`, `reviewer_id`, and
`reviewed_at`, then change `config/jobs.yaml` and the coverage registry
together. `outreach_status` may become `approved_to_contact` or `contacted`
only after `review_decision=approved`. Set the gate back to `0` and leave the
job disabled if the API fails, returns malformed data, or the sample contains
a non-public/private source.

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
