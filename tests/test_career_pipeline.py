from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from application_review import build_packets, prepare, record_submission
from career_discovery import collect, normalize_board, write_capture
from filter_job_matches import main as filter_matches
from job_target_policy import qualify_job, is_approved_for_submission, sponsorship_signal


class CareerPipelineTests(unittest.TestCase):
    def relocation(self):
        return {'title': 'Full-time Python Engineer', 'company': 'Example',
                'location': 'Tokyo, Japan', 'source': 'Greenhouse:example',
                'description': 'Hybrid. We provide visa sponsorship and relocation support.',
                'url': 'https://job-boards.greenhouse.io/example/jobs/123',
                'search_lane': 'relocation'}

    def evidence(self):
        return {'verified_role_requirements': 'YES', 'verified_destination_country': 'Japan', 'verified_destination_eligibility': 'YES', 'verified_career_transition': 'YES',
                'verified_employment_terms': 'YES', 'verified_at': date.today().isoformat(),
                'verification_source_url': 'https://example.test/careers/123',
                'verification_notes': 'Fixture only: employer terms, work rights and transition reviewed.'}

    def test_relocation_is_retained_without_assuming_work_rights(self):
        result = qualify_job(self.relocation())
        self.assertEqual(result['qualification_status'], 'VERIFY')
        self.assertEqual(result['thailand_eligibility'], 'NO')
        self.assertEqual(result['application_readiness'], 'REVIEW_REQUIRED')

    def test_verified_relocation_does_not_require_two_concurrent_jobs(self):
        result = qualify_job({**self.relocation(), **self.evidence()})
        self.assertEqual(result['qualification_status'], 'PASS')
        self.assertEqual(result['concurrent_employment'], 'OVERLAP_RISK')
        self.assertEqual(result['application_readiness'], 'REVIEW_REQUIRED')

    def test_no_sponsorship_requires_existing_work_rights(self):
        row = {**self.relocation(), 'description': 'Hybrid. No visa sponsorship available.'}
        self.assertEqual(qualify_job(row)['visa_sponsorship'], 'NO')
        self.assertEqual(qualify_job(row)['qualification_status'], 'VERIFY')
        row.update(self.evidence(), verified_destination_eligibility='NO')
        self.assertEqual(qualify_job(row)['qualification_status'], 'REJECT')

    def test_question_and_search_label_are_not_sponsorship(self):
        self.assertEqual(sponsorship_signal('Do you require visa sponsorship?'), 'VERIFY')
        row = {'title': 'Python Engineer', 'location': 'Remote',
               'keyword': 'visa support relocation support', 'tags': 'visa support relocation support'}
        self.assertEqual(qualify_job(row)['search_lane'], 'remote_contract')
        row['description'] = 'We do not provide visa assistance or relocation support.'
        self.assertEqual(qualify_job(row)['visa_sponsorship'], 'NO')
        self.assertEqual(qualify_job(row)['search_lane'], 'remote_contract')

    def test_hybrid_cloud_is_not_hybrid_office_work(self):
        result = qualify_job({'title': 'Full-time Python Engineer', 'location': 'Home Based - APAC',
                              'description': 'Build hybrid cloud infrastructure remotely.'})
        self.assertEqual(result['work_arrangement'], 'Remote')
        self.assertEqual(result['search_lane'], 'remote_career')

    def test_taiwan_remote_is_not_thailand_remote(self):
        row = {**self.relocation(), 'search_lane': 'remote_career',
               'location': 'Taipei, Taiwan', 'description': 'Remote software development.'}
        self.assertEqual(qualify_job(row)['qualification_status'], 'REJECT')

    def test_home_based_with_company_events_remains_remote(self):
        result = qualify_job({'title': 'Full-time Python Engineer', 'location': 'Home Based - APAC',
                              'description': 'Meet colleagues in person twice a year at company events.'})
        self.assertEqual(result['work_arrangement'], 'Remote')

    def test_remote_career_requires_explicit_thailand_evidence(self):
        row = {**self.relocation(), 'search_lane': 'remote_career', 'location': 'Worldwide',
               'description': 'Full-time remote role.', **self.evidence()}
        self.assertEqual(qualify_job(row)['qualification_status'], 'VERIFY')
        row['verified_thailand_eligibility'] = 'YES'
        self.assertEqual(qualify_job(row)['qualification_status'], 'PASS')
        row.update(location='US only', verified_thailand_eligibility='')
        self.assertEqual(qualify_job(row)['qualification_status'], 'REJECT')

    def test_stale_and_future_verification_cannot_authorize(self):
        for days in [-8, 1]:
            row = {**self.relocation(), **self.evidence(), 'qualification_status': 'PASS',
                   'application_readiness': 'APPROVED',
                   'verified_at': (date.today() + timedelta(days=days)).isoformat()}
            self.assertEqual(qualify_job(row)['qualification_status'], 'VERIFY')
            self.assertFalse(is_approved_for_submission(row))

    def test_missing_source_notes_prevents_pass(self):
        row = {**self.relocation(), **self.evidence(), 'verification_notes': ''}
        self.assertEqual(qualify_job(row)['qualification_status'], 'VERIFY')

    def test_source_adapter_does_not_invent_visa_support(self):
        payload = {'jobs': [{'id': 123, 'title': 'Full-time Python Engineer',
                            'location': {'name': 'Worldwide'},
                            'content': '<p>Remote. Do you require visa sponsorship?</p>'}]}
        rows = normalize_board(payload, 'example', 'Example', datetime.now(timezone.utc).isoformat())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['search_lane'], 'remote_career')
        self.assertEqual(qualify_job(rows[0])['visa_sponsorship'], 'VERIFY')

    def test_partial_failure_never_returns_complete_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'sources.yaml'
            config.write_text('greenhouse_boards:\n  - {board: one, company: One}\n  - {board: two, company: Two}\n')
            def fetch(board):
                if board == 'two':
                    raise ValueError('failed source')
                return {'jobs': []}
            with self.assertRaises(ValueError):
                collect(config, fetch)

    def test_capture_to_match_to_preparation_to_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, matches, output = root/'raw.csv', root/'matched.csv', root/'review'
            payload = {'jobs': [{'id': 123, 'title': 'Full-time Python Engineer',
                                'location': {'name': 'Tokyo, Japan'},
                                'content': '<p>Hybrid. We provide visa sponsorship and relocation support.</p>'}]}
            rows = normalize_board(payload, 'example', 'Example', datetime.now(timezone.utc).isoformat())
            write_capture(rows, raw)
            filter_matches(input=str(raw), output=str(matches), descriptions=str(root/'none.csv'), top=0)
            self.assertEqual(build_packets(matches, output), {'relocation': 1})
            job_id = json.loads((output/'index.json').read_text())['items'][0]['id']
            directory = output/job_id
            candidate_before = (directory/'candidate.json').read_bytes()
            build_packets(matches, output)
            self.assertEqual((directory/'candidate.json').read_bytes(), candidate_before)
            resume, letter, receipt = root/'resume.txt', root/'letter.txt', root/'receipt.txt'
            resume.write_text('Synthetic resume fixture')
            letter.write_text('Synthetic tailored cover letter fixture')
            with self.assertRaises(ValueError):
                prepare(directory, resume, letter, owner_approved=True)
            (directory/'verification.json').write_text(json.dumps(self.evidence()))
            manifest = prepare(directory, resume, letter, owner_approved=True)
            self.assertEqual(json.loads(manifest.read_text())['status'], 'prepared')
            self.assertFalse((root/'ledger.json').exists())
            with self.assertRaises(ValueError):
                record_submission(manifest, receipt, root/'ledger.json', datetime.now(timezone.utc).isoformat())
            receipt.write_text('Synthetic ATS confirmation fixture; no real application')
            entry = record_submission(manifest, receipt, root/'ledger.json', datetime.now(timezone.utc).isoformat())
            self.assertEqual(entry['status'], 'submitted')
            record_submission(manifest, receipt, root/'ledger.json', datetime.now(timezone.utc).isoformat())
            self.assertEqual(len(json.loads((root/'ledger.json').read_text())), 1)
            letter.write_text('changed document')
            with self.assertRaises(ValueError):
                record_submission(manifest, receipt, root/'ledger.json', datetime.now(timezone.utc).isoformat())

    def test_supplemental_input_preserves_lane_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, supplemental, matches = root/'raw.csv', root/'extra.csv', root/'matches.csv'
            write_capture([], raw)
            row = self.relocation()
            from career_discovery import FIELDS
            write_capture([{key: row.get(key, '') for key in FIELDS}], supplemental)
            filter_matches(input=str(raw), supplemental_input=str(supplemental), output=str(matches),
                           descriptions=str(root/'none'), top=0)
            with matches.open() as handle:
                result = list(csv.DictReader(handle))
            self.assertEqual(result[0]['search_lane'], 'relocation')
            self.assertIn('visa sponsorship', result[0]['description'])


if __name__ == '__main__':
    unittest.main()
