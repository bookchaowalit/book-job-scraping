---
title: Book Job Scraping — ภาพรวมระบบและสารบัญเอกสาร
doc_id: BJS-DOC-00
doc_type: overview
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
related: 00-product-card.md, 01-prd.md, 02-architecture.md, 03-nfr-security.md, 04-runbook.md, 05-srs.md, 06-ux-flows.md, 07-test-uat.md, 08-rtm.md
---

# Book Job Scraping — ภาพรวมระบบและสารบัญเอกสาร

## 1. สรุประบบ

Book Job Scraping เป็นเครื่องมือ Python สำหรับ operator คนเดียว ทำหน้าที่ **producer** ของข้อมูลงาน: เก็บประกาศงาน remote/contract และ career จากบอร์ดสาธารณะตามตารางเวลา, จัดประเภทด้วยนโยบาย contract-first (`PASS`/`VERIFY`/`REJECT`), เตรียมแพ็กเก็ตใบสมัครให้คนตรวจ และบันทึกใบสมัครที่ส่งด้วยมือพร้อมหลักฐาน การส่งอีเมล/ATS จริงถูกล็อกไว้หลัง gate หลายชั้น ข้อมูลส่งต่อเป็นไฟล์ CSV ให้ `book-job-data` ingest เข้าสู่ lake (`job.v1`) โดย repo นี้ไม่เขียนฐานข้อมูลของระบบอื่น นอกจากนี้ยังมี lane รอง (discovery feeds, property, Facebook Group capture) ที่อยู่ระหว่างย้ายไป repo เจ้าของ

## 2. สถานะปัจจุบัน

| หัวข้อ | สถานะ | หลักฐาน |
|---|---|---|
| Scheduler | ทำงานทุก 5 นาทีบน Windows Task Scheduler (ย้ายจาก Linux 2026-09-30) | `PRODUCT.md` §Current runtime state |
| Jobs ที่เปิด | 9 jobs ตาม README/PRODUCT; ตรวจ `config/jobs.yaml` รอบนี้พบ `enabled: true` 9 job (`github_trending`, `hackernews`, `devto_articles`, `producthunt_top`, `property_listings`, `job_postings`, `career_postings`, `job_match_filter`, `scraper_dashboard`) | `config/jobs.yaml` |
| Runtime snapshot ล่าสุดที่บันทึก | 1,647 postings, 118 matches, 106 tracker rows (`discovered`), 10 descriptions, 5 resume variants (2026-08-24) **[ต้องยืนยัน]** ค่าปัจจุบัน | `README.md`, `RUNBOOK.md` |
| Live send/apply | ล็อกโดยค่าเริ่มต้น; ไม่มี cron ที่ส่งใบสมัคร | `SAFETY.md` |
| CI | GitHub Actions: Ubuntu (ruff + pytest offline) และ Windows (scheduler tests) | `.github/workflows/ci.yml` |
| Test | 36 ไฟล์ `tests/test_*.py`; รอบนี้รันชุด scheduler + safety ได้ 29 passed | `07-test-uat.md` |
| Deploy / live URL | ไม่มี — รันบนเครื่อง operator | `00-product-card.md` |
| Commit | 34 commits (2026-07-09 ถึง 2026-10-01) | `git log` |

## 3. ผู้ใช้หลัก

| ผู้ใช้ | บทบาท |
|---|---|
| Operator (เจ้าของ) | ผู้ใช้คนเดียว: ตรวจรายการงาน, เตรียมเอกสาร, ส่งใบสมัครด้วยมือ, บันทึกหลักฐาน |
| `book-job-data` | ผู้บริโภคไฟล์ CSV (ingest → Bronze `job.v1` → API `:8109`) |
| Solo Empire `JOB-TRACKER` | ปลายทางบันทึกใบสมัครที่ยืนยันแล้ว (ผ่าน `import_job_applications.py`) |
| ผู้ใช้ภายนอก | ไม่มี; README มี pricing ของ MCP แต่ไม่ใช่หลักฐานรายได้ (`PRODUCT.md` §Claim hygiene) |

## 4. ตารางรายการเอกสาร

| รหัส | ไฟล์ | ชื่อ | ผู้อ่านหลัก |
|---|---|---|---|
| CARD-book-job-scraping | `00-product-card.md` | Product Card | Product owner |
| BJS-DOC-00 | `00-overview.md` | ภาพรวมระบบและสารบัญเอกสาร | ทุกคน |
| BJS-DOC-01 | `01-prd.md` | Product Requirements (PRD) | Product owner |
| BJS-DOC-02 | `02-architecture.md` | System Architecture | Solution Architect, นักพัฒนา |
| BJS-DOC-03 | `03-nfr-security.md` | NFR และความปลอดภัย | Solution Architect, Security |
| BJS-DOC-04 | `04-runbook.md` | Runbook การติดตั้งและดูแลระบบ | Operator |
| BJS-DOC-05 | `05-srs.md` | Software Requirements (SRS) | BA, นักพัฒนา |
| BJS-DOC-06 | `06-ux-flows.md` | User Flow และ Screen Inventory | UX/UI, Operator |
| BJS-DOC-07 | `07-test-uat.md` | Test Strategy และ UAT | QA |
| BJS-DOC-08 | `08-rtm.md` | Requirements Traceability Matrix | BA + QA |

## 5. วิธีอ่าน

1. อ่าน `00-product-card.md` (verdict `invest` พร้อมเงื่อนไขตัดขอบเขต) แล้ว `01-prd.md`
2. เรื่องความปลอดภัยของการส่งใบสมัครอ่าน `03-nfr-security.md` คู่กับ `SAFETY.md` (ฉบับเต็ม)
3. Operator อ่าน `04-runbook.md` และ `06-ux-flows.md` คู่กับ `CAREER-WORKFLOW.md`
4. เอกสารชุดนี้เน้น **job pipeline**; lane property/Facebook Group บันทึกเท่าที่จำเป็นเพราะกำลังย้ายไป `book-property-scraping`

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `README.md`, `PRODUCT.md`, `SAFETY.md`, `BOUNDARY.md`, `CAREER-WORKFLOW.md`, `RUNBOOK.md`
- `config/jobs.yaml`, `.github/workflows/ci.yml`
- `DOCPACK/00-product-card.md`
