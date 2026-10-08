---
title: Book Job Scraping — Software Requirements (SRS)
doc_id: BJS-DOC-05
doc_type: srs
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: BA (Book Dev)
related: 01-prd.md, 02-architecture.md, 06-ux-flows.md, 07-test-uat.md, 08-rtm.md
---

# Book Job Scraping — Software Requirements (SRS)

## 1. บทบาทและสิทธิ์

ไม่มีระบบ login; สิทธิ์มาจากการเข้าถึงเครื่องและ env

| บทบาท | ทำได้ | ทำไม่ได้ |
|---|---|---|
| Scheduler (อัตโนมัติ) | รัน job collection ที่เปิด + health | ส่งใบสมัคร, แจ้งเตือนภายนอกโดยไม่อนุมัติ |
| Operator | รันทุกสคริปต์, กรอก `verification.json`, prepare, record-submission | ส่งจริงโดยไม่ผ่าน gate |
| Owner (approver) | ใส่ `--owner-approved`, ตั้ง `application_readiness=APPROVED`, ตั้ง unlock env | — |
| Reviewer (lane property) | บันทึกการตัดสินใจด้วย reviewer ID | เลื่อนเป็น `approved_to_contact` หรือส่งข้อความ |
| ระบบภายนอก (`book-job-data`) | อ่านไฟล์ CSV | เขียนกลับเข้า repo นี้ |

## 2. User story และ acceptance criteria

| ID | Story | Acceptance criteria |
|---|---|---|
| US-01 | ในฐานะ operator ฉันต้องการให้ระบบเก็บงานใหม่เอง | ทุก 5 นาที รันเฉพาะ job ที่ถึงเวลา; ไม่มี tick ซ้อน; step เกินเวลาถูก kill และ tick exit 124 |
| US-02 | ในฐานะ operator ฉันต้องการงานจากหลายบอร์ดในไฟล์เดียว | `job_postings.csv` รวมทุกแหล่ง; history บันทึกครั้งแรกที่เห็น; เคารพ rate limit และ `Retry-After` |
| US-03 | ในฐานะ operator ฉันต้องการงานจาก career page บริษัทเป้าหมาย | `career_discovery.py --write` ใช้ GET กับ Greenhouse; บอร์ดใดล้ม → ไม่ทับ capture เดิม; ผลว่างต่างจากแหล่งล่ม |
| US-04 | ในฐานะ operator ฉันต้องการเห็นเฉพาะงานที่สมัครได้ | ทุก match ได้ `PASS`/`VERIFY`/`REJECT` ตาม lane; full-time ไทย, onsite/hybrid, exclusivity → REJECT ใน `remote_contract`; volunteer/internship → VERIFY |
| US-05 | ในฐานะ operator ฉันต้องการแพ็กเก็ตตรวจงาน | `application_review.py build --per-lane N` สร้าง snapshot, checklist ไทย, `verification.json` ว่าง; ไม่ทับแพ็กเก็ตเดิม |
| US-06 | ในฐานะ operator ฉันต้องการเตรียมเอกสารอย่างตรวจย้อนได้ | `prepare` ต้องมี verification ครบและอายุ ≤ 7 วัน; เขียน `prepared.json` พร้อม hash; ไม่ส่ง |
| US-07 | ในฐานะ operator ฉันต้องการบันทึกการสมัครที่ส่งจริง | `record-submission` ต้องมี packet ที่ owner-approved, เอกสารไม่ถูกแก้, receipt ไม่ว่าง; dedup URL; ตั้ง follow-up +7 วัน |
| US-08 | ในฐานะเจ้าของ ฉันต้องการให้การส่งจริงถูกล็อก | sender ทุกตัวปฏิเสธถ้าขาด flag, env 2 ตัว, `PASS` หรือ `APPROVED` |
| US-09 | ในฐานะ operator ฉันต้องการรู้ว่าระบบปกติไหม | `--health` เขียวเมื่อ 4 artifact สด; ไม่ต้องใช้ AI/Telegram |
| US-10 | ในฐานะ data product ฉันต้องการไฟล์ที่ ingest ได้ | CSV อยู่ใน `data/`; คอลัมน์ตาม `job.v1` **[ต้องยืนยัน]** contract |
| US-11 | ในฐานะ operator ฉันต้องการค้นข้อมูลที่เก็บแล้วผ่าน AI agent | MCP tools `search_jobs`, `search_businesses`, `get_product_prices`, `get_news` อ่าน storage ในเครื่อง |

## 3. Functional requirements

| ID | Requirement | Priority | Phase | สถานะ |
|---|---|---|---|---|
| FR-01 | Scheduler จาก `config/jobs.yaml` (`main.py run/status/enable/disable`), lock, timeout, log rotate | Must | ปัจจุบัน | มีแล้ว |
| FR-02 | Capture งานจากบอร์ด remote 10+ แหล่งผ่าน `http_policy` | Must | ปัจจุบัน | มีแล้ว |
| FR-03 | Career discovery จาก Greenhouse public boards (`config/career_sources.yaml`) | Must | ปัจจุบัน | มีแล้ว |
| FR-04 | Targeting policy 3 lane + bridge-to-hire → `matched_jobs.csv` | Must | ปัจจุบัน | มีแล้ว |
| FR-05 | Description enrichment (`scrape_job_descriptions.py --top N`), OpenRouter ทางเลือก | Should | ปัจจุบัน | มีแล้ว |
| FR-06 | Seed tracker เฉพาะ `PASS` เป็น `discovered` | Should | ปัจจุบัน | มีแล้ว |
| FR-07 | Review packet → prepare → record-submission → `confirmed_applications.json` | Must | ปัจจุบัน | มีแล้ว |
| FR-08 | Draft generators (`auto_apply.py` → `prepared`, tailor resume, cover letter, resume variants) | Should | ปัจจุบัน | มีแล้ว |
| FR-09 | Live send gate สำหรับ sender ทุกตัว | Must | ปัจจุบัน | มีแล้ว |
| FR-10 | Source coverage registry + `--check` | Must | ปัจจุบัน | มีแล้ว |
| FR-11 | Health monitor ของ 4 artifact | Must | ปัจจุบัน | มีแล้ว |
| FR-12 | Cleaner ไทย (zero-width, sara am), dedup ด้วย content hash, exact host match | Should | ปัจจุบัน | มีแล้ว |
| FR-13 | Export CSV ให้ `book-job-data` | Should | ปัจจุบัน | มีแล้ว; contract ยังไม่เขียน |
| FR-14 | Handoff receipt metadata → JOB-TRACKER (สคริปต์ฝั่ง Solo Empire) | Should | ปัจจุบัน | มีแล้ว |
| FR-15 | MCP search tools 4 ตัว | Could | ปัจจุบัน | มีแล้ว |
| FR-16 | Lane property + Chrome extension + Facebook Group import/review | Won't (ย้าย) | — | มีอยู่ รอย้าย |
| FR-17 | Discovery feeds (GitHub trending, HN, dev.to, Product Hunt) + scraper dashboard | Could | — | เปิดอยู่; เจ้าของปลายทาง **[ต้องยืนยัน]** |

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| BA (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |
| Product owner | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `main.py`, `config/*.yaml`, `scripts/application_review.py`, `scripts/job_target_policy.py`, `scripts/safety.py`, `mcp_server/server.py`
- `README.md`, `SAFETY.md`, `CAREER-WORKFLOW.md`, `PRODUCT.md`
