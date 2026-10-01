"""Offline tests for core use cases (fake ports) and the file StorageAdapter."""
import asyncio
import json

import pytest

from adapters.outbound.storage_adapter import StorageAdapter, _as_number
from core.models import JobListing, NewsArticle, ProductListing, ScrapedItem, ScrapeJob
from core.use_cases import ScrapeUseCase, SearchUseCase


class FakeScraper:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    async def scrape(self, job):
        if self.error:
            raise self.error
        return list(self.items)


class FakeExporter:
    def __init__(self):
        self.calls = []

    def export(self, items, format, filename):
        self.calls.append((format, filename, len(items)))
        return f"/out/{filename}"


class FakeStorage:
    def __init__(self, collections=None):
        self.saved = []
        self.collections = collections or {}
        self.loads = []

    def save(self, items, collection):
        self.saved.append((collection, list(items)))
        return len(items)

    def load(self, collection, filters=None):
        self.loads.append((collection, filters))
        return list(self.collections.get(collection, []))


def job(name="jobsdb", category="jobs"):
    return ScrapeJob(name=name, category=category, engine="httpx", url="https://example.com", schedule="0 * * * *")


def run(use_case, scrape_job):
    return asyncio.run(use_case.execute(scrape_job))


class TestScrapeUseCase:
    def test_full_pipeline_cleans_dedups_exports_and_saves(self):
        items = [
            JobListing(url="https://a/1", title="  Data Engineer  ", description=" x "),
            JobListing(url="https://a/1", title="dup"),
            JobListing(url="", title="no url"),
            JobListing(url="", title="no url 2"),
        ]
        exporter, storage = FakeExporter(), FakeStorage()
        result = run(ScrapeUseCase(FakeScraper(items), exporter, storage), job())

        assert result.success is True
        assert (result.items_scraped, result.items_cleaned, result.items_new) == (4, 4, 3)
        assert result.exported_to == ["/out/jobsdb.json", "/out/jobsdb.csv"]
        assert [c[0] for c in exporter.calls] == ["json", "csv"]
        collection, saved = storage.saved[0]
        assert collection == "jobs"
        assert saved[0].title == "Data Engineer" and saved[0].description == "x"
        assert all(item.cleaned for item in saved)
        assert result.errors == []
        assert result.duration_seconds >= 0

    def test_no_items_is_unsuccessful_without_side_effects(self):
        exporter, storage = FakeExporter(), FakeStorage()
        result = run(ScrapeUseCase(FakeScraper([]), exporter, storage), job())
        assert result.success is False
        assert result.errors == ["No items scraped"]
        assert exporter.calls == [] and storage.saved == []

    def test_scraper_exception_is_captured_not_raised(self):
        result = run(ScrapeUseCase(FakeScraper(error=RuntimeError("boom")), FakeExporter(), FakeStorage()), job())
        assert result.success is False
        assert result.errors == ["Pipeline error: boom"]
        assert result.duration_seconds >= 0

    def test_storage_failure_marks_result_failed(self):
        class BrokenStorage(FakeStorage):
            def save(self, items, collection):
                raise OSError("disk full")

        result = run(
            ScrapeUseCase(FakeScraper([ScrapedItem(url="https://x")]), FakeExporter(), BrokenStorage()), job()
        )
        assert result.success is False
        assert result.errors == ["Pipeline error: disk full"]


class TestSearchUseCase:
    def test_filters_are_built_from_arguments(self):
        storage = FakeStorage({"jobs": [JobListing(title=str(i)) for i in range(5)]})
        search = SearchUseCase(storage)
        assert len(search.search_jobs(keyword="data", location="Bangkok", limit=2)) == 2
        assert storage.loads[-1] == ("jobs", {"title_contains": "data", "location_contains": "Bangkok"})
        search.search_businesses(category="cafe", area="Ari")
        assert storage.loads[-1] == ("businesses", {"category": "cafe", "area": "Ari"})

    def test_zero_max_price_is_a_filter_and_negative_limit_is_empty(self):
        storage = FakeStorage({"products": [ProductListing(name="a", price=10.0)]})
        search = SearchUseCase(storage)
        search.search_products(keyword="a", max_price=0)
        assert storage.loads[-1] == ("products", {"name_contains": "a", "price_lte": 0})
        assert search.search_products(limit=-1) == []


class TestStorageAdapter:
    def test_save_load_roundtrip_dedups_by_url(self, tmp_path):
        store = StorageAdapter(tmp_path)
        first = [JobListing(url="https://a/1", title="Data Engineer", salary="50,000"), JobListing(url="", title="x", salary="1")]
        assert store.save(first, "jobs") == 2
        assert store.save([JobListing(url="https://a/1", title="again", salary="1")], "jobs") == 0

        fresh = StorageAdapter(tmp_path)  # no cache: reads items.json
        loaded = fresh.load("jobs")
        assert [i.title for i in loaded] == ["Data Engineer", "x"]
        assert isinstance(loaded[0], JobListing)
        data = json.loads((tmp_path / "jobs" / "items.json").read_text(encoding="utf-8"))
        assert data[0]["url"] == "https://a/1"

    def test_load_returns_a_copy_of_the_cache(self, tmp_path):
        store = StorageAdapter(tmp_path)
        store.save([ScrapedItem(url="https://a")], "misc")
        store.load("misc").append(ScrapedItem(url="https://b"))
        assert [i.url for i in store.load("misc")] == ["https://a"]

    def test_filters_handle_string_prices_without_crashing(self, tmp_path):
        exported = tmp_path / "exported"
        exported.mkdir()
        (exported / "shopee_products.json").write_text(
            json.dumps(
                [
                    {"source": "shopee_product", "name": "Cheap", "price": "1,299"},
                    {"source": "shopee_product", "name": "Pricey", "price": 5000},
                    {"source": "shopee_product", "name": "Unknown", "price": "ติดต่อผู้ขาย"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        store = StorageAdapter(tmp_path)
        names = [i.name for i in store.load("ecommerce", {"price_lte": 2000})]
        assert names == ["Cheap"]
        assert [i.name for i in store.load("ecommerce", {"price_gte": 2000})] == ["Pricey"]
        assert [i.name for i in store.load("ecommerce", {"name_contains": "pri"})] == ["Pricey"]

    def test_news_records_become_news_articles(self, tmp_path):
        exported = tmp_path / "exported"
        exported.mkdir()
        (exported / "thai_news.json").write_text(
            json.dumps([{"source": "thai_news", "title": "ข่าว", "summary": "s", "published_date": "2026-09-30T08:00:00+07:00"}]),
            encoding="utf-8",
        )
        [item] = StorageAdapter(tmp_path).load("news")
        assert isinstance(item, NewsArticle)
        assert item.published_date == "2026-09-30T08:00:00+07:00"

    def test_exists_skips_corrupt_files(self, tmp_path):
        store = StorageAdapter(tmp_path)
        (tmp_path / "broken").mkdir()
        (tmp_path / "broken" / "items.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "odd").mkdir()
        (tmp_path / "odd" / "items.json").write_text('{"url": "https://a"}', encoding="utf-8")
        store.save([ScrapedItem(url="https://a")], "misc")
        assert store.exists("https://a") is True
        assert store.exists("https://missing") is False

    def test_missing_collection_is_empty(self, tmp_path):
        assert StorageAdapter(tmp_path).load("nothing") == []


@pytest.mark.parametrize(
    "value, expected",
    [(1299, 1299.0), ("1,299", 1299.0), ("฿1,299.50", 1299.5), ("-5", -5.0), ("n/a", None), (None, None), (True, None)],
)
def test_as_number(value, expected):
    assert _as_number(value) == expected
