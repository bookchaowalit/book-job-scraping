#!/usr/bin/env python3
"""
Unified Pipeline Health Monitor
Comprehensive health check: DB status, cron, disk, API keys, scrape age, notifications.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent.parent.parent
DATA_DIR = SCRIPT_DIR.parent / "data"
CRON_LOG = DATA_DIR / "cron_scheduler_log.json"
HEALTH_REPORT = DATA_DIR / "unified_health_report.json"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# API Keys to check
API_KEYS = {
    "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
}


def check_disk_space():
    """Check disk space on root partition."""
    try:
        stat = shutil.disk_usage("/")
        total_gb = stat.total / (1024**3)
        used_gb = stat.used / (1024**3)
        free_gb = stat.free / (1024**3)
        percent = (stat.used / stat.total) * 100
        
        return {
            "status": "ok" if percent < 80 else "warning" if percent < 90 else "critical",
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_used": round(percent, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_cron_status():
    """Check cron scheduler status."""
    if not CRON_LOG.exists():
        return {"status": "missing", "message": "No cron log found"}
    
    try:
        log = json.loads(CRON_LOG.read_text())
        last_daily = log.get("last_daily", "")
        last_weekly = log.get("last_weekly", "")
        
        # Check if recent
        now = datetime.now()
        issues = []
        
        if last_daily:
            daily_dt = datetime.fromisoformat(last_daily[:19])
            hours_ago = (now - daily_dt).total_seconds() / 3600
            if hours_ago > 48:
                issues.append(f"Daily tasks stale ({hours_ago:.1f}h ago)")
        
        if last_weekly:
            weekly_dt = datetime.fromisoformat(last_weekly[:19])
            days_ago = (now - weekly_dt).total_seconds() / 86400
            if days_ago > 8:
                issues.append(f"Weekly tasks stale ({days_ago:.1f}d ago)")
        
        status = "ok" if not issues else "warning"
        return {
            "status": status,
            "last_daily": last_daily[:19] if last_daily else "never",
            "last_weekly": last_weekly[:19] if last_weekly else "never",
            "issues": issues,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_data_freshness():
    """Check freshness of key data files."""
    files = {
        "job_postings.csv": DATA_DIR / "job_postings.csv",
        "matched_jobs.csv": DATA_DIR / "matched_jobs.csv",
        "apply_tracker.csv": DATA_DIR / "apply_tracker.csv",
        "job_descriptions.csv": DATA_DIR / "job_descriptions.csv",
    }
    
    freshness = {}
    for name, path in files.items():
        if path.exists():
            mtime = path.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            size = path.stat().st_size
            
            # Count rows
            row_count = 0
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    row_count = sum(1 for _ in reader) - 1  # Exclude header
            except Exception:
                pass
            
            freshness[name] = {
                "status": "ok" if age_hours < 48 else "stale",
                "age_hours": round(age_hours, 1),
                "size_bytes": size,
                "rows": row_count,
            }
        else:
            freshness[name] = {"status": "missing", "age_hours": None, "size_bytes": 0, "rows": 0}
    
    return freshness


def check_api_keys():
    """Check if API keys are configured (env var or hardcoded fallback)."""
    results = {}
    for key_name, fallback in API_KEYS.items():
        env_val = os.environ.get(key_name, "")
        # Accept if env var is non-empty OR fallback is non-empty
        effective = env_val if env_val else fallback
        if effective:
            results[key_name] = {"status": "ok", "configured": True, "source": "env" if env_val else "fallback"}
        else:
            results[key_name] = {"status": "missing", "configured": False, "source": None}
    
    return results


def check_pipeline_health():
    """Check pipeline runner health."""
    health_file = DATA_DIR / "pipeline_health.json"
    if not health_file.exists():
        return {"status": "missing", "message": "No pipeline health report"}
    
    try:
        health = json.loads(health_file.read_text())
        return {
            "status": "ok" if health.get("healthy") else "warning",
            "timestamp": health.get("timestamp", "")[:19],
            "issues": len(health.get("issues", [])),
            "warnings": len(health.get("warnings", [])),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_resume_variants():
    """Check resume variants status."""
    registry_file = DATA_DIR / "resume_variants" / "resume_registry.json"
    if not registry_file.exists():
        return {"status": "missing", "count": 0}
    
    try:
        registry = json.loads(registry_file.read_text())
        variants = registry.get("variants", {})
        return {
            "status": "ok" if len(variants) >= 5 else "warning",
            "count": len(variants),
            "updated_at": registry.get("updated_at", "")[:19],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def send_telegram(message):
    """Send Telegram notification."""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")


def run_health_check(send_telegram_flag=False):
    """Run comprehensive health check."""
    print(f"\n{'='*70}")
    print(f"  UNIFIED PIPELINE HEALTH MONITOR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    report = {"timestamp": datetime.now().isoformat(), "checks": {}}
    issues = []
    warnings = []
    
    # 1. Disk Space
    print("💾 Disk Space:")
    disk = check_disk_space()
    report["checks"]["disk"] = disk
    icon = "✅" if disk["status"] == "ok" else "⚠️" if disk["status"] == "warning" else "❌"
    print(f"   {icon} {disk.get('free_gb', 0):.1f} GB free ({disk.get('percent_used', 0):.1f}% used)")
    if disk["status"] != "ok":
        issues.append(f"Disk: {disk.get('percent_used', 0):.1f}% used")
    
    # 2. Cron Status
    print("\n⏰ Cron Scheduler:")
    cron = check_cron_status()
    report["checks"]["cron"] = cron
    icon = "✅" if cron["status"] == "ok" else "⚠️"
    print(f"   {icon} Last daily: {cron.get('last_daily', 'never')}")
    print(f"   {icon} Last weekly: {cron.get('last_weekly', 'never')}")
    if cron.get("issues"):
        warnings.extend(cron["issues"])
        for issue in cron["issues"]:
            print(f"   ⚠️  {issue}")
    
    # 3. Data Freshness
    print("\n📊 Data Freshness:")
    freshness = check_data_freshness()
    report["checks"]["data"] = freshness
    for name, info in freshness.items():
        icon = "✅" if info["status"] == "ok" else "⚠️" if info["status"] == "stale" else "❌"
        age = f"{info['age_hours']:.1f}h" if info['age_hours'] else "N/A"
        rows = info.get('rows', 0)
        print(f"   {icon} {name:30s} {age:8s} ({rows:,} rows)")
        if info["status"] == "missing":
            issues.append(f"Data missing: {name}")
        elif info["status"] == "stale":
            warnings.append(f"Data stale: {name}")
    
    # 4. API Keys
    print("\n🔑 API Keys:")
    api_keys = check_api_keys()
    report["checks"]["api_keys"] = api_keys
    for key_name, info in api_keys.items():
        icon = "✅" if info["status"] == "ok" else "❌"
        print(f"   {icon} {key_name}")
        if info["status"] != "ok":
            issues.append(f"API key missing: {key_name}")
    
    # 5. Pipeline Health
    print("\n🔧 Pipeline Health:")
    pipeline = check_pipeline_health()
    report["checks"]["pipeline"] = pipeline
    icon = "✅" if pipeline["status"] == "ok" else "⚠️" if pipeline["status"] == "warning" else "❌"
    print(f"   {icon} Status: {pipeline.get('status', 'unknown')}")
    if pipeline.get("issues"):
        print(f"   ⚠️  {pipeline['issues']} issue(s), {pipeline.get('warnings', 0)} warning(s)")
    
    # 6. Resume Variants
    print("\n📄 Resume Variants:")
    resumes = check_resume_variants()
    report["checks"]["resumes"] = resumes
    icon = "✅" if resumes["status"] == "ok" else "⚠️"
    print(f"   {icon} {resumes.get('count', 0)} variants configured")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    
    if not issues and not warnings:
        print("  ✅ All systems healthy!")
        report["overall_status"] = "healthy"
    else:
        if issues:
            print(f"  🔴 {len(issues)} critical issue(s):")
            for issue in issues[:5]:
                print(f"     • {issue}")
        if warnings:
            print(f"  🟡 {len(warnings)} warning(s):")
            for warning in warnings[:5]:
                print(f"     • {warning}")
        
        report["overall_status"] = "critical" if issues else "warning"
        report["issues"] = issues
        report["warnings"] = warnings
    
    # Save report
    HEALTH_REPORT.write_text(json.dumps(report, indent=2))
    print(f"\n  📄 Report saved: {HEALTH_REPORT.name}")
    print(f"{'='*70}\n")
    
    # Telegram
    if send_telegram_flag:
        status_icon = "✅" if report["overall_status"] == "healthy" else "⚠️" if report["overall_status"] == "warning" else "❌"
        msg = f"{status_icon} *Pipeline Health Check*\n\n"
        msg += f"Status: {report['overall_status'].upper()}\n"
        msg += f"Disk: {disk.get('free_gb', 0):.1f} GB free\n"
        msg += f"Data files: {sum(1 for f in freshness.values() if f['status'] == 'ok')}/{len(freshness)} fresh\n"
        
        if issues:
            msg += f"\n🔴 {len(issues)} critical issue(s)\n"
        if warnings:
            msg += f"🟡 {len(warnings)} warning(s)\n"
        
        send_telegram(msg)
        print("📱 Telegram notification sent")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Unified Pipeline Health Monitor")
    parser.add_argument("--send-telegram", action="store_true", help="Send Telegram notification")
    args = parser.parse_args()
    
    run_health_check(send_telegram_flag=args.send_telegram)


if __name__ == "__main__":
    main()
