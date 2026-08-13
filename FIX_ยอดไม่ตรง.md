# แก้ปัญหายอดเทรดใน Turso ไม่ตรงกับ techswop

## สาเหตุ

ยอดรายเดือนของบางสาขาต่ำกว่าที่เห็นใน techswop เพราะสาขาบางแห่ง**ไม่เคยถูกดึงข้อมูลเข้า Turso** โดยระบบไม่แจ้งเตือนอะไรเลย เกิดจาก 2 ช่องโหว่

### ช่องโหว่ที่ 1 — เขียนลง Turso ไม่ลง แต่รายงานว่าสำเร็จ (ร้ายแรงที่สุด)

`_execute_batch_http()` ใน `turso_handler.py` มีปัญหา 3 อย่างพร้อมกัน

```python
def _execute_batch_http(self, stmts):
    ...
    try:
        requests.post(f"{url}/v2/pipeline", ..., json={"requests": reqs}, timeout=30)
        return True          # <- ไม่เคยเช็คว่าสำเร็จจริงไหม
    except: return False
```

1. ส่งทุก statement ในคำขอเดียว — บางวันเกิน 1,800 รายการ ด้วย `timeout=30`
   จึง timeout แทบทุกครั้ง แล้วเขียนไม่ลงเลยสักรายการ
2. ไม่เช็ค `status_code` และไม่เช็ค error รายคำสั่ง — Turso ตอบ error ก็ยังคืน `True`
   ผู้เรียกรายงานว่าเขียนครบ
3. `except:` เปล่าๆ กลืน exception ทุกชนิด

หลักฐานจาก production (13 ส.ค. 2026)

```
GET /api/admin/sync-progress?date=2026-08-12

zone Studio7 | status: done_warning
Reconcile mismatch: Eve=1885, inserted=0, Turso=1102, missing=681
```

ดึงจาก Eve ได้ครบ 1,885 รายการ แต่เขียนลง Turso ได้ **0** — ในฐานมีอยู่ 1,102 จากการเขียนสำเร็จบางส่วนครั้งก่อน ขาดไป 681 รายการ

นี่คือเหตุผลที่ยอดขาดแบบไม่มีรูปแบบตายตัว: ขึ้นกับว่าวันไหน batch ใหญ่พอจะ timeout

### ช่องโหว่ที่ 2 — daily sync ไม่เคยจบ

`/api/admin/auto-export-cron` รัน `run_daily_export()` ทั้งหมดใน HTTP request เดียว
ซึ่งใช้เวลาเกิน 30 วินาทีเสมอ แต่ workflow ตั้ง `curl --max-time 30`

ผลจากการตรวจ GitHub Actions ย้อนหลัง 400 runs (21 ก.ค. – 13 ส.ค. 2026)

- วันปกติ job `auto-export` ล้มเหลว **1 ครั้งทุกวัน** ตอน 00:07–01:26 น. (exit 28 = curl timeout)
- บางวันล้มเหลวรัวทั้งวัน แปลว่า sync ไม่เคยจบ → ข้อมูลวันนั้นหาย
  - 13 ส.ค. — 0 สำเร็จ / 12 ล้มเหลว → ข้อมูลของ 12 ส.ค. ไม่มีเลย
  - 10 ส.ค. — 1 สำเร็จ / 25 ล้มเหลว → ข้อมูลของ 9 ส.ค. ไม่ครบ
  - 9 ส.ค. (5 fail) และ 7 ส.ค. (3 fail) — น่าสงสัย

ที่แย่กว่านั้นคือ guard "already ran" ซึ่งเช็คจาก `auto_export_log`
แถวล่าสุดที่ `status='success'` พลาดได้ 2 ทาง

| สถานการณ์ | ผลลัพธ์ |
|---|---|
| ถูกฆ่าก่อน zone แรกเสร็จ | ไม่มี success เลย → ping ถัดไปเริ่มใหม่หมด → วนไม่จบทั้งวัน |
| zone แรกๆ เสร็จแล้วถูกฆ่า | guard ติด → **zone ที่เหลือไม่ได้ sync ทั้งวัน แบบเงียบๆ** |

เคสที่สองคือที่มาของ "ยอดบางสาขาไม่ตรง" โดยตรง — และเกิดซ้ำได้ทุกวัน

### ช่องโหว่ที่ 3 — รายชื่อสาขาไม่รีเฟรชอัตโนมัติ

`/api/admin/auto-export-cron` sync ยอดเข้า Turso ทุกวันอัตโนมัติ แต่รายชื่อสาขาต้อง**กดปุ่มอัปเดตเอง** (`/api/admin/update-branches`)

สาขาที่เปิดใหม่ที่ techswop จะไม่โผล่ในระบบจนกว่าจะมีคนกดอัปเดต และต้องเพิ่มเข้า zone ด้วยมืออีกที ระหว่างนั้น cron จะรัน "สำเร็จ" ทุกวันโดยไม่รู้ว่าสาขานั้นมีอยู่

### ช่องโหว่ที่ 4 — branch ID สองชุดที่ไม่ตรงกัน

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

ตรวจว่าวันไหน sync ไม่ครบ (มีข้อมูลตั้งแต่หลัง deploy รอบนี้เป็นต้นไป)

```
GET /api/admin/sync-progress?date=2026-08-12
```

บอกว่า zone ไหนเสร็จ zone ไหนค้าง พร้อม error ของแต่ละ zone

ดูประวัติการแก้ zone เพิ่มเติมได้ที่ (มีข้อมูลตั้งแต่หลัง deploy รอบนี้เป็นต้นไป)

```
GET /api/admin/zone-audit-log?only_suspicious=1
```

### ขั้นที่ 2 — แก้ zone ให้ถูกต้อง

เข้าหน้าจัดการ Zone แล้วเพิ่มสาขาที่หายกลับเข้าไป

ถ้าหน้าจอขึ้น "⛔ บันทึก Zone ไม่ได้" แปลว่ารายชื่อสาขาโหลดไม่สำเร็จ — **อย่าพยายามหลบ** ให้กดอัปเดตสาขาให้ผ่านก่อน นี่คือกลไกที่เพิ่มเข้ามาเพื่อกันไม่ให้ปัญหาเดิมเกิดซ้ำ

### ขั้นที่ 3 — Backfill ย้อนหลัง

Backfill ทำงานเป็น **job ที่มี cursor** — แต่ละ request จะรันเท่าที่ทันใน time budget
(240 วินาทีบน Vercel) แล้วจำว่าค้างวันไหน ครั้งถัดไปทำต่อจากจุดนั้น จึงไม่ชน timeout
ต่อให้ backfill ทั้งปี และถ้า process ถูกฆ่ากลางคันก็ไม่ต้องเริ่มใหม่

เลือกวิธีใดวิธีหนึ่ง

#### วิธีที่ 1 — รันจากเครื่องตัวเอง (ง่ายและเร็วที่สุด)

ไม่ผ่าน HTTP จึงไม่มี timeout เลย ต้องมี `.env` ที่มี `POSTGRES_URL_NON_POOLING` และ `TURSO_*` ครบ

```bash
python3 run_backfill.py --start 01/07/2026 --end 31/07/2026 --dry-run   # ดูก่อน
python3 run_backfill.py --start 01/07/2026 --end 31/07/2026             # รันจริง
```

#### วิธีที่ 2 — GitHub Actions (ไม่ต้องเฝ้า)

ไปที่แท็บ Actions → **TechTrade Backfill** → Run workflow → ใส่ช่วงวันที่

Runner จะวนเรียก `/backfill-continue` ให้เองจนจบ พร้อมโชว์ progress ทุกรอบ

#### วิธีที่ 3 — เรียก API เอง

```bash
# เริ่ม job
curl -X POST https://report-trade.vercel.app/api/admin/backfill-range \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"date_start":"01/07/2026","date_end":"31/07/2026"}'
```

ถ้าตอบกลับมา `"completed": false` แปลว่ายังไม่จบ ให้เรียกต่อด้วย `job_id` ที่ได้มา
ซ้ำจนกว่า `completed` เป็น `true`

```bash
curl -X POST https://report-trade.vercel.app/api/admin/backfill-continue \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"BF_20260813..."}'
```

หรือให้ `run_backfill.py` วนให้

```bash
python3 run_backfill.py --mode remote --start 01/07/2026 --end 31/07/2026 \
  --secret "$CRON_SECRET"
```

ดูสถานะ/ผลรายวันได้ที่

```
GET /api/admin/backfill-status                    # 20 job ล่าสุด
GET /api/admin/backfill-status?job_id=BF_...      # รายละเอียดรายวัน
```

**ข้อควรรู้**

- ปลอดภัยต่อการรันซ้ำ — แต่ละวันจะ `delete_zone_records` ก่อน insert ใหม่ ไม่เกิดข้อมูลซ้ำ
- รับทั้ง `DD/MM/YYYY` และ `YYYY-MM-DD` สูงสุด 366 วันต่อ job
- ปรับ time budget ได้ด้วย env `BACKFILL_TIME_BUDGET` (วินาที)
- ถ้าวันไหนล้มเหลว job จะไม่หยุด แต่จะนับไว้ใน `days_failed` และบอก `last_error`
  รัน backfill เฉพาะช่วงนั้นซ้ำได้เลย

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
| Backfill | รันรวดเดียว ชน timeout แล้วไม่รู้ว่าค้างวันไหน | job ที่มี cursor ใน `backfill_jobs` ทำต่อได้ + บันทึก progress ทุกวัน |
| `_execute_batch_http()` | ส่งทุก statement ในคำขอเดียว timeout 30s แล้ว `return True` เสมอ | แบ่งก้อนละ 200 timeout 60s retry 2 ครั้ง คืนจำนวนที่เขียนสำเร็จจริง |
| `insert_trades_batch()` | คืน `len(stmts)` โดยไม่ตรวจว่าเขียนลงจริง | คืนจำนวนจริง เพื่อให้ `reconcile_snapshot()` จับ mismatch ได้ |
| `run_daily_export()` | รันทุก zone รวดเดียว โดนตัดกลางคันแล้วเริ่มใหม่ | ทำเท่าที่ทันใน budget 240s บันทึก `sync_progress` ราย zone แล้วทำต่อ |
| guard "already ran" | ดู log แถวล่าสุดที่ `status='success'` | เช็คจาก `sync_progress` ว่าครบทุก zone ของวันนั้นหรือยัง |
| zone ที่ error | ค้างบล็อกทั้งวัน | ลองใหม่ได้ 3 ครั้ง แล้ว `failed_final` ข้ามไป zone อื่น |
| Eve คืน 0 รายการ | `delete_zone_records()` ลบข้อมูลเดิมทิ้ง | ถ้า Turso ยังมีข้อมูล → ไม่ลบ + ขึ้น warning |
| workflow `auto-export` | `--max-time 30` ยิงครั้งเดียว | `--max-time 300` วนจนครบทุก zone |
| sync ไม่จบ | เงียบสนิท | แจ้ง Telegram เมื่อเลยเวลา schedule เกิน 6 ชั่วโมงแล้วยังไม่ครบ |

ตั้งเวลา cron รีเฟรชสาขาได้ที่ `system_settings` key = `branch_refresh_time` (รูปแบบ `HH:MM`, default `23:30`) ควรตั้งให้เร็วกว่าเวลา auto-export

## ไฟล์ที่แก้

- `audit_zones.py` *(ใหม่)* — สคริปต์ตรวจ zone
- `run_backfill.py` *(ใหม่)* — ตัวรัน backfill จนจบ (โหมด local / remote)
- `app.py` — `zone_audit_log`, `backfill_jobs`, upsert zones, `/api/admin/zone-audit-log`,
  `/api/admin/backfill-range`, `/api/admin/backfill-continue`, `/api/admin/backfill-status`,
  `/api/admin/refresh-branches-cron`
- `auto_daily_export.py` — `verify_zone_branches()`, `find_unassigned_branches()`, branch audit ใน sync loop, Telegram alert
- `templates/index.html` — branch list trust guard
- `.github/workflows/techtrade-cron.yml` — job `refresh-branches`
- `.github/workflows/backfill.yml` *(ใหม่)* — workflow_dispatch วน backfill จนจบ
- `turso_handler.py` — แก้ `_execute_batch_http()` และ `insert_trades_batch()`
- `test_sync_resume.py`, `test_backfill.py`, `test_zone_fixes.py`, `test_turso_insert.py` *(ใหม่)* — เทสต์ (mock ทั้งหมด ไม่แตะ production)

ปรับพฤติกรรมการเขียนได้ด้วย env: `TURSO_BATCH_SIZE` (200), `TURSO_HTTP_TIMEOUT` (60), `TURSO_MAX_RETRIES` (2)

## วันที่ควร backfill ก่อน

จากผลตรวจ GitHub Actions — ยืนยันอีกครั้งด้วย `/api/admin/sync-progress` หรือ `auto_export_log`

| วันของข้อมูล | เหตุผล |
|---|---|
| 12 ส.ค. 2026 | sync ไม่เคยจบเลย |
| 9 ส.ค. 2026 | ล้มเหลว 25 ครั้ง |
| 8 ส.ค. 2026 | ล้มเหลว 5 ครั้ง |
| 6 ส.ค. 2026 | ล้มเหลว 3 ครั้ง |
