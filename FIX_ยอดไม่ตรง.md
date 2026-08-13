# แก้ปัญหายอดเทรดใน Turso ไม่ตรงกับ techswop

## สาเหตุ

ยอดรายเดือนของบางสาขาต่ำกว่าที่เห็นใน techswop เพราะสาขาบางแห่ง**ไม่เคยถูกดึงข้อมูลเข้า Turso** โดยระบบไม่แจ้งเตือนอะไรเลย เกิดจาก 2 ช่องโหว่

### ช่องโหว่ที่ 1 — รายชื่อสาขาไม่รีเฟรชอัตโนมัติ

`/api/admin/auto-export-cron` sync ยอดเข้า Turso ทุกวันอัตโนมัติ แต่รายชื่อสาขาต้อง**กดปุ่มอัปเดตเอง** (`/api/admin/update-branches`)

สาขาที่เปิดใหม่ที่ techswop จะไม่โผล่ในระบบจนกว่าจะมีคนกดอัปเดต และต้องเพิ่มเข้า zone ด้วยมืออีกที ระหว่างนั้น cron จะรัน "สำเร็จ" ทุกวันโดยไม่รู้ว่าสาขานั้นมีอยู่

### ช่องโหว่ที่ 2 — branch ID สองชุดที่ไม่ตรงกัน (ตัวการหลัก)

| ชุด | แหล่ง | รูปแบบ ID |
|---|---|---|
| ชุดจริง | `cached_branches` ใน Postgres | ID จริงจาก Eve |
| ชุดสำรอง | `static/branches-data.js`, `extracted_branches.json` (freeze 3 ม.ค. 2026) | index เรียงลำดับ 1, 2, 3... |

หน้าแก้ไข zone ปกติดึงจากชุดจริง แต่ถ้า `/api/branches` ล้ม (session Eve หมดอายุ, DB ล่ม) โค้ดเดิม **fallback ไปใช้ชุดสำรองแบบเงียบๆ** แค่ log ใน console

ถ้า admin บันทึก zone ตอนนั้นพอดี → zone จะเก็บ index แทน ID จริง → cron เอา ID นั้นไปยิง Eve ทุกวันแล้วไม่ได้ข้อมูล → ยอดหายถาวรจนกว่าจะมีคนสังเกต

### ทำไมไม่มี error

`reconcile_snapshot()` เทียบแค่ "ข้อมูลที่ดึงจาก Eve" กับ "ที่เขียนลง Turso" ถ้าสาขาไม่ถูกดึงตั้งแต่แรก มันจะไม่อยู่ในทั้งสองฝั่ง = ผ่านการตรวจ

---

## วิธีซ่อมข้อมูล (ทำตามลำดับ)

### ขั้นที่ 1 — หาว่าสาขาไหนหาย

```bash
python3 audit_zones.py --refresh --json report.json
```

`--refresh` จะ login Eve ดึงรายชื่อสาขาสดก่อนตรวจ (แนะนำให้ใส่เสมอ) ผลลัพธ์บอก

- **orphan** — `branch_id` ใน zone ที่หาไม่เจอในรายชื่อจริง = สาขาที่ดึงไม่ได้มาตลอด
- **drift** — ID ที่ resolve ได้แต่ชี้ไปคนละสาขากับชุดเก่า = ร่องรอยการบันทึกด้วยชุดสำรอง
- **unassigned** — สาขาที่มีจริงแต่ไม่อยู่ใน zone ไหนเลย
- **timeline** — วันที่ยอด record ตกฮวบเทียบกับค่าเฉลี่ย 7 วันก่อนหน้า (จาก `auto_export_log`)

ดูประวัติการแก้ zone เพิ่มเติมได้ที่ (มีข้อมูลตั้งแต่หลัง deploy รอบนี้เป็นต้นไป)

```
GET /api/admin/zone-audit-log?only_suspicious=1
```

### ขั้นที่ 2 — แก้ zone ให้ถูกต้อง

เข้าหน้าจัดการ Zone แล้วเพิ่มสาขาที่หายกลับเข้าไป

ถ้าหน้าจอขึ้น "⛔ บันทึก Zone ไม่ได้" แปลว่ารายชื่อสาขาโหลดไม่สำเร็จ — **อย่าพยายามหลบ** ให้กดอัปเดตสาขาให้ผ่านก่อน นี่คือกลไกที่เพิ่มเข้ามาเพื่อกันไม่ให้ปัญหาเดิมเกิดซ้ำ

### ขั้นที่ 3 — Backfill ย้อนหลัง

ดูก่อนว่าจะรันวันไหนบ้าง (ไม่ sync จริง)

```bash
curl -X POST https://report-trade.vercel.app/api/admin/backfill-range \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"date_start":"01/07/2026","date_end":"31/07/2026","dry_run":true}'
```

รันจริง (ตัด `dry_run` ออก) — ปลอดภัยต่อการรันซ้ำ เพราะแต่ละวันจะ `delete_zone_records` ก่อน insert ใหม่

```bash
curl -X POST https://report-trade.vercel.app/api/admin/backfill-range \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"date_start":"01/07/2026","date_end":"31/07/2026"}'
```

จำกัดครั้งละไม่เกิน 62 วัน รับทั้ง `DD/MM/YYYY` และ `YYYY-MM-DD`

> ⚠️ ช่วงเวลานาน ๆ อาจชน timeout ของ Vercel — ถ้าเจอ ให้แบ่งเป็นสัปดาห์ละครั้ง หรือรัน `run_daily_export(force=True, target_dt=...)` จากเครื่องตัวเอง

### ขั้นที่ 4 — ตรวจซ้ำ

```bash
python3 audit_zones.py --refresh
```

ต้องได้ orphan = 0, drift = 0 แล้วเทียบยอดรายเดือนกับ techswop อีกครั้ง

---

## กลไกป้องกันที่เพิ่มเข้ามา

| จุด | เดิม | ใหม่ |
|---|---|---|
| `templates/index.html` — zone modal | fallback ไปชุดสำรองเงียบๆ | โหลดจาก DB เท่านั้น ล้มเหลว = แสดง error + ปิดปุ่มบันทึก |
| `saveZone()` | บันทึกได้เสมอ | บล็อกถ้า `BRANCH_LIST_TRUSTED` เป็น false |
| `saveZone()` | ขึ้น "บันทึกเรียบร้อย" แม้ backend fail | ไม่ปิด modal ถ้า backend ปฏิเสธ |
| `save_custom_zones_to_file()` | `DELETE` ทั้งตารางแล้ว insert ใหม่ | upsert เฉพาะที่เปลี่ยน + ปฏิเสธ payload ว่าง + เขียน `zone_audit_log` |
| `auto_daily_export.py` | reconcile แค่ Eve↔Turso | เพิ่ม `verify_zone_branches()` เช็คว่า ID ทุกตัว resolve ได้ ไม่ได้ = warning + แจ้ง Telegram |
| รายชื่อสาขา | กดอัปเดตเอง | cron `/api/admin/refresh-branches-cron` วันละครั้ง 23:30 น. + แจ้งเตือนสาขาใหม่ที่ยังไม่อยู่ใน zone |

ตั้งเวลา cron รีเฟรชสาขาได้ที่ `system_settings` key = `branch_refresh_time` (รูปแบบ `HH:MM`, default `23:30`) ควรตั้งให้เร็วกว่าเวลา auto-export

## ไฟล์ที่แก้

- `audit_zones.py` *(ใหม่)* — สคริปต์ตรวจ zone
- `app.py` — `zone_audit_log`, upsert zones, `/api/admin/zone-audit-log`, `/api/admin/backfill-range`, `/api/admin/refresh-branches-cron`
- `auto_daily_export.py` — `verify_zone_branches()`, `find_unassigned_branches()`, branch audit ใน sync loop, Telegram alert
- `templates/index.html` — branch list trust guard
- `.github/workflows/techtrade-cron.yml` — job `refresh-branches`
