#!/usr/bin/env python3
"""Validate and report multi-business source coverage.

The scheduler configuration remains the runtime source of truth for cadence
and enablement. ``config/source_coverage.yaml`` adds the product view:
business lane, acquisition channel, implementation readiness, contract, and
restoration priority.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - project venv supplies PyYAML
    raise SystemExit("PyYAML is required; install requirements.txt first") from exc


ROOT = Path(__file__).resolve().parents[1]
JOBS_CONFIG = ROOT / "config" / "jobs.yaml"
COVERAGE_CONFIG = ROOT / "config" / "source_coverage.yaml"
ALLOWED_CHANNELS = {"api", "cli", "rss", "scrape", "hybrid", "local"}
ALLOWED_STATUSES = {"active", "blocked", "planned", "migrated"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def _module_path(module: str) -> Path:
    return ROOT / (module.replace(".", "/") + ".py")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping at {path}")
    return value


def validate() -> tuple[dict, list[str], list[str]]:
    jobs_doc = _load_yaml(JOBS_CONFIG)
    coverage_doc = _load_yaml(COVERAGE_CONFIG)
    jobs = jobs_doc.get("jobs", [])
    sources = coverage_doc.get("sources", [])
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(jobs, list):
        errors.append("config/jobs.yaml: jobs must be a list")
        jobs = []
    if not isinstance(sources, list):
        errors.append("config/source_coverage.yaml: sources must be a list")
        sources = []

    jobs_by_name = {job.get("name"): job for job in jobs if isinstance(job, dict)}
    coverage_by_name: dict[str, dict] = {}
    for entry in sources:
        if not isinstance(entry, dict):
            errors.append("source coverage entry must be a mapping")
            continue
        name = entry.get("job")
        if not name:
            errors.append("source coverage entry is missing job")
        elif name in coverage_by_name:
            errors.append(f"duplicate source coverage job: {name}")
        else:
            coverage_by_name[name] = entry

    missing = sorted(set(jobs_by_name) - set(coverage_by_name))
    extra = sorted(set(coverage_by_name) - set(jobs_by_name))
    errors.extend(f"missing coverage entry for scheduler job: {name}" for name in missing)
    errors.extend(f"coverage entry has no scheduler job: {name}" for name in extra)

    lane_names = set((coverage_doc.get("business_lanes") or {}).keys())
    if not lane_names:
        errors.append("source coverage must define business_lanes")

    for name, job in jobs_by_name.items():
        entry = coverage_by_name.get(name)
        if not entry:
            continue

        for coverage_field, job_field in (
            ("url", "url"),
            ("engine", "engine"),
            ("schedule", "schedule"),
            ("module", "scraper_module"),
        ):
            if entry.get(coverage_field) != job.get(job_field):
                errors.append(
                    f"{name}: {coverage_field} differs between jobs.yaml ({job.get(job_field)!r}) "
                    f"and source_coverage.yaml ({entry.get(coverage_field)!r})"
                )

        business = entry.get("business")
        channel = entry.get("channel")
        status = entry.get("status")
        priority = entry.get("priority")
        for field, value, allowed in (
            ("business", business, lane_names),
            ("channel", channel, ALLOWED_CHANNELS),
            ("status", status, ALLOWED_STATUSES),
            ("priority", priority, ALLOWED_PRIORITIES),
        ):
            if value not in allowed:
                errors.append(f"{name}: invalid {field}={value!r}")

        if not entry.get("source"):
            errors.append(f"{name}: source is required")
        if not entry.get("contract"):
            errors.append(f"{name}: contract is required")
        if not entry.get("next_action"):
            errors.append(f"{name}: next_action is required")

        enabled = bool(job.get("enabled"))
        if enabled and status != "active":
            errors.append(f"{name}: enabled scheduler job must have status=active")
        if not enabled and status == "active":
            errors.append(f"{name}: disabled scheduler job cannot have status=active")
        if status == "migrated":
            if enabled:
                errors.append(f"{name}: migrated coverage must disable the local scheduler job")
            if not entry.get("owner_repository"):
                errors.append(f"{name}: migrated coverage requires owner_repository")
        if channel == "local" and job.get("engine") != "local":
            errors.append(f"{name}: local channel requires engine=local")
        if channel != "local" and not job.get("url"):
            errors.append(f"{name}: non-local channel requires a source URL")

        module = entry.get("module", "")
        available = _module_path(module).is_file() if module else False
        if enabled and not available:
            errors.append(f"{name}: enabled adapter module is missing: {module}")
        if status == "active" and not available:
            errors.append(f"{name}: active coverage requires an available adapter: {module}")
        if status == "blocked" and available:
            warnings.append(f"{name}: adapter exists but coverage is still blocked by policy/config")

    summary = {
        "schema_version": coverage_doc.get("schema_version", ""),
        "jobs": len(jobs_by_name),
        "sources": len(coverage_by_name),
        "active": sum(1 for entry in coverage_by_name.values() if entry.get("status") == "active"),
        "blocked": sum(1 for entry in coverage_by_name.values() if entry.get("status") == "blocked"),
        "planned": sum(1 for entry in coverage_by_name.values() if entry.get("status") == "planned"),
        "migrated": sum(1 for entry in coverage_by_name.values() if entry.get("status") == "migrated"),
        "by_business": dict(Counter(entry.get("business", "unknown") for entry in coverage_by_name.values())),
        "by_channel": dict(Counter(entry.get("channel", "unknown") for entry in coverage_by_name.values())),
        "restoration_queue": [
            {
                "job": entry.get("job"),
                "business": entry.get("business"),
                "priority": entry.get("priority"),
                "source": entry.get("source"),
                "next_action": entry.get("next_action"),
            }
            for entry in sorted(
                (
                    item
                    for item in coverage_by_name.values()
                    if item.get("status") not in {"active", "migrated"}
                ),
                key=lambda item: (PRIORITY_ORDER.get(item.get("priority"), 99), item.get("job", "")),
            )
        ],
    }
    return summary, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate multi-business source coverage")
    parser.add_argument("--check", action="store_true", help="Fail on registry/config drift")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    args = parser.parse_args()

    try:
        summary, errors, warnings = validate()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"summary": summary, "errors": errors, "warnings": warnings}, indent=2))
    else:
        print("Source Coverage Registry")
        print("=" * 72)
        print(
            f"Sources: {summary['sources']} | active: {summary['active']} | "
            f"blocked: {summary['blocked']} | planned: {summary['planned']} | "
            f"migrated: {summary['migrated']}"
        )
        print(f"By business: {', '.join(f'{key}={value}' for key, value in sorted(summary['by_business'].items()))}")
        print(f"By channel: {', '.join(f'{key}={value}' for key, value in sorted(summary['by_channel'].items()))}")
        if summary["restoration_queue"]:
            print("\nRestoration queue:")
            for item in summary["restoration_queue"]:
                print(f"  [{item['priority']}] {item['job']} ({item['business']}) — {item['next_action']}")
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
        print("\nResult: " + ("FAIL" if errors else "OK"))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
