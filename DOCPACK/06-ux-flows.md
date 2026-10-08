---
title: Book Job Scraping — User Flow และ Screen Inventory
doc_id: BJS-DOC-06
doc_type: ux-flows
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: UX/UI (Book Dev)
related: 04-runbook.md, 05-srs.md, 07-test-uat.md, 08-rtm.md
---

# Book Job Scraping — User Flow และ Screen Inventory

## 1. รายการหน้าจอ / พื้นผิวการใช้งาน

ไม่มี web app; พื้นผิวคือ CLI, ไฟล์ review packet, Chrome extension และ MCP

| ID | พื้นผิว | ชื่อ | บทบาท | สถานะ |
|---|---|---|---|---|
| SC-01 | `main.py status` | สถานะ scheduler | Operator | มีแล้ว |
| SC-02 | `pipeline_runner.py --health` / health monitor | Health report (console) | Operator | มีแล้ว |
| SC-03 | `data/career-review/current/README.md` + `<JOB_ID>/` | Review packet (snapshot, checklist ไทย, `verification.json`) | Operator | มีแล้ว |
| SC-04 | `application_review.py prepare` / `record-submission` | Prepare และบันทึกการสมัคร | Operator / Owner | มีแล้ว |
| SC-05 | `matched_jobs.csv` ในโปรแกรม spreadsheet | รายการงานที่จัดประเภทแล้ว | Operator | มีแล้ว |
| SC-06 | `scraper_dashboard.py` → console + JSON | Dashboard รวม scraper | Operator | มีแล้ว |
| SC-07 | `job_dashboard.py`, `pipeline_dashboard.py` | Dashboard อื่น | Operator | มีโค้ด; การใช้งาน **[ต้องยืนยัน]** |
| SC-08 | Chrome extension popup (`popup.html`) | Quick Saver — Jobs & Property Leads | Operator | มีแล้ว (lane property/FB) |
| SC-09 | MCP tools | ค้นข้อมูลผ่าน AI agent | AI agent | มีแล้ว |
| SC-10 | Solo Empire `JOB-TRACKER.md` | บันทึกใบสมัครที่ยืนยันแล้ว | Owner | นอก repo |

## 2. User flow หลัก

### 2.1 จากประกาศงานถึงใบสมัครที่มีหลักฐาน

```mermaid
flowchart TD
  A["Scheduler เก็บงาน ทุก 6 ชม."] --> B["filter_job_matches: PASS / VERIFY / REJECT"]
  B --> C["application_review build: สร้าง packet"]
  C --> D["Operator ตรวจแหล่งจริง กรอก verification.json"]
  D --> E{"ครบและอายุไม่เกิน 7 วัน?"}
  E -->|"ไม่"| D
  E -->|"ใช่"| F["เตรียม resume และ cover letter ที่ตรงความจริง"]
  F --> G["application_review prepare"]
  G --> H{"Owner อนุมัติงานนี้?"}
  H -->|"ไม่"| X["หยุด ไม่ส่ง"]
  H -->|"ใช่"| I["prepare --owner-approved"]
  I --> J["ส่งด้วยมือที่ URL ทางการของ ATS"]
  J --> K["เก็บ receipt แบบ private"]
  K --> L["record-submission: ledger + follow-up 7 วัน"]
  L --> M["import_job_applications.py เข้า JOB-TRACKER"]
```

### 2.2 Gate ของ sender เดิม

```mermaid
flowchart LR
  S["สั่ง sender"] --> F1{"มี --send หรือ --apply?"}
  F1 -->|"ไม่"| DRY["dry-run เท่านั้น"]
  F1 -->|"มี"| F2{"BOOK_JOB_LIVE_SEND_ENABLED=1 และ unlock ถูกต้อง?"}
  F2 -->|"ไม่"| BLOCK["ปฏิเสธ"]
  F2 -->|"ใช่"| F3{"PASS และ APPROVED?"}
  F3 -->|"ไม่"| BLOCK
  F3 -->|"ใช่"| SEND["ส่งจริง (ห้ามทำจนกว่าจะมีคำสั่ง)"]
```

### 2.3 Health รายวัน

```mermaid
sequenceDiagram
  participant O as Operator
  participant H as pipeline_runner health
  participant D as data directory
  O->>H: รัน --health
  H->>D: ตรวจอายุ 4 artifact หลัก
  D-->>H: เวลาแก้ไขล่าสุด
  H-->>O: เขียว หรือรายการไฟล์ที่เก่า
  O->>O: ถ้าแดง รัน main.py run job_postings แล้วดู log
```

## 3. Design system / component

- ไม่มี design system ของ UI; ข้อความ CLI และ checklist ใน packet เป็นภาษาไทย/อังกฤษผสม
- Review packet: โครงสร้างคงที่ (snapshot, checklist ไทย, `verification.json`, `prepared.json`) และ immutable หลัง prepare
- Chrome extension: popup + content script + background (MV3), ส่งออก CSV ผ่าน `downloads`
- หลักการ UX: ค่าเริ่มต้นปลอดภัย (dry-run), ไม่เดาข้อมูลที่ไม่รู้ (เงินเดือน, notice period, คำถามเฉพาะบริษัท), สถานะชัด (`discovered` → `prepared` → `submitted` เฉพาะส่งจริง)

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| UX/UI (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `CAREER-WORKFLOW.md`, `SAFETY.md`, `README.md` §Collection health
- `scripts/application_review.py`, `scripts/scraper_dashboard.py`, `chrome-extension/`, `mcp_server/server.py`
