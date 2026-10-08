---
title: Book Job Scraping — Requirements Traceability Matrix
doc_id: BJS-DOC-08
doc_type: rtm
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: BA + QA (Book Dev)
related: 01-prd.md, 05-srs.md, 06-ux-flows.md, 07-test-uat.md
---

# Book Job Scraping — Requirements Traceability Matrix

## 1. ตาราง FR ↔ US ↔ พื้นผิว ↔ TC ↔ หลักฐาน

| FR | ฟีเจอร์ (PRD) | US | พื้นผิว | TC | สถานะหลักฐาน |
|---|---|---|---|---|---|
| FR-01 | F-01 | US-01 | SC-01 | TC-01, TC-02, TC-03 | อัตโนมัติ — ผ่านรอบ 2026-10-08 (บางส่วน) |
| FR-02 | F-02, F-06 | US-02 | SC-05 | TC-04 | อัตโนมัติ — ไม่ได้รันรอบนี้ |
| FR-03 | F-02 | US-03 | SC-03 | TC-05 | อัตโนมัติ (fixture E2E) — ไม่ได้รันรอบนี้ |
| FR-04 | F-03 | US-04 | SC-05 | TC-06 | อัตโนมัติ — ไม่ได้รันรอบนี้ (ขาด deps) |
| FR-05 | F-09 | — | SC-05 | TC-14 | ไม่พบ test เฉพาะ |
| FR-06 | F-09 | — | SC-05 | TC-14 | ไม่พบ test เฉพาะ |
| FR-07 | F-04 | US-05, US-06, US-07 | SC-03, SC-04 | TC-05, TC-U1 | อัตโนมัติ; UAT ค้าง |
| FR-08 | F-09 | — | SC-04 | TC-07, TC-14 | บางส่วน (สถานะ `prepared` ผ่าน safety test) |
| FR-09 | F-05 | US-08 | SC-04 | TC-07 | อัตโนมัติ — ผ่านรอบ 2026-10-08 |
| FR-10 | F-06 | US-02 | SC-02 | TC-08 | อัตโนมัติ — ไม่ได้รันรอบนี้ |
| FR-11 | F-01 | US-09 | SC-02 | TC-09 | อัตโนมัติ — ไม่ได้รันรอบนี้ |
| FR-12 | F-07 | US-02 | — | TC-10 | อัตโนมัติ — ไม่ได้รันรอบนี้ |
| FR-13 | F-08 | US-10 | ไฟล์ CSV | TC-13 | ไม่มี — ช่องว่าง |
| FR-14 | F-08 | US-07 | SC-10 | TC-U1 | test อยู่ฝั่ง Solo Empire |
| FR-15 | F-10 | US-11 | SC-09 | TC-11 | บางส่วน **[ต้องยืนยัน]** |
| FR-16 | F-11 | — | SC-08 | TC-12 | อัตโนมัติ — ไม่ได้รันรอบนี้ |
| FR-17 | F-11 | — | SC-06 | — | ไม่พบ test สำหรับ discovery feeds |

## 2. ช่องว่างที่ยังไม่ครอบคลุม

| ID | ช่องว่าง | ผลกระทบ | ข้อเสนอ |
|---|---|---|---|
| GAP-01 | ไม่มี CSV column contract และ contract test กับ `book-job-data` (FR-13) | เปลี่ยนคอลัมน์แล้ว ingest พังโดยไม่รู้ | เขียน schema ใน `contracts/` + test ที่ตรวจหัวคอลัมน์ |
| GAP-02 | FR-05/FR-06/FR-08 ไม่มี test เฉพาะ | seed/draft อาจเปลี่ยนสถานะผิด | เพิ่ม test ว่าไม่มีทางได้ `submitted` จาก seed/draft |
| GAP-03 | ไม่มีบันทึก UAT/funnel ของใบสมัครจริง | วัดคุณค่าไม่ได้ (เงื่อนไข verdict) | บันทึกใบสมัครแรกตาม TC-U1 และนับใน JOB-TRACKER |
| GAP-04 | Discovery feeds (FR-17) ไม่มี test และไม่ชัดว่าใครใช้ | ภาระดูแลโดยไม่มีผู้ใช้ | ตัดสินใจย้ายหรือปิด |
| GAP-05 | ruff ตรวจเฉพาะ syntax/undefined names | บั๊กประเภทอื่นหลุด | ขยาย rule ทีละกลุ่มสำหรับโมดูล policy/safety |
| GAP-06 | สถานะ CI ล่าสุดไม่ได้ตรวจในรอบนี้ | ไม่รู้ว่า main เขียวหรือไม่ | ตรวจ GitHub Actions run ล่าสุด |

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| BA (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |
| QA (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `DOCPACK/01-prd.md`, `DOCPACK/05-srs.md`, `DOCPACK/06-ux-flows.md`, `DOCPACK/07-test-uat.md`
- `PRODUCT.md` §Next improvements, `tests/`
