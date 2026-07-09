#!/usr/bin/env bash
# ============================================================
# Cron Auto-Scheduler Setup for Book Scraping Platform
# ============================================================
# This script sets up a cron job to run the scraper scheduler
# loop automatically in the background.
#
# Usage:
#   bash setup_cron.sh install   — Install cron job
#   bash setup_cron.sh remove    — Remove cron job
#   bash setup_cron.sh status    — Check if cron is installed
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"
CRON_TAG="# book-scraping-scheduler"
LOG_FILE="${PROJECT_DIR}/data/logs/cron.log"

install_cron() {
    # Remove existing entry first
    remove_cron_silent

    # Ensure log directory exists
    mkdir -p "${PROJECT_DIR}/data/logs"

    # Add cron job: run scheduler loop every 5 minutes
    # The scheduler loop itself checks for due jobs every 60s
    (crontab -l 2>/dev/null || true; echo "*/5 * * * * cd ${PROJECT_DIR} && ${PYTHON} main.py run >> ${LOG_FILE} 2>&1 ${CRON_TAG}") | crontab -

    echo "✓ Cron job installed — runs every 5 minutes"
    echo "  Log: ${LOG_FILE}"
    echo ""
    echo "To verify: crontab -l | grep book-scraping"
}

remove_cron_silent() {
    crontab -l 2>/dev/null | grep -v "${CRON_TAG}" | crontab - 2>/dev/null || true
}

remove_cron() {
    remove_cron_silent
    echo "✓ Cron job removed"
}

show_status() {
    echo "Cron jobs for book-scraping:"
    if crontab -l 2>/dev/null | grep -q "${CRON_TAG}"; then
        crontab -l | grep "${CRON_TAG}"
        echo ""
        echo "Status: ACTIVE"
    else
        echo "  (none installed)"
        echo ""
        echo "Status: NOT INSTALLED"
    fi
}

case "${1}" in
    install)
        install_cron
        ;;
    remove)
        remove_cron
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {install|remove|status}"
        exit 1
        ;;
esac
