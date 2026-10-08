---
title: Book Job Scraping — NFR และความปลอดภัย
doc_id: BJS-DOC-03
doc_type: nfr-security
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Solution Architect + Security (Book Dev)
related: 02-architecture.md, 04-runbook.md, 07-test-uat.md
---

# Book Job Scraping — NFR และความปลอดภัย

## 1. NFR พร้อมเป้าหมายที่วัดได้

| ID | หมวด | ข้อกำหนด | เป้าหมาย | หลักฐาน |
|---|---|---|---|---|
| NFR-01 | Safety | ไม่มีการส่งอีเมล/ATS โดยไม่ผ่าน gate ทั้งหมด | 0 ครั้ง | `test_paths_and_safety.py` (17 test ตาม `PRODUCT.md`) |
| NFR-02 | Freshness | artifact หลัก 4 ไฟล์สด | jobs ทุก 6 ชม.; เกณฑ์อายุตาม `PIPELINE_COLLECTION_MAX_AGE_HOURS` | `pipeline_health_monitor.py`, `test_health_staleness.py` |
| NFR-03 | Reliability | ไม่มี tick ซ้อน; step ที่ค้างถูก kill ทั้ง process tree | collection ≤ 45 นาที, health ≤ 5 นาที, tick exit 124 เมื่อ timeout | `test_scheduled_run.py`, `test_file_lock.py` |
| NFR-04 | Integrity | tick ที่ถูก kill ไม่ทำให้ไฟล์ store ขาด | เขียน temp + `os.replace` | `test_atomic_writes.py`, `test_json_log_recovery.py` |
| NFR-05 | Politeness | ต่อ host ≤ 1 request ต่อ `rate_limit` วินาที; retry ≤ 3 | ตาม `config/jobs.yaml` (`job_postings` 2.0 วินาที) | `test_http_policy.py` |
| NFR-06 | Compliance | ไม่มีบอร์ดที่ไม่มี terms decision หรือถูก `blocked` ถูก schedule | 0 | `source_coverage.py --check`, `test_source_coverage.py` |
| NFR-07 | Log hygiene | `cron.log` rotate | ที่ 5 MB | README §Collection health |
| NFR-08 | Portability | Windows + Linux | CI รัน Windows scheduler tests | `.github/workflows/ci.yml` |
| NFR-09 | Performance | เวลารันต่อ tick | **[ต้องยืนยัน]** ยังไม่มีการวัด | — |
| NFR-10 | Data quality | dedup URL/fingerprint, ตรงกับ host แบบ exact | ไม่มีงานซ้ำใน history | `test_job_history_dedup.py`, git log 2026-09-30 |

## 2. Security controls

| ID | Control | รายละเอียด |
|---|---|---|
| SEC-01 | Send gate | ต้องมี `--send`/`--apply` + `BOOK_JOB_LIVE_SEND_ENABLED=1` + `BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND` + `qualification_status=PASS` + `application_readiness=APPROVED` |
| SEC-02 | Preview-only | `ats_auto_apply.py --test` ไม่เปิด Chrome ไม่ submit; `auto_apply.py` เขียนเฉพาะ `prepared` |
| SEC-03 | Immutable prepare | `prepared.json` เก็บ hash ของเอกสาร/candidate/verification; แก้แล้วต้องสร้าง packet ใหม่; verification อายุ ≤ 7 วัน |
| SEC-04 | No runtime pip | สคริปต์ห้าม `pip install` ระหว่างรัน (ใช้ venv + `requirements.txt`) |
| SEC-05 | Secrets | ค่าอยู่ใน secret store ส่วนตัว; ห้าม commit `.env`, tracker CSV, browser profile, PII (`RUNBOOK.md`, `BOUNDARY.md`) |
| SEC-06 | Browser profile | Facebook background capture ใช้ profile แยกนอก repo; ไม่อ่าน cookies/`storage_state`; ไม่ auto-login |
| SEC-07 | Chrome extension | อ่านเฉพาะข้อความที่ render ในแท็บที่ operator กด capture; permission `activeTab`, `storage`, `contextMenus`, `downloads` และ host permission รวม `<all_urls>` **[ต้องยืนยัน]** ความจำเป็นของ `<all_urls>` |
| SEC-08 | Social lane gate | `BRAVE_SEARCH_STORAGE_APPROVED`, `PROPERTY_SOCIAL_RETENTION_UNTIL`, `PROPERTY_SOCIAL_TERMS_BASIS_REF` ต้องตั้งก่อนเก็บผลค้นหา; ค่าเริ่มต้นปิด |
| SEC-09 | CI | `permissions: contents: read`; ห้ามตั้ง unlock env ใน CI |
| SEC-10 | Process security | test เฉพาะ (`test_process_security.py`) **[ต้องยืนยัน]** ขอบเขตที่ตรวจ |

## 3. Privacy / PDPA

- ข้อมูลส่วนบุคคลของ operator: resume, cover letter, receipt — เก็บใน path ส่วนตัวที่ไม่ commit; JOB-TRACKER รับเฉพาะ metadata
- ข้อมูลบุคคลที่สาม: อีเมล/contact ของ recruiter (สคริปต์ `find_contact_emails.py`, `extract_hn_emails.py`) และ contact ใน lane property/social — ต้องมีวัตถุประสงค์ ฐานทางกฎหมาย ระยะเวลาเก็บ และทางลบ ตามที่ `SAFETY.md` อ้าง PDPC notice; ปัจจุบัน lane social ปิดและแถวเริ่มที่ `pending`/`not_contacted`
- สถานะการใช้งานจริงของสคริปต์เก็บอีเมล recruiter **[ต้องยืนยัน]**
- `book-job-data` จัด `job.v1` เป็น privacy class internal (`PRODUCT.md`)

## 4. Observability

| สัญญาณ | ที่มา |
|---|---|
| Health | `pipeline_runner.py --health`, `pipeline_health_monitor.py` (disk, scheduler, ความสด, integration ทางเลือก) |
| Scheduler | `main.py status`, `data/schedule_state.json`, `cron.log` |
| ต่อ run | จำนวน request/retry/failure และ scraped/new ที่ scheduler บันทึก |
| Dashboard | `scripts/scraper_dashboard.py` → `data/briefings/scraper_dashboard.json` (08:15, 11:15, 20:15) |
| Alert | Telegram (ทางเลือก, ต้องอนุมัติ) |

## 5. Backup / DR

- `scripts/pipeline_backup.py` และ `pipeline_recovery.py` มีอยู่ **[ต้องยืนยัน]** ว่าถูกใช้ตามตารางหรือไม่
- `data/` เป็น runtime ที่ gitignore: สูญหายได้ถ้าเครื่องเสีย ส่วนที่สำคัญที่สุดคือ `confirmed_applications.json` และ `career-review/` (หลักฐานการสมัคร)
- RPO/RTO ไม่ได้กำหนด **[ต้องยืนยัน]**; ข้อเสนอ **[สมมติฐาน]** สำรอง `data/confirmed_applications.json` และ `career-review/` รายวันไปยัง backup ส่วนตัว
- Capture ส่วนใหญ่สร้างใหม่ได้จากการรัน scraper (ยกเว้นงานที่หมดอายุไปแล้ว)

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Solution Architect (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |
| Security reviewer | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `SAFETY.md`, `CAREER-WORKFLOW.md`, `PRODUCT.md`, `BOUNDARY.md`, `RUNBOOK.md`, `README.md`
- `scripts/safety.py`, `scripts/http_policy.py`, `scripts/scheduled_run.py`, `scripts/file_lock.py`
- `chrome-extension/manifest.json`, `.github/workflows/ci.yml`, `tests/`
