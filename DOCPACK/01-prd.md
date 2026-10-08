---
title: Book Job Scraping — Product Requirements (PRD)
doc_id: BJS-DOC-01
doc_type: prd
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
related: 00-overview.md, 00-product-card.md, 02-architecture.md, 05-srs.md, 08-rtm.md
---

# Book Job Scraping — Product Requirements (PRD)

> ขอบเขต: job pipeline เป็นหลัก (เก็บ → จับคู่ → ตรวจ → เตรียม → ส่งด้วยมือ → บันทึกหลักฐาน) เอกสารนี้ **ไม่ใช่** การอนุญาตให้เปิด live send/apply

## 1. ปัญหาและเป้าหมาย

### 1.1 ปัญหา

| # | ปัญหา | ผลกระทบ |
|---|---|---|
| PB-1 | ประกาศงาน remote/contract กระจายบน 10+ บอร์ดและ career page ของบริษัท | เสียเวลาค้นซ้ำ พลาดงานใหม่ (ประกาศหมดอายุเร็ว) |
| PB-2 | งานจำนวนมากไม่เข้ากับเงื่อนไขจริง (full-time ไทย, onsite, exclusivity, ไม่รับคนในไทย) | เสียเวลาเตรียมใบสมัครที่ไม่มีโอกาส หรือเสี่ยงขัดกับงานปัจจุบัน |
| PB-3 | การส่งใบสมัครอัตโนมัติเสี่ยงส่งผิด ส่งซ้ำ หรือกรอกข้อมูลเดา | เสียชื่อเสียงและโอกาส |
| PB-4 | ไม่รู้ว่าส่งใบสมัครไปจริงกี่ใบ และควร follow-up เมื่อไร | ติดตามผลไม่ได้ |

### 1.2 เป้าหมาย

| ID | เป้าหมาย | ตัวชี้วัด | ค่าเป้าหมาย |
|---|---|---|---|
| G-1 | เก็บงานใหม่สม่ำเสมอ | ความสดของ 4 artifact หลัก | สดตามเกณฑ์ `PIPELINE_COLLECTION_MAX_AGE_HOURS` **[ต้องยืนยัน]** ค่าเริ่มต้น |
| G-2 | คัดเฉพาะงานที่สมัครได้จริง | สัดส่วน `PASS` ที่ผ่านการตรวจโดยคน | **[ต้องยืนยัน]** ยังไม่มี baseline |
| G-3 | ส่งใบสมัครอย่างปลอดภัย | จำนวน send อัตโนมัติที่ไม่ผ่าน gate | 0 |
| G-4 | มีหลักฐานการสมัครทุกใบ | % ใบสมัครที่ส่งแล้วมี receipt ใน `confirmed_applications.json` | 100% |
| G-5 | ผลลัพธ์ด้านอาชีพ | ใบสมัคร → สัมภาษณ์ → ข้อเสนอ | **[ต้องยืนยัน]** ยังไม่มีการวัด (card §6) |

## 2. ผู้ใช้ / persona

| ID | Persona | เป้าหมาย |
|---|---|---|
| P-OP | Operator (เจ้าของ) ในไทย | หางาน remote contract ที่ทำคู่กับงานปัจจุบันได้, หรือเปลี่ยนงานแบบ remote/relocation |
| P-DATA | `book-job-data` (ระบบ) | ได้ CSV ที่ ingest ได้เข้าสู่ `job.v1` |
| P-EXT | ผู้ใช้ภายนอก (career-prep service) | **[สมมติฐาน]** ยังไม่มี; ต้องทบทวน PDPA/ToS ก่อน |

## 3. ขอบเขต

### 3.1 In scope

- Scheduler ตาม `config/jobs.yaml` ทุก 5 นาที (เฉพาะ job ที่ถึงเวลา) พร้อม lock และ timeout
- Capture งานจากบอร์ด remote (RemoteOK, Remotive, Himalayas, Jobicy, WeWorkRemotely, Arc.dev, Dice, Wellfound ฯลฯ) และ Greenhouse public board ตาม `config/career_sources.yaml`
- Targeting policy 3 lane (`remote_contract`, `remote_career`, `relocation`) + bridge-to-hire
- Review packet, prepare แบบ immutable, record-submission พร้อม receipt, follow-up 7 วัน
- Source coverage registry (robots/terms decision ต่อบอร์ด)
- Health monitor, MCP search ภายในเครื่อง, export CSV ให้ `book-job-data`

### 3.2 Out of scope

- ส่งใบสมัคร/อีเมลอัตโนมัติในโหมดปกติ (มีโค้ดแต่ถูกล็อก)
- Analytics/lake (เป็นของ `book-job-data`)
- News, e-commerce, restaurant, finance feeds (ย้ายออกแล้ว), property (กำลังย้ายไป `book-property-scraping`)
- Hosted API, การขาย MCP แบบเสียเงิน (มีเพียงตาราง pricing ใน README)
- Social login, crawl private group, outreach อัตโนมัติ

## 4. ฟีเจอร์หลักพร้อมลำดับความสำคัญ

| ID | ฟีเจอร์ | Priority | สถานะ | FR |
|---|---|---|---|---|
| F-01 | Scheduler + lock + timeout + health | Must | มีแล้ว | FR-01, FR-11 |
| F-02 | Capture งานจากบอร์ดและ career page | Must | มีแล้ว | FR-02, FR-03 |
| F-03 | Targeting policy และ matching | Must | มีแล้ว | FR-04 |
| F-04 | Review → prepare → record-submission | Must | มีแล้ว | FR-07 |
| F-05 | Gate การส่งจริง | Must | มีแล้ว | FR-09 |
| F-06 | Source coverage และความสุภาพต่อบอร์ด | Must | มีแล้ว | FR-02, FR-10 |
| F-07 | Dedup/cleaner ภาษาไทย | Should | มีแล้ว | FR-12 |
| F-08 | Handoff CSV → `book-job-data` และ receipt → JOB-TRACKER | Should | มีแล้ว; CSV column contract ยังไม่เขียนใน repo | FR-13, FR-14 |
| F-09 | Description enrichment, tracker seeding, resume variants | Should | มีแล้ว | FR-05, FR-06, FR-08 |
| F-10 | MCP search | Could | มีแล้ว | FR-15 |
| F-11 | Discovery feeds, property, Facebook Group capture | Won't (ย้ายออก) | มีอยู่; รอย้าย | FR-16, FR-17 |

## 5. ตัวชี้วัดความสำเร็จ

| ID | ตัวชี้วัด | แหล่ง | เป้าหมาย |
|---|---|---|---|
| M-1 | Health monitor เขียว | `pipeline_health_monitor.py` | ทุก tick |
| M-2 | จำนวน `PASS` ใหม่ต่อสัปดาห์ | `matched_jobs.csv` | **[ต้องยืนยัน]** |
| M-3 | ใบสมัครที่ส่งด้วยมือพร้อม receipt ต่อเดือน | `confirmed_applications.json` | **[ต้องยืนยัน]** เจ้าของกำหนด |
| M-4 | อัตราสัมภาษณ์ต่อใบสมัคร | JOB-TRACKER | **[ต้องยืนยัน]** |
| M-5 | บอร์ดที่ถูก schedule โดยไม่มี terms decision | `source_coverage.py --check` | 0 |

## 6. Roadmap / phase

| Phase | งาน | สถานะ |
|---|---|---|
| P0 | ตัดขอบเขตเหลือ job pipeline (ย้าย property/discovery ออก) | กำลังทำ (news/e-commerce/restaurant ย้ายแล้ว 2026-09-30) |
| P1 | เขียน CSV column contract ที่ `book-job-data` ใช้ (ลิงก์ `job.v1`) | ค้าง (`PRODUCT.md` §Next improvements) |
| P2 | วัดผล funnel ใบสมัคร → สัมภาษณ์ | ค้าง |
| P3 | ปลด tracker คู่ (`apply_tracker.csv` vs JOB-TRACKER) | P1 ใน `SAFETY.md` |
| P4 | ทบทวน live ATS adapter (Lever ไม่ครบ) | ยังไม่รับรอง — manual submission เป็นเส้นทางหลัก |

## 7. ข้อสมมติฐานและความเสี่ยง

| ID | ประเภท | รายละเอียด | การจัดการ |
|---|---|---|---|
| A-1 | สมมติฐาน | เจ้าของยังหางาน/งาน contract อยู่ **[ต้องยืนยัน]** | เงื่อนไข verdict ใน card |
| A-2 | สมมติฐาน | บอร์ดที่ใช้ยังอนุญาตการเข้าถึงตาม terms ที่บันทึก | `source_coverage.py --check` |
| R-1 | ความเสี่ยง | ขอบเขตกว้าง (125 ไฟล์ `.py` ใน `scripts/`) ดูแลยาก | ย้าย lane ที่ไม่ใช่งานออก |
| R-2 | ความเสี่ยง | บอร์ดเปลี่ยน HTML/API หรือบล็อก (เช่น DDproperty Cloudflare 403) | health monitor + disable job |
| R-3 | ความเสี่ยง | เผลอปลด send gate | gate 3 ชั้น + PASS + APPROVED, ห้ามตั้ง unlock ใน CI |
| R-4 | ความเสี่ยง | ข้อมูลส่วนบุคคล (contact, resume) รั่ว | `data/` ถูก gitignore, receipt เก็บ private |
| R-5 | ความเสี่ยง | ขัดกับสัญญางานปัจจุบัน | policy ปฏิเสธ exclusivity; ต้องตรวจ conflict ก่อน APPROVED |

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `README.md` (Scheduled Jobs, Job Application Automation Pipeline), `PRODUCT.md`, `SAFETY.md`, `CAREER-WORKFLOW.md`, `BOUNDARY.md`
- `config/jobs.yaml`, `config/job_targeting.yaml`, `config/career_sources.yaml`, `config/source_coverage.yaml`
- `DOCPACK/00-product-card.md`
