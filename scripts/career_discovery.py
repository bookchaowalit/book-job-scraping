#!/usr/bin/env python3
"""Bounded, public Greenhouse discovery for remote career changes/relocation.

GET only. Captures belong here; Bronze/job.v1 remains owned by book-job-data.
An incomplete scan fails without replacing the last complete capture.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

try:
    from .job_role_relevance import is_relevant_role
    from .job_target_policy import qualify_job, REJECT
except ImportError:
    from job_role_relevance import is_relevant_role
    from job_target_policy import qualify_job, REJECT

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['title', 'company', 'location', 'salary', 'url', 'source', 'keyword',
          'posted', 'tags', 'scraped_at', 'description', 'search_lane']
MAX_BYTES = 12 * 1024 * 1024


def public_get(board: str) -> dict:
    if not re.fullmatch(r'[a-z0-9_-]{1,80}', board):
        raise ValueError('Invalid public board identifier')
    endpoint = f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs'
    with requests.Session() as session:
        session.trust_env = False  # never send local netrc credentials
        with session.get(endpoint, params={'content': 'true'}, timeout=(10, 30),
                         allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError(f'{board}: HTTP {response.status_code}')
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f'{board}: response exceeds capture budget')
                chunks.append(chunk)
            return json.loads(b''.join(chunks))


def normalize_board(payload: dict, board: str, company: str, now: str) -> list[dict]:
    rows = payload.get('jobs')
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError(f'{board}: invalid or oversized jobs payload')
    output = []
    for item in rows:
        if not isinstance(item, dict) or not str(item.get('id', '')).isdigit() or not item.get('title'):
            raise ValueError(f'{board}: malformed job record')
        # Use documented canonical ATS URL; never follow arbitrary embedded URLs.
        body = BeautifulSoup(html.unescape(item.get('content') or ''), 'html.parser').get_text(' ', strip=True)
        row = dict(title=item['title'], company=company,
                   location=(item.get('location') or {}).get('name', ''), salary='',
                   url=f"https://job-boards.greenhouse.io/{board}/jobs/{item['id']}",
                   source=f'Greenhouse:{board}', keyword='', posted=item.get('updated_at', ''),
                   tags='', scraped_at=now, description=body, search_lane='')
        qualified = qualify_job(row)
        # Explicit listing evidence controls relocation. Otherwise this source
        # is a career-change search, not a concurrent side-job recommendation.
        row['search_lane'] = 'relocation' if qualified['search_lane'] == 'relocation' else 'remote_career'
        qualified = qualify_job(row)
        if row['search_lane'] == 'remote_career' and qualified['work_arrangement'] != 'Remote':
            continue
        if is_relevant_role(row) and qualified['qualification_status'] != REJECT:
            output.append(row)
    return output


def collect(config: Path, fetch=public_get) -> tuple[list[dict], dict]:
    sources = yaml.safe_load(config.read_text())['greenhouse_boards']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 10:
        raise ValueError('Configure between 1 and 10 public boards')
    now = datetime.now(timezone.utc).isoformat()
    records, counts = [], {}
    for source in sources:
        board = source['board']
        records.extend(normalize_board(fetch(board), board, source['company'], now))
        counts[board] = sum(r['source'] == f'Greenhouse:{board}' for r in records)
    return list({row['url']: row for row in records}.values()), counts


def write_capture(rows: list[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                     dir=destination.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    tmp.replace(destination)


class CareerDiscovery:
    async def run(self, **kwargs):
        rows, counts = collect(ROOT / 'config/career_sources.yaml')
        write_capture(rows, ROOT / 'data/career_postings.csv')
        print(json.dumps({'career_capture': len(rows), 'sources': counts}))
        return [{'source': 'career_postings'} for _ in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Save local capture; never submit')
    args = parser.parse_args()
    try:
        rows, counts = collect(ROOT / 'config/career_sources.yaml')
        if args.write:
            write_capture(rows, ROOT / 'data/career_postings.csv')
        print(json.dumps({'rows': len(rows), 'sources': counts, 'saved': args.write}))
    except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
        # Do not echo provider payloads, credential-bearing URLs, or full traces.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'capture_replaced': False}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
