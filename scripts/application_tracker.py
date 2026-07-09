#!/usr/bin/env python3
"""
Lightweight Application Tracker Web UI.

Usage:
    python3 scripts/application_tracker.py
    python3 scripts/application_tracker.py --port 8080

Opens a browser-based UI to track job applications.
Reads/writes to apply_tracker.csv.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[4]
    load_dotenv(_root / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "domains" / "book-dev" / "book-scraping" / "data"
TRACKER_CSV = DATA_DIR / "apply_tracker.csv"
MATCHED_CSV = DATA_DIR / "matched_jobs.csv"

STATUS_OPTIONS = ["notified", "applied", "interviewing", "offer", "rejected", "withdrawn"]
STATUS_COLORS = {
    "notified": "#3b82f6",
    "applied": "#f59e0b",
    "interviewing": "#8b5cf6",
    "offer": "#10b981",
    "rejected": "#ef4444",
    "withdrawn": "#6b7280",
}

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Application Tracker</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #3b82f6;
    --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --purple: #8b5cf6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 24px; }
  .container { max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 1.8rem; margin-bottom: 8px; }
  .subtitle { color: var(--muted); margin-bottom: 24px; }

  /* Stats row */
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border-radius: 10px; padding: 16px; text-align: center; border: 1px solid var(--border); }
  .stat-card .num { font-size: 1.8rem; font-weight: 700; }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }

  /* Toolbar */
  .toolbar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
  .toolbar input, .toolbar select { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; }
  .toolbar input:focus, .toolbar select:focus { outline: none; border-color: var(--accent); }
  .btn { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-weight: 500; }
  .btn:hover { opacity: 0.85; }
  .btn-sm { padding: 4px 10px; font-size: 0.78rem; border-radius: 6px; }
  .btn-green { background: var(--green); }
  .btn-red { background: var(--red); }
  .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--muted); }

  /* Table */
  .table-wrap { background: var(--card); border-radius: 12px; border: 1px solid var(--border); overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 12px 16px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--border); }
  td { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 0.88rem; vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(59,130,246,0.05); }
  .title-cell { max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .url-cell a { color: var(--accent); text-decoration: none; font-size: 0.82rem; }
  .url-cell a:hover { text-decoration: underline; }

  /* Status badge */
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; text-transform: capitalize; }

  /* Modal */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; align-items: center; justify-content: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: var(--card); border-radius: 14px; padding: 28px; width: 440px; max-width: 95vw; border: 1px solid var(--border); }
  .modal h2 { margin-bottom: 16px; font-size: 1.2rem; }
  .modal label { display: block; font-size: 0.82rem; color: var(--muted); margin-bottom: 4px; margin-top: 12px; }
  .modal input, .modal select, .modal textarea { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; }
  .modal textarea { resize: vertical; min-height: 60px; }
  .modal-actions { display: flex; gap: 10px; margin-top: 20px; justify-content: flex-end; }

  .empty { text-align: center; padding: 40px; color: var(--muted); }

  /* Quick-add modal */
  .modal-lg { width: 600px; }
  .job-pick-list { max-height: 400px; overflow-y: auto; margin-top: 12px; }
  .job-pick-item { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-bottom: 1px solid var(--border); cursor: pointer; border-radius: 8px; }
  .job-pick-item:hover { background: rgba(59,130,246,0.08); }
  .job-pick-item:last-child { border-bottom: none; }
  .job-pick-score { font-weight: 700; font-size: 0.9rem; min-width: 36px; text-align: center; padding: 4px 8px; border-radius: 6px; background: var(--accent); color: white; }
  .job-pick-info { flex: 1; min-width: 0; }
  .job-pick-title { font-weight: 600; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .job-pick-meta { font-size: 0.78rem; color: var(--muted); }
  .job-pick-added { color: var(--green); font-size: 0.82rem; font-weight: 600; }
</style>
</head>
<body>
<div class="container">
  <h1>Application Tracker</h1>
  <p class="subtitle">Track your job applications pipeline</p>

  <div class="stats" id="stats"></div>

  <div class="toolbar">
    <input type="text" id="searchInput" placeholder="Search title / company / URL..." style="flex:1; min-width:180px;">
    <select id="filterStatus">
      <option value="">All statuses</option>
      <option value="notified">Notified</option>
      <option value="applied">Applied</option>
      <option value="interviewing">Interviewing</option>
      <option value="offer">Offer</option>
      <option value="rejected">Rejected</option>
      <option value="withdrawn">Withdrawn</option>
    </select>
    <button class="btn" onclick="openAddModal()">+ Add Application</button>
    <button class="btn btn-green" onclick="openQuickAddModal()">Quick Add</button>
    <button class="btn btn-ghost" onclick="loadData()">Refresh</button>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Title / Company</th>
          <th>Status</th>
          <th>Note</th>
          <th>Updated</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
    <div class="empty" id="emptyState" style="display:none;">No applications found. Click "+ Add Application" to get started.</div>
  </div>
</div>

<!-- Add/Edit Modal -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <h2 id="modalTitle">Add Application</h2>
    <label>Job URL *</label>
    <input type="url" id="inputUrl" placeholder="https://...">
    <label>Title (auto-filled from matched jobs if available)</label>
    <input type="text" id="inputTitle" placeholder="Job title">
    <label>Company</label>
    <input type="text" id="inputCompany" placeholder="Company name">
    <label>Status</label>
    <select id="inputStatus">
      <option value="notified">Notified</option>
      <option value="applied">Applied</option>
      <option value="interviewing">Interviewing</option>
      <option value="offer">Offer</option>
      <option value="rejected">Rejected</option>
      <option value="withdrawn">Withdrawn</option>
    </select>
    <label>Note</label>
    <textarea id="inputNote" placeholder="Salary, contact person, interview date..."></textarea>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn" id="modalSaveBtn" onclick="saveApplication()">Save</button>
    </div>
  </div>
</div>

<!-- Quick-Add Modal -->
<div class="modal-overlay" id="quickAddModal">
  <div class="modal modal-lg">
    <h2>Quick Add from Matched Jobs</h2>
    <p style="font-size:0.85rem;color:var(--muted);margin-bottom:8px;">Click a job to add it to your tracker. Already-tracked jobs are hidden.</p>
    <div class="job-pick-list" id="jobPickList"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeQuickAddModal()">Close</button>
    </div>
  </div>
</div>

<script>
let allApps = [];
let matchedJobs = {};
let editingUrl = null;

async function loadData() {
  const res = await fetch('/api/applications');
  const data = await res.json();
  allApps = data.applications || [];
  matchedJobs = data.matched_jobs || {};
  renderStats();
  renderTable();
}

function renderStats() {
  const counts = {};
  STATUS_OPTIONS.forEach(s => counts[s] = 0);
  allApps.forEach(a => { counts[a.status] = (counts[a.status] || 0) + 1; });
  const total = allApps.length;
  const statsHtml = `
    <div class="stat-card"><div class="num">${total}</div><div class="label">Total</div></div>
    ${STATUS_OPTIONS.map(s => `
      <div class="stat-card"><div class="num" style="color:${STATUS_COLORS[s]}">${counts[s]}</div><div class="label">${s}</div></div>
    `).join('')}
  `;
  document.getElementById('stats').innerHTML = statsHtml;
}

function renderTable() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const filterStatus = document.getElementById('filterStatus').value;
  let filtered = allApps.filter(a => {
    if (filterStatus && a.status !== filterStatus) return false;
    if (search) {
      const hay = `${a.title||''} ${a.company||''} ${a.url}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  const tbody = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');

  if (filtered.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = filtered.map(a => {
    const color = STATUS_COLORS[a.status] || '#6b7280';
    const title = a.title || a.url.split('/').slice(-1)[0].replace(/-/g,' ').slice(0,40);
    const company = a.company || '';
    const updated = a.updated_at ? new Date(a.updated_at).toLocaleDateString('en-AU', {day:'numeric',month:'short',year:'numeric'}) : '';
    return `<tr>
      <td class="title-cell">
        <div style="font-weight:600;">${esc(title)}</div>
        <div style="font-size:0.78rem;color:var(--muted);">${esc(company)}</div>
      </td>
      <td><span class="badge" style="background:${color}22;color:${color};border:1px solid ${color}44;">${a.status}</span></td>
      <td style="max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${esc(a.note||'')}">${esc(a.note||'')}</td>
      <td style="white-space:nowrap;font-size:0.82rem;color:var(--muted);">${updated}</td>
      <td>
        <select class="btn-sm" style="background:${color}22;color:${color};border:1px solid ${color}44;border-radius:6px;padding:3px 6px;font-size:0.78rem;" onchange="updateStatus('${esc(a.url)}', this.value)">
          ${STATUS_OPTIONS.map(s => `<option value="${s}" ${s===a.status?'selected':''}>${s}</option>`).join('')}
        </select>
        <button class="btn btn-sm btn-ghost" style="margin-left:4px;" onclick="openEditModal('${esc(a.url)}')">Edit</button>
        <button class="btn btn-sm btn-red" style="margin-left:2px;" onclick="deleteApp('${esc(a.url)}')">✕</button>
      </td>
    </tr>`;
  }).join('');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function updateStatus(url, status) {
  await fetch('/api/applications', {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({url, status})
  });
  loadData();
}

async function deleteApp(url) {
  if (!confirm('Remove this application?')) return;
  await fetch('/api/applications', {
    method: 'DELETE',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({url})
  });
  loadData();
}

function openAddModal() {
  editingUrl = null;
  document.getElementById('modalTitle').textContent = 'Add Application';
  document.getElementById('inputUrl').value = '';
  document.getElementById('inputTitle').value = '';
  document.getElementById('inputCompany').value = '';
  document.getElementById('inputStatus').value = 'applied';
  document.getElementById('inputNote').value = '';
  document.getElementById('modal').classList.add('active');
}

function openEditModal(url) {
  const app = allApps.find(a => a.url === url);
  if (!app) return;
  editingUrl = url;
  document.getElementById('modalTitle').textContent = 'Edit Application';
  document.getElementById('inputUrl').value = app.url;
  document.getElementById('inputTitle').value = app.title || '';
  document.getElementById('inputCompany').value = app.company || '';
  document.getElementById('inputStatus').value = app.status;
  document.getElementById('inputNote').value = app.note || '';
  document.getElementById('modal').classList.add('active');
}

function closeModal() { document.getElementById('modal').classList.remove('active'); }

async function saveApplication() {
  const url = document.getElementById('inputUrl').value.trim();
  if (!url) { alert('URL is required'); return; }
  const payload = {
    url,
    title: document.getElementById('inputTitle').value.trim(),
    company: document.getElementById('inputCompany').value.trim(),
    status: document.getElementById('inputStatus').value,
    note: document.getElementById('inputNote').value.trim(),
  };
  await fetch('/api/applications', {
    method: editingUrl ? 'PATCH' : 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  closeModal();
  loadData();
}

document.getElementById('searchInput').addEventListener('input', renderTable);
document.getElementById('filterStatus').addEventListener('change', renderTable);
document.getElementById('modal').addEventListener('click', e => { if (e.target === document.getElementById('modal')) closeModal(); });
document.getElementById('quickAddModal').addEventListener('click', e => { if (e.target === document.getElementById('quickAddModal')) closeQuickAddModal(); });

const STATUS_OPTIONS = ${json.dumps(STATUS_OPTIONS)};
const STATUS_COLORS = ${json.dumps(STATUS_COLORS)};

// ── Quick-Add ──────────────────────────────────────────────────────────────
let availableJobs = [];

async function openQuickAddModal() {
  const res = await fetch('/api/matched-jobs');
  const data = await res.json();
  availableJobs = data.jobs || [];
  renderJobPickList();
  document.getElementById('quickAddModal').classList.add('active');
}

function closeQuickAddModal() { document.getElementById('quickAddModal').classList.remove('active'); }

function renderJobPickList() {
  const list = document.getElementById('jobPickList');
  if (availableJobs.length === 0) {
    list.innerHTML = '<div style="text-align:center;padding:24px;color:var(--muted);">No unmatched jobs available. Run the pipeline first.</div>';
    return;
  }
  list.innerHTML = availableJobs.map(j => `
    <div class="job-pick-item" onclick="quickAddJob('${esc(j.url)}')">
      <div class="job-pick-score">${j.score}</div>
      <div class="job-pick-info">
        <div class="job-pick-title">${esc(j.title || 'Unknown')}</div>
        <div class="job-pick-meta">${esc(j.company || 'N/A')} · ${esc(j.source || '')} ${j.salary ? '· ' + esc(j.salary) : ''}</div>
      </div>
    </div>
  `).join('');
}

async function quickAddJob(url) {
  const job = availableJobs.find(j => j.url === url);
  if (!job) return;
  await fetch('/api/applications', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      url: job.url,
      title: job.title || '',
      company: job.company || '',
      status: 'notified',
      note: `score=${job.score}`,
    })
  });
  // Remove from available list
  availableJobs = availableJobs.filter(j => j.url !== url);
  renderJobPickList();
  loadData();
}

loadData();
</script>
</body>
</html>"""


def bulk_mark_applied() -> int:
    """Move all 'notified' entries to 'applied' status. Returns count of updated entries."""
    apps = load_applications()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = 0
    for app in apps:
        if app.get("status") == "notified":
            app["status"] = "applied"
            app["updated_at"] = now
            updated += 1
    if updated > 0:
        save_applications(apps)
    return updated


def load_applications() -> list:
    """Load applications from CSV."""
    if not TRACKER_CSV.exists():
        return []
    apps = []
    with open(TRACKER_CSV, "r") as f:
        for row in csv.DictReader(f):
            apps.append(row)
    return apps


def save_applications(apps: list):
    """Save applications to CSV."""
    fieldnames = ["url", "title", "company", "status", "note", "updated_at"]
    with open(TRACKER_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for app in apps:
            writer.writerow(app)


def load_matched_jobs() -> dict:
    """Load matched jobs for auto-fill lookup (url -> {title, company})."""
    if not MATCHED_CSV.exists():
        return {}
    result = {}
    with open(MATCHED_CSV, "r") as f:
        for row in csv.DictReader(f):
            url = row.get("url", "")
            if url:
                result[url] = {"title": row.get("title", ""), "company": row.get("company", "")}
    return result


def load_matched_jobs_list() -> list:
    """Load all matched jobs as a list of dicts with score, source, salary."""
    if not MATCHED_CSV.exists():
        return []
    jobs = []
    with open(MATCHED_CSV, "r") as f:
        for row in csv.DictReader(f):
            url = row.get("url", "")
            if not url:
                continue
            try:
                score = int(row.get("_score", 0))
            except (ValueError, TypeError):
                score = 0
            jobs.append({
                "url": url,
                "title": row.get("title", ""),
                "company": row.get("company", ""),
                "score": score,
                "source": row.get("source", ""),
                "salary": row.get("salary", ""),
                "location": row.get("location", ""),
            })
    jobs.sort(key=lambda j: j["score"], reverse=True)
    return jobs


def enrich_applications(apps: list, matched: dict) -> list:
    """Add title/company from matched_jobs if missing."""
    for app in apps:
        url = app.get("url", "")
        if not app.get("title") and url in matched:
            app["title"] = matched[url].get("title", "")
        if not app.get("company") and url in matched:
            app["company"] = matched[url].get("company", "")
    return apps


class TrackerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self.send_html(HTML_TEMPLATE)
        elif path == "/api/applications":
            apps = load_applications()
            matched = load_matched_jobs()
            apps = enrich_applications(apps, matched)
            self.send_json({"applications": apps, "matched_jobs": matched})
        elif path == "/api/matched-jobs":
            # Return matched jobs not already in the tracker
            tracked_urls = {a.get("url") for a in load_applications()}
            all_jobs = load_matched_jobs_list()
            available = [j for j in all_jobs if j["url"] not in tracked_urls]
            self.send_json({"jobs": available, "total": len(available)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/applications":
            data = self.read_body()
            url = data.get("url", "").strip()
            if not url:
                self.send_json({"error": "url required"}, 400)
                return
            apps = load_applications()
            # Check for duplicate
            for app in apps:
                if app.get("url") == url:
                    self.send_json({"error": "already exists, use PATCH"}, 409)
                    return
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_app = {
                "url": url,
                "title": data.get("title", ""),
                "company": data.get("company", ""),
                "status": data.get("status", "applied"),
                "note": data.get("note", ""),
                "updated_at": now,
            }
            apps.append(new_app)
            save_applications(apps)
            self.send_json({"ok": True, "application": new_app}, 201)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PATCH(self):
        path = urlparse(self.path).path
        if path == "/api/applications":
            data = self.read_body()
            url = data.get("url", "").strip()
            apps = load_applications()
            found = False
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for app in apps:
                if app.get("url") == url:
                    for key in ["title", "company", "status", "note"]:
                        if key in data:
                            app[key] = data[key]
                    app["updated_at"] = now
                    found = True
                    break
            if not found:
                self.send_json({"error": "not found"}, 404)
                return
            save_applications(apps)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/applications":
            data = self.read_body()
            url = data.get("url", "").strip()
            apps = load_applications()
            new_apps = [a for a in apps if a.get("url") != url]
            if len(new_apps) == len(apps):
                self.send_json({"error": "not found"}, 404)
                return
            save_applications(new_apps)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="Application Tracker Web UI")
    parser.add_argument("--port", type=int, default=8787, help="Port to serve on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--bulk-apply", action="store_true", help="Move all 'notified' entries to 'applied' and exit")
    args = parser.parse_args()

    # Ensure CSV exists
    if not TRACKER_CSV.exists():
        TRACKER_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["url", "title", "company", "status", "note", "updated_at"])
            writer.writeheader()
        print(f"Created {TRACKER_CSV}")

    # Handle bulk-apply mode
    if args.bulk_apply:
        count = bulk_mark_applied()
        print(f"✓ Moved {count} entries from 'notified' to 'applied'")
        return

    server = HTTPServer((args.host, args.port), TrackerHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Application Tracker running at {url}")
    print(f"Press Ctrl+C to stop")

    if not args.no_browser:
        import threading
        threading.Timer(1.0, lambda: os.system(f"xdg-open '{url}' 2>/dev/null &")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
