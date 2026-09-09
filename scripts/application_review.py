#!/usr/bin/env python3
"""Local application review, immutable prepared packets, and confirmed receipts.

No network, AI provider, browser, email, or automatic submission. Manual ATS
submission works across providers; legacy browser adapters are not prerequisites.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

try:
    from .job_target_policy import HUMAN_VERIFICATION_FIELDS, PASS, REJECT, qualify_job
except ImportError:
    from job_target_policy import HUMAN_VERIFICATION_FIELDS, PASS, REJECT, qualify_job

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'data/career-review/current'


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('A public HTTPS job URL is required')
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.startswith('utm_') and k not in {'gh_src', 'source'}]
    return urlunsplit(('https', parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(query), ''))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    tmp.replace(path)


def build_packets(matches: Path, output: Path, per_lane: int = 3) -> dict:
    if not 1 <= per_lane <= 20:
        raise ValueError('per-lane must be 1..20')
    with matches.open(encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    def score(row):
        try:
            points = float(row.get('score') or 0)
        except ValueError:
            points = 0
        # Current direct employer postings are more actionable than aggregators.
        return (str(row.get('source', '')).startswith('Greenhouse:'), points)
    rows.sort(key=score, reverse=True)
    counts, selected, seen = {}, [], set()
    output.mkdir(parents=True, exist_ok=True)
    for row in rows:
        qualification = qualify_job(row)
        lane = qualification['search_lane']
        if lane not in {'remote_career', 'relocation'} or qualification['qualification_status'] == REJECT:
            continue
        if counts.get(lane, 0) >= per_lane:
            continue
        url = canonical_url(row['url'])
        if url in seen:
            continue
        seen.add(url)
        job_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        directory = output / job_id
        directory.mkdir(exist_ok=True)
        candidate = {**row, **qualification, 'url': url}
        candidate_path = directory / 'candidate.json'
        # A reviewed snapshot is never silently refreshed under an approval.
        if not candidate_path.exists():
            atomic_json(candidate_path, candidate)
            atomic_json(directory / 'verification.json', {
                field: '' for field in HUMAN_VERIFICATION_FIELDS
            })
            title = str(row.get('title', '')).replace('\n', ' ')
            company = str(row.get('company', '')).replace('\n', ' ')
            text = (
                f'# ตรวจใบสมัคร: {title} — {company}\n\n'
                f'- ช่องทาง: `{lane}`\n- ประกาศ: {url}\n'
                f'- สถานที่: {row.get("location", "")}\n'
                f'- เก็บข้อมูล: {row.get("scraped_at", "")}\n'
                f'- เงินเดือน: {row.get("salary") or "ต้องตรวจจากประกาศ/ผู้สรรหา"}\n'
                f'- สัญญาณวีซ่า: `{qualification["visa_sponsorship"]}` (ยังไม่ใช่การยืนยันสิทธิ์)\n\n'
                '## ข้อมูลที่ยังต้องตรวจ\n\n' +
                '\n'.join(f'- [ ] `{reason}`' for reason in qualification['qualification_reasons'].split(';')) +
                '\n\n## เอกสารและคำตอบ\n\n'
                '- [ ] Resume ที่ตรวจความถูกต้องและปรับให้ตรงตำแหน่ง\n'
                '- [ ] Cover letter ที่ใช้ผลงานจริง พร้อมเหตุผลที่ตรงกับงาน\n'
                '- [ ] สิทธิ์ทำงาน/ความต้องการ sponsorship ตามข้อเท็จจริง\n'
                '- [ ] เงินเดือนที่คาดหวัง สกุลเงิน notice period และวันเริ่มงาน\n'
                '- [ ] ตรวจคำถามเฉพาะบริษัทด้วยตนเอง ไม่เดาคำตอบหรือข้อมูลส่วนตัว\n'
                '- [ ] เจ้าของตรวจบริษัท ตำแหน่ง URL และเอกสารก่อนอนุมัติ\n\n'
                'กรอก `verification.json` ด้วยหลักฐานจากประกาศปัจจุบันหรือผู้สรรหา '
                'แล้วใช้คำสั่ง prepare พร้อม resume และ cover letter จริง '
                'ชุดนี้ยังไม่ใช่ใบสมัครที่ส่งแล้ว\n'
            )
            (directory / 'review.md').write_text(text, encoding='utf-8')
        if not (directory / 'prepared.json').exists():
            verification_path = directory / 'verification.json'
            verification = json.loads(verification_path.read_text())
            missing = {field: '' for field in HUMAN_VERIFICATION_FIELDS if field not in verification}
            if missing:
                atomic_json(verification_path, {**verification, **missing})
        counts[lane] = counts.get(lane, 0) + 1
        selected.append({'id': job_id, 'lane': lane, 'company': row.get('company'),
                         'title': row.get('title'), 'url': url, 'review': f'{job_id}/review.md'})
    atomic_json(output / 'index.json', {'schema_version': 'application-review.v1', 'items': selected})
    index = '# คิวตรวจใบสมัคร\n\nยังไม่มีการส่งใบสมัครจากคำสั่งนี้\n\n'
    for item in selected:
        label = f'{item["company"]} — {item["title"]}'.replace('[', '').replace(']', '').replace('\n', ' ')
        index += f'- `{item["lane"]}` [{label}]({item["review"]})\n'
        for name, title in [('FIT-REVIEW.md', 'ข้อพิจารณาเฉพาะงาน'), ('cover-letter-draft.md', 'Cover letter draft')]:
            if (output / item['id'] / name).is_file():
                index += f'  [{title}]({item["id"]}/{name})\n'
    (output / 'README.md').write_text(index, encoding='utf-8')
    return counts


def prepare(directory: Path, resume: Path, cover_letter: Path, owner_approved: bool = False) -> Path:
    candidate = json.loads((directory / 'candidate.json').read_text())
    verification = json.loads((directory / 'verification.json').read_text())
    unknown = set(verification) - set(HUMAN_VERIFICATION_FIELDS)
    if unknown:
        raise ValueError('Verification may contain only documented human evidence fields')
    job = {**candidate, **verification}
    qualification = qualify_job(job)
    if qualification['qualification_status'] != PASS:
        raise ValueError('Qualification incomplete: ' + qualification['qualification_reasons'])
    for path in (resume, cover_letter):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Resume and cover letter must be nonempty real files')
    manifest = directory / 'prepared.json'
    if manifest.exists():
        raise ValueError('Prepared packet already exists; create a new review directory for revisions')
    packet = {'schema_version': 'prepared-application.v1', 'status': 'prepared',
              'job': {**job, **qualification}, 'owner_approved': owner_approved,
              'created_at': datetime.now(timezone.utc).isoformat(),
              'candidate_sha256': digest(directory / 'candidate.json'),
              'verification_sha256': digest(directory / 'verification.json'),
              'resume': {'path': str(resume.resolve()), 'sha256': digest(resume)},
              'cover_letter': {'path': str(cover_letter.resolve()), 'sha256': digest(cover_letter)}}
    atomic_json(manifest, packet)
    return manifest


def record_submission(manifest: Path, receipt: Path, ledger: Path, submitted_at: str) -> dict:
    packet = json.loads(manifest.read_text())
    if packet.get('schema_version') != 'prepared-application.v1' or packet.get('owner_approved') is not True:
        raise ValueError('An owner-approved prepared packet is required')
    if packet.get('status') != 'prepared':
        raise ValueError('Invalid packet state')
    for field, filename in [('candidate', 'candidate.json'), ('verification', 'verification.json')]:
        if digest(manifest.parent / filename) != packet[field + '_sha256']:
            raise ValueError('Candidate or verification changed after preparation')
    for key in ('resume', 'cover_letter'):
        if digest(Path(packet[key]['path'])) != packet[key]['sha256']:
            raise ValueError('Application material changed after preparation')
    if qualify_job(packet['job'])['qualification_status'] != PASS:
        raise ValueError('Refresh expired qualification before recording submission')
    submitted = datetime.fromisoformat(submitted_at)
    if submitted.tzinfo is None or submitted > datetime.now(timezone.utc):
        raise ValueError('Submission time requires an offset and must not be in the future')
    if submitted < datetime.fromisoformat(packet['created_at']):
        raise ValueError('Submission cannot precede preparation')
    if not receipt.is_file() or not receipt.stat().st_size:
        raise ValueError('A saved ATS confirmation or sent-message receipt is required')
    # Evidence is retained privately; the export contains hashes/references only.
    job = packet['job']
    url = canonical_url(job['url'])
    entry = {'schema_version': 'confirmed-application.v1', 'status': 'submitted',
             'url': url, 'company': job['company'], 'title': job['title'],
             'search_lane': job['search_lane'], 'submitted_at': submitted.isoformat(),
             'followup_date': (submitted.date() + timedelta(days=7)).isoformat(),
             'receipt_path': str(receipt.resolve()), 'receipt_sha256': digest(receipt),
             'resume_sha256': packet['resume']['sha256'],
             'cover_letter_sha256': packet['cover_letter']['sha256'],
             'packet_sha256': digest(manifest)}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = json.loads(ledger.read_text()) if ledger.exists() else []
        for previous in existing:
            if canonical_url(previous['url']) == url:
                if previous['receipt_sha256'] != entry['receipt_sha256']:
                    raise ValueError('Submission already recorded with a different receipt')
                return previous
        atomic_json(ledger, [*existing, entry])
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--matches', type=Path, default=ROOT / 'data/matched_jobs.csv')
    build.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    build.add_argument('--per-lane', type=int, default=3)
    prep = sub.add_parser('prepare')
    prep.add_argument('--directory', type=Path, required=True)
    prep.add_argument('--resume', type=Path, required=True)
    prep.add_argument('--cover-letter', type=Path, required=True)
    prep.add_argument('--owner-approved', action='store_true', help='Only after owner reviewed this job and exact documents')
    record = sub.add_parser('record-submission')
    record.add_argument('--packet', type=Path, required=True)
    record.add_argument('--receipt', type=Path, required=True)
    record.add_argument('--submitted-at', required=True)
    record.add_argument('--ledger', type=Path, default=ROOT / 'data/confirmed_applications.json')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            print(json.dumps(build_packets(args.matches, args.output, args.per_lane)))
        elif args.command == 'prepare':
            prepare(args.directory, args.resume, args.cover_letter, args.owner_approved)
            print('Prepared locally; not submitted')
        else:
            record_submission(args.packet, args.receipt, args.ledger, args.submitted_at)
            print('Confirmed submission recorded; duplicate URLs are not appended')
    except (ValueError, KeyError, OSError) as exc:
        # Local validation messages contain no raw applicant material.
        print(f'Blocked: {exc if isinstance(exc, ValueError) else type(exc).__name__}')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
