---
title: Book Job Scraping — Product Card
doc_id: CARD-book-job-scraping
doc_type: product-card
verdict: invest
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Book Job Scraping — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

ช่วยเจ้าของค้นหางาน (รวม remote ระหว่างประเทศ) จับคู่กับโปรไฟล์ และเตรียมเอกสารสมัครอย่างเป็นระบบ โดยการส่งใบสมัคร/อีเมลจริงถูกล็อกไว้หลัง gate สามชั้น

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: การหางานและเตรียมใบสมัครแบบ manual ใช้เวลามาก และประกาศกระจายหลายแหล่ง
- ผู้ใช้: operator (เจ้าของ) คนเดียวตาม `PRODUCT.md` — ไม่ใช่บริการสาธารณะ

## 3. สิ่งที่ทำได้จริงตอนนี้

- สถาปัตยกรรม hexagonal: `core/` (models, use cases, cleaner ภาษาไทย, dedup), engine httpx+BS4/Playwright/Selenium/Scrapy/RSS
- `config/jobs.yaml`: 23 jobs (README) โดยพบ `enabled: true` 10 รายการในรอบตรวจนี้
- MCP server ค้นข้อมูลในเครื่อง, Chrome extension MV3, สคริปต์ tailor resume, skills gap, digest, follow-up (ส่งจริงถูกบล็อกโดยค่าเริ่มต้น)
- ส่งออก capture CSV ให้ `book-job-data` ingest; ไม่เขียน DB ของแอปอื่น (`BOUNDARY.md`, `SAFETY.md`)

## 4. หลักฐานสถานะ

| รายการ | ค่า (ตรวจจาก repository) |
|---|---|
| Stack | Python |
| Commits | 34 (แรก 2026-07-09 → ล่าสุด 2026-10-01) |
| Source | 211 ไฟล์ / 58,740 บรรทัด |
| Tests | 55 ไฟล์ |
| CI | 1 workflow |
| Deploy config | ไม่มี |
| Live URL | ไม่มี |
| README | 898 บรรทัด (`Book Job Scraping — Multi-Engine Capture + Job Pipeline`) |
| โครงสร้างซ้ำ (template family) | 1 repo ที่มี structure signature เดียวกัน |

เป็น Tier A ใน `repository-catalog/roadmaps/tier-a.yaml` (tool flagship); roadmap ระบุ has_ci=false แต่ตอนนี้มี `.github/workflows/ci.yml` แล้ว

## 5. คุณค่าและจุดต่าง

- แก้ปัญหาจริงของเจ้าของโดยตรง และเป็น flagship ด้าน automation ที่ใหญ่ที่สุดใน batch นี้ (58k บรรทัด, 55 test files)
- จุดต่าง: safety gate ก่อน send/apply, แยก producer กับ data product ชัด
- มุมรายได้: ต่อยอดเป็นบริการ career-prep สำหรับคนอื่น **[สมมติฐาน]** — ต้องมีการทบทวน PDPA/ToS ก่อน

## 6. ช่องว่างสำคัญ

- ขอบเขตกว้างเกิน (property/social, e-commerce, news ยังอยู่ใน scheduler) ซ้ำกับ repo scraping อื่น
- live ATS submission ยังไม่ verify; ไม่มีตัวชี้วัดผลลัพธ์ (สัมภาษณ์/ข้อเสนองาน) **[ต้องยืนยัน]**
- CSV column contract ที่ `book-job-data` ใช้ยังไม่ระบุไว้ใน repo นี้ (unknown ใน roadmap)

## 7. คำตัดสิน

**`invest`** — ปัญหาจริงของผู้ใช้จริง (เจ้าของ) core ทำงานและมี test มาก เป็น Tier A อยู่แล้ว จึงลงทุนต่อ — แต่ต้องตัดขอบเขตให้เหลือ job pipeline จะลดเป็น `showcase` ถ้าเจ้าของเลิกใช้หางาน/หาลูกค้าจริง

## 8. ขั้นต่อไป

1. เลื่อนเป็น docpack L1 และบันทึก CSV contract ที่ส่งให้ `book-job-data`
2. ย้ายงาน news/e-commerce/property ออกไป repo เจ้าของ (`book-news-scraping` ฯลฯ)
3. วัดผล pipeline: จำนวนใบสมัครที่ส่งด้วยมือ → สัมภาษณ์

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอพิจารณา | — | ________ |

## แหล่งข้อมูล

- `README.md`
- `PRODUCT.md`
- `BOUNDARY.md`
- `SAFETY.md`
- `config/jobs.yaml`
- `.github/workflows/ci.yml`
- `(solo-empire) repository-catalog/roadmaps/tier-a.yaml`
