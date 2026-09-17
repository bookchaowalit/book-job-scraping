#!/usr/bin/env python3
"""HTTP-scrape public Pantip topics for first-person property demand.

The default is a non-persisting dry run. The command only fetches Pantip's
public search/topic HTML, never opens a browser, follows profiles, logs in, or
contacts a person. Use ``--persist`` only after a human has supplied a valid
retention deadline and terms-basis reference.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from property.demand import (  # noqa: E402
    PANTIP_HOSTS,
    TOPIC_PATH_RE,
    canonical_topic_url,
    extract_topic_links,
    parse_topic,
    search_url,
)


DEFAULT_QUERIES = ("หาคอนโดเช่า", "หาบ้านเช่า", "หาซื้อคอนโด")
DEFAULT_OUTPUT = ROOT / "data" / "exported" / "property_demand.csv"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SoloEmpirePropertyResearch/1.0"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
REDIRECT_CODES = {301, 302, 303, 307, 308}
DEMAND_CSV_FIELDS = [
    "schema_version",
    "lead_id",
    "source_url",
    "source_platform",
    "source_channel",
    "source_access_method",
    "source_visibility",
    "title",
    "exact_demand_text",
    "demand_signal",
    "observed_at",
    "posted_at",
    "property_type",
    "location",
    "budget",
    "timing",
    "public_contact_path",
    "contact_permission",
    "confidence",
    "review_status",
    "next_action",
    "retention_until",
    "terms_basis_ref",
]
HANDOFF_REVIEW_STATUSES = {"call_ready", "permission_needed", "needs_more_evidence"}


class SourceBlocked(RuntimeError):
    """The source or its robots policy prevented a safe request."""


def sort_records_newest_first(records: list[dict]) -> list[dict]:
    """Order dated records newest-first and keep undated records at the end."""

    def sort_key(record: dict) -> tuple[int, datetime, str]:
        posted_at = str(record.get("posted_at") or "")
        if not posted_at:
            return (0, datetime.min.replace(tzinfo=timezone.utc), str(record.get("source_url") or ""))
        try:
            posted = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        except ValueError:
            return (0, datetime.min.replace(tzinfo=timezone.utc), str(record.get("source_url") or ""))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return (1, posted.astimezone(timezone.utc), str(record.get("source_url") or ""))

    return sorted(records, key=sort_key, reverse=True)


def _valid_fetch_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host not in PANTIP_HOSTS:
        raise ValueError("only HTTPS Pantip URLs are allowed")
    if parsed.path == "/search":
        return value
    if TOPIC_PATH_RE.match(parsed.path):
        return canonical_topic_url(value)
    raise ValueError("only Pantip search or topic URLs are allowed")


class PantipHttpClient:
    """Bounded HTTP client with robots, redirect, response-size, and pacing gates."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        delay: float = 2.0,
        respect_robots: bool = True,
    ) -> None:
        self.timeout = max(1.0, min(float(timeout), 60.0))
        self.delay = max(0.0, min(float(delay), 60.0))
        self.respect_robots = respect_robots
        self._last_request = 0.0
        self._robots: RobotFileParser | None = None
        self._client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "th-TH,th;q=0.9,en;q=0.7",
            },
            follow_redirects=False,
            timeout=self.timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _pace(self) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _load_robots(self) -> RobotFileParser:
        if self._robots is not None:
            return self._robots
        self._pace()
        try:
            response = self._client.get("https://pantip.com/robots.txt")
        except httpx.HTTPError as exc:
            raise SourceBlocked("robots_unavailable") from exc
        self._last_request = time.monotonic()
        if response.status_code == 404:
            parser = RobotFileParser()
            parser.parse([])
            self._robots = parser
            return parser
        if response.status_code != 200:
            raise SourceBlocked("robots_denied")
        parser = RobotFileParser()
        parser.set_url("https://pantip.com/robots.txt")
        parser.parse(response.text.splitlines())
        self._robots = parser
        return parser

    def get(self, url: str) -> str:
        current = _valid_fetch_url(url)
        for _ in range(2):
            if self.respect_robots and not self._load_robots().can_fetch(USER_AGENT, current):
                raise SourceBlocked("robots_disallowed")
            self._pace()
            try:
                response = self._client.get(current)
            except httpx.HTTPError as exc:
                raise SourceBlocked("http_request_failed") from exc
            self._last_request = time.monotonic()
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    raise SourceBlocked("redirect_without_location")
                current = _valid_fetch_url(urljoin(current, location))
                continue
            if response.status_code in {403, 429}:
                raise SourceBlocked(f"http_{response.status_code}")
            if response.status_code >= 400:
                raise SourceBlocked(f"http_{response.status_code}")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise SourceBlocked("response_too_large")
            return response.text
        raise SourceBlocked("too_many_redirects")


def collect(
    *,
    queries: list[str],
    urls: list[str],
    limit: int,
    timeout: float,
    delay: float,
    max_age_days: int | None,
    respect_robots: bool = True,
) -> dict:
    """Fetch search/topic pages and return demand records plus safe counters."""

    bounded_limit = max(1, min(int(limit), 100))
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    client = PantipHttpClient(timeout=timeout, delay=delay, respect_robots=respect_robots)
    topic_urls: list[str] = []
    errors: Counter[str] = Counter()
    search_pages = 0
    topic_pages = 0

    def add_topic(value: str) -> None:
        try:
            canonical = canonical_topic_url(value)
        except ValueError:
            errors["invalid_topic_url"] += 1
            return
        if canonical not in topic_urls and len(topic_urls) < bounded_limit:
            topic_urls.append(canonical)

    for url in urls:
        add_topic(url)

    records: list[dict] = []
    try:
        for query in queries:
            if len(topic_urls) >= bounded_limit:
                break
            try:
                html = client.get(search_url(query))
                search_pages += 1
            except (SourceBlocked, ValueError) as exc:
                errors[str(exc)] += 1
                continue
            for topic_url in extract_topic_links(html)[:bounded_limit]:
                add_topic(topic_url)

        for topic_url in topic_urls[:bounded_limit]:
            try:
                html = client.get(topic_url)
                topic_pages += 1
                records.append(
                    parse_topic(
                        html,
                        topic_url,
                        observed_at=observed_at,
                        max_age_days=max_age_days,
                    )
                )
            except (SourceBlocked, ValueError) as exc:
                errors[str(exc)] += 1
    finally:
        client.close()

    records = sort_records_newest_first(records)
    return {
        "observed_at": observed_at,
        "search_pages": search_pages,
        "topic_pages": topic_pages,
        "topic_candidates": len(topic_urls),
        "records": records,
        "errors": dict(sorted(errors.items())),
    }


def _write_records(
    records: list[dict],
    output: Path,
    *,
    retention_until: str,
    terms_basis_ref: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            enriched = dict(record)
            enriched["retention_until"] = retention_until
            enriched["terms_basis_ref"] = terms_basis_ref
            handle.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n")


def write_demand_csv(
    records: list[dict],
    output: Path,
    *,
    retention_until: str,
    terms_basis_ref: str,
) -> int:
    """Write a review handoff CSV and return the number of demand rows written.

    ``utf-8-sig`` keeps Thai text readable in common spreadsheet applications.
    Listing/owner/noise rows are deliberately omitted from this handoff.
    """

    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DEMAND_CSV_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        for record in records:
            if record.get("review_status") not in HANDOFF_REVIEW_STATUSES:
                continue
            row = {field: record.get(field, "") for field in DEMAND_CSV_FIELDS}
            row["retention_until"] = retention_until
            row["terms_basis_ref"] = terms_basis_ref
            writer.writerow(row)
            written += 1
    return written


def _summary(result: dict) -> dict:
    counts = Counter(record.get("review_status", "unknown") for record in result["records"])
    return {
        "status": "ok",
        "mode": "dry_run",
        "search_pages": result["search_pages"],
        "topic_pages": result["topic_pages"],
        "topic_candidates": result["topic_candidates"],
        "record_count": len(result["records"]),
        "review_status_counts": dict(sorted(counts.items())),
        "errors": result["errors"],
        "leads": [
            {
                "lead_id": record["lead_id"],
                "source_url": record["source_url"],
                "title": record["title"],
                "property_type": record["property_type"],
                "location": record["location"],
                "budget": record["budget"],
                "timing": record["timing"],
                "posted_at": record["posted_at"],
                "review_status": record["review_status"],
                "next_action": record["next_action"],
                "contact_permission": record["contact_permission"],
            }
            for record in result["records"]
            if record["review_status"] != "not_demand"
        ],
    }


def _valid_retention(value: str) -> str:
    candidate = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retention deadline must be an ISO date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError("retention deadline must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", help="Pantip search query; repeatable")
    parser.add_argument("--url", action="append", default=[], help="HTTPS Pantip topic URL; repeatable")
    parser.add_argument("--limit", type=int, default=10, help="Maximum unique topics across all queries (1-100)")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--max-age-days", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true", help="Report a bounded result without writing files (default)")
    parser.add_argument("--persist", action="store_true", help="Write a governed CSV handoff (or JSONL with --format jsonl)")
    parser.add_argument(
        "--format",
        choices=("csv", "jsonl"),
        default="csv",
        help="Persisted handoff format (default: csv; CSV excludes not_demand rows)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retention-until", help="Required with --persist, ISO date-time with timezone")
    parser.add_argument("--terms-basis-ref", help="Required with --persist, source-terms review reference")
    parser.add_argument("--json", action="store_true", help="Print a redacted summary JSON")
    args = parser.parse_args(argv)

    if args.persist and args.dry_run:
        parser.error("choose either --dry-run or --persist")
    retention_until = ""
    if args.persist:
        if not args.retention_until or not args.terms_basis_ref:
            parser.error("--persist requires --retention-until and --terms-basis-ref")
        try:
            retention_until = _valid_retention(args.retention_until)
        except ValueError as exc:
            parser.error(str(exc))

    result = collect(
        queries=args.query or ([] if args.url else list(DEFAULT_QUERIES)),
        urls=args.url,
        limit=args.limit,
        timeout=args.timeout,
        delay=args.delay,
        max_age_days=args.max_age_days,
        respect_robots=True,
    )
    summary = _summary(result)
    if args.persist:
        terms_basis_ref = str(args.terms_basis_ref).strip()
        if args.format == "csv":
            summary["output_count"] = write_demand_csv(
                result["records"],
                args.output,
                retention_until=retention_until,
                terms_basis_ref=terms_basis_ref,
            )
        else:
            _write_records(
                result["records"],
                args.output,
                retention_until=retention_until,
                terms_basis_ref=terms_basis_ref,
            )
            summary["output_count"] = len(result["records"])
        summary["mode"] = "persisted"
        summary["format"] = args.format
        summary["output"] = str(args.output)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"pantip_property_demand: {summary['mode']} | "
            f"topics={summary['topic_pages']} | records={summary['record_count']} | "
            f"statuses={summary['review_status_counts']}"
        )
        for lead in summary["leads"]:
            print(
                f"  {lead['review_status']} | {lead['title'][:80]} | "
                f"{lead['source_url']}"
            )
        if summary["errors"]:
            print(f"  errors={summary['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
