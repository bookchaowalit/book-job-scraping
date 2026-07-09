"""
Data quality report generator — scans exported data and produces summary stats.
Run: python quality_report.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent / "data" / "exported"
REPORT_PATH = Path(__file__).parent / "data" / "quality_report.json"

# Map exported files to job categories
FILE_JOB_MAP = {
    "thai_news.json": "thai_business_news",
    "thai_news.csv": "thai_business_news",
    "jobsdb_jobs.json": "jobsdb_thai",
    "jobsdb_jobs.csv": "jobsdb_thai",
    "wongnai_restaurants.json": "wongnai_bangkok",
    "wongnai_restaurants.csv": "wongnai_bangkok",
    "shopee_products.json": "shopee_tech",
    "shopee_products.csv": "shopee_tech",
    "lazada_products.json": "lazada_tech",
    "lazada_products.csv": "lazada_tech",
    "ddproperty_listings.json": "ddproperty_condos",
    "ddproperty_listings.csv": "ddproperty_condos",
    "yellow_pages.json": "thai_yellow_pages",
    "yellow_pages.csv": "thai_yellow_pages",
}


def analyze_file(filepath: Path) -> dict:
    """Analyze a single JSON data file."""
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"error": "unreadable", "items": 0}

    if not isinstance(data, list):
        return {"error": "not a list", "items": 0}

    items = len(data)
    if items == 0:
        return {"items": 0, "fields": [], "empty_fields": []}

    # Analyze fields
    all_fields = set()
    empty_counts = {}
    for item in data:
        if isinstance(item, dict):
            for k, v in item.items():
                all_fields.add(k)
                if not v or v == "" or v == [] or v is None:
                    empty_counts[k] = empty_counts.get(k, 0) + 1

    # Find fields that are mostly empty (>80%)
    mostly_empty = [
        f for f, count in empty_counts.items() if count > items * 0.8
    ]

    # Check for scraped_at timestamps
    has_timestamp = "scraped_at" in all_fields
    timestamps = []
    if has_timestamp:
        for item in data:
            ts = item.get("scraped_at", "")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts))
                except ValueError:
                    pass

    freshness = {}
    if timestamps:
        oldest = min(timestamps)
        newest = max(timestamps)
        freshness = {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "age_hours": round((datetime.now() - newest).total_seconds() / 3600, 1),
        }

    return {
        "items": items,
        "fields": sorted(all_fields),
        "mostly_empty_fields": mostly_empty,
        "freshness": freshness,
        "file_size_kb": round(filepath.stat().st_size / 1024, 1),
    }


def generate_report() -> dict:
    """Generate full quality report across all exported data."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "categories": {},
        "summary": {
            "total_items": 0,
            "total_categories": 0,
            "files_analyzed": 0,
        },
    }

    if not DATA_DIR.exists():
        report["error"] = "No data/exported directory found"
        return report

    json_files = sorted(DATA_DIR.glob("*.json"))

    for filepath in json_files:
        job_name = FILE_JOB_MAP.get(filepath.name, filepath.stem)
        analysis = analyze_file(filepath)
        analysis["source_file"] = filepath.name

        if job_name not in report["categories"]:
            report["categories"][job_name] = []
        report["categories"][job_name].append(analysis)

        report["summary"]["total_items"] += analysis.get("items", 0)
        report["summary"]["files_analyzed"] += 1

    report["summary"]["total_categories"] = len(report["categories"])

    return report


def print_report(report: dict):
    """Pretty-print the quality report."""
    print("\n" + "=" * 70)
    print("  DATA QUALITY REPORT")
    print(f"  Generated: {report['generated_at'][:19]}")
    print("=" * 70)

    summary = report["summary"]
    print(f"\n  Total items:    {summary['total_items']:,}")
    print(f"  Categories:     {summary['total_categories']}")
    print(f"  Files analyzed: {summary['files_analyzed']}")

    print(f"\n{'─' * 70}")
    print(f"  {'Category':<25} {'Items':>8} {'Size':>8} {'Freshness':>12}")
    print(f"{'─' * 70}")

    for cat, files in sorted(report["categories"].items()):
        for f in files:
            items = f.get("items", 0)
            size = f"{f.get('file_size_kb', 0):.0f}KB"
            freshness = f.get("freshness", {})
            age = freshness.get("age_hours", "?")
            age_str = f"{age}h ago" if isinstance(age, (int, float)) else "n/a"
            print(f"  {cat:<25} {items:>8,} {size:>8} {age_str:>12}")

            if f.get("mostly_empty_fields"):
                empty = ", ".join(f["mostly_empty_fields"][:3])
                print(f"    ⚠ mostly empty: {empty}")

    print(f"{'─' * 70}\n")


if __name__ == "__main__":
    report = generate_report()
    print_report(report)

    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved → {REPORT_PATH}")
