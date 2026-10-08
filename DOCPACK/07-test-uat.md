---
title: Book Job Scraping — Test Strategy และ UAT
doc_id: BJS-DOC-07
doc_type: test-uat
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: QA (Book Dev)
related: 03-nfr-security.md, 05-srs.md, 08-rtm.md
---

# Book Job Scraping — Test Strategy และ UAT

## 1. ระดับการทดสอบ

| ระดับ | เครื่องมือ | ขอบเขต | หมายเหตุ |
|---|---|---|---|
| Unit / integration (offline) | pytest (`pytest.ini` → `tests/`) | 36 ไฟล์ `test_*.py`: core pipeline, scheduler, safety, targeting, career pipeline, source coverage, http policy, dedup, property/Facebook lane, feeds | ไม่ต่อเครือข่าย |
| Fixture E2E | `tests/test_career_pipeline.py` | capture → match → review → prepare → receipt ledger | ไม่ส่งใบสมัครจริง |
| Windows scheduler | pytest บน `windows-latest` | `test_file_lock.py`, `test_scheduled_run.py`, `test_atomic_writes.py` | stdlib เท่านั้น |
| Static | ruff `--select E9,F63,F7,F82` | syntax / undefined names | ไม่ใช่ lint เต็ม |
| Live probe | `scripts/test_ats_autoapply.py` | ATS จริง | ตั้งใจไม่รวมใน suite |
| Parent integration | Solo Empire `infra/tests/data_lake/job_application_import_test.py` | import receipt เข้า JOB-TRACKER | อยู่นอก repo |
| UAT | operator ใช้งานจริง | flow ใน `06-ux-flows.md` §2.1 | ยังไม่มีบันทึกผล funnel **[ต้องยืนยัน]** |

## 2. สภาพแวดล้อม

- CI Ubuntu: Python 3.11, `pip install -r requirements.txt pytest ruff`, `PYTHONUTF8=1`
- CI Windows: Python 3.11 + pytest
- Local: `.venv` ของ repo (`requirements.txt`)

## 3. Test cases

| ID | FR | กรณีทดสอบ | ผลคาดหวัง | หลักฐานอัตโนมัติ |
|---|---|---|---|---|
| TC-01 | FR-01 | tick ซ้อน | tick ที่สองข้ามเพราะ lock | `test_file_lock.py`, `test_scheduled_run.py` |
| TC-02 | FR-01 | step เกิน timeout | kill ทั้ง process tree, exit 124 | `test_scheduled_run.py` |
| TC-03 | FR-01 | tick ถูก kill ระหว่างเขียน store | ไฟล์ไม่ขาด | `test_atomic_writes.py`, `test_json_log_recovery.py` |
| TC-04 | FR-02 | host ตอบ 429 พร้อม `Retry-After` | retry ตามเวลา ≤ 3 ครั้ง สูงสุด 60 วินาที | `test_http_policy.py` |
| TC-05 | FR-03, FR-07 | fixture E2E career pipeline รวมกรณี qualification ไม่ครบ, approval เก่า, เอกสารถูกแก้, บันทึกซ้ำ | ถูกปฏิเสธทุกกรณีผิด; กรณีถูกบันทึกครั้งเดียว | `test_career_pipeline.py` |
| TC-06 | FR-04 | งาน full-time ไทย/onsite/exclusivity/upfront fee | `REJECT`; volunteer → `VERIFY` | `test_job_target_policy.py` |
| TC-07 | FR-09 | sender ขาด gate ใดก็ได้ | ไม่ส่ง; `--test` เป็น preview | `test_paths_and_safety.py` |
| TC-08 | FR-10 | บอร์ดไม่มี terms decision ถูก schedule | `--check` fail | `test_source_coverage.py` |
| TC-09 | FR-11 | artifact เก่าเกินเกณฑ์ | health แดง | `test_health_staleness.py` |
| TC-10 | FR-12 | ข้อความไทยมี zero-width/sara am, URL ซ้ำ | normalize และ dedup ถูก | `test_core_pipeline.py`, `test_job_history_dedup.py`, `test_use_cases_and_storage.py` |
| TC-11 | FR-15 | ค้นผ่าน `SearchUseCase` | คืนผลจาก storage | `test_use_cases_and_storage.py` **[ต้องยืนยัน]** ครอบคลุม MCP โดยตรงหรือไม่ |
| TC-12 | FR-16 | property/Facebook capture และ import | quarantine แถว private/unknown; `pending`/`not_contacted` | `test_property_*.py`, `test_facebook_group_*.py`, `test_chrome_extension_property_capture.py` |
| TC-13 | FR-13 | CSV ingest โดย `book-job-data` | ingest ผ่าน `job.v1` | ไม่มีใน repo นี้ — ช่องว่าง |
| TC-14 | FR-05, FR-06, FR-08 | enrichment, seed tracker, draft | `prepared` เท่านั้น ไม่ `submitted` | **[ต้องยืนยัน]** — ไม่พบ test เฉพาะชื่อ |
| TC-U1 | FR-07 | Operator ส่งใบสมัครจริง 1 งานตาม flow และ import เข้า JOB-TRACKER | มี receipt + แถวใน tracker + follow-up date | **[ต้องยืนยัน]** |

## 4. เกณฑ์ผ่าน (entry / exit)

- Entry: `.venv` ครบตาม `requirements.txt`, ไม่มี unlock env ใน shell
- Exit สำหรับ merge: CI ทั้ง 2 job เขียว
- Exit สำหรับเปิด job ใหม่: smoke ที่ bounded ให้ผลตรง contract + terms decision ใน `source_coverage.yaml`
- Exit สำหรับส่งใบสมัคร: ผ่าน flow §2.1 ทุกขั้น (ไม่ใช้ sender อัตโนมัติ)

## 5. หลักฐานที่มี

| หลักฐาน | วันที่ | ผล |
|---|---|---|
| รอบเขียนเอกสารนี้: `pytest -q -p no:cacheprovider tests/test_file_lock.py tests/test_scheduled_run.py tests/test_atomic_writes.py tests/test_paths_and_safety.py` (venv `.runtime/venv-services` ของ Solo Empire) | 2026-10-08 | **29 passed** ใน 4.5 วินาที |
| ความพยายามรัน `test_job_target_policy.py` และอื่น ๆ | 2026-10-08 | ไม่ได้รัน — เครื่องนี้ไม่มี venv ที่มี `requirements.txt` ครบ (`scripts/scrape_job_postings.py` หยุดด้วย Missing dependency); ไม่ติดตั้งเพิ่มตามข้อห้าม |
| Safety tests 17/17 | 2026-08-11, 2026-08-24 | ผ่าน (`PRODUCT.md`, `RUNBOOK.md`) |
| Collection health "All systems healthy" | 2026-08-24 | ผ่าน (`RUNBOOK.md`) |
| CI run ล่าสุด | — | **[ต้องยืนยัน]** |

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| QA (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `tests/`, `pytest.ini`, `.github/workflows/ci.yml`
- `CAREER-WORKFLOW.md` §Verification, `PRODUCT.md`, `RUNBOOK.md`, `SAFETY.md`
- ผลรัน pytest 2026-10-08
