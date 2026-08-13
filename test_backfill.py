"""ทดสอบ backfill แบบ chunk/resume — mock DB + mock run_daily_export ทั้งหมด"""
import os, sys, json, time
from datetime import date, datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A

ok = lambda m: print(f"  ✅ {m}")

# ---------- in-memory backfill_jobs ----------
JOBS = {}

def fake_load(job_id):
    j = JOBS.get(job_id)
    return dict(j) if j else None

def fake_save(job_id, cursor_date, status, days_done, days_failed,
              total_records, last_error, results, cleared_date=None):
    j = JOBS[job_id]
    j.update(cursor_date=cursor_date, status=status, days_done=days_done,
             days_failed=days_failed, total_records=total_records,
             last_error=last_error, results=results, cleared_date=cleared_date)
    return True

def new_job(job_id, start, end):
    JOBS[job_id] = {
        'job_id': job_id, 'date_start': start, 'date_end': end,
        'cursor_date': start, 'status': 'running',
        'total_days': (end - start).days + 1, 'days_done': 0,
        'days_failed': 0, 'total_records': 0, 'last_error': '', 'results': [],
        'cleared_date': None,
    }
    return dict(JOBS[job_id])

print("\n[1] time budget")
os.environ.pop('BACKFILL_TIME_BUDGET', None)
os.environ.pop('VERCEL', None)
assert A._backfill_time_budget() == 3000
os.environ['VERCEL'] = '1'
assert A._backfill_time_budget() == 240
os.environ['BACKFILL_TIME_BUDGET'] = '90'
assert A._backfill_time_budget() == 90
ok("local=3000s / vercel=240s / env override=90s")

print("\n[2] chunk หยุดตาม budget แล้วบันทึก cursor")
os.environ['BACKFILL_TIME_BUDGET'] = '10'   # budget 10s
calls = []

class FakeExport:
    """แต่ละวันใช้เวลา 4 วินาที (จำลองด้วย monkeypatched time)"""
    def __init__(s): s.t = 1000.0
    def now(s): return s.t
    def run(s, force=False, target_dt=None, time_budget=None, resume=True):
        calls.append(target_dt.date())
        s.t += 4.0
        return {'sync_completed': True, 'completed': True, 'total_records': 100,
                'total_synced': 1, 'total_errors': 0, 'total_warnings': 0}

fe = FakeExport()
job = new_job('J1', date(2026, 7, 1), date(2026, 7, 10))

import auto_daily_export as AE
with patch.object(A, '_load_backfill_job', fake_load), \
     patch.object(A, '_save_backfill_progress', fake_save), \
     patch.object(AE, 'run_daily_export', fe.run), \
     patch.object(AE, 'clear_sync_progress', lambda d: True), \
     patch.object(A.time, 'time', fe.now):
    j, chunk_days, chunk_records = A._run_backfill_chunk(job)

# 10s budget, 4s ต่อวัน -> ทำได้ 2 วัน (วันที่ 3 คาดว่า 8+4=12 > 10)
assert chunk_days == 2, chunk_days
assert j['cursor_date'] == date(2026, 7, 3), j['cursor_date']
assert j['status'] == 'running' and j['days_done'] == 2
assert calls == [date(2026, 7, 1), date(2026, 7, 2)], calls
ok(f"budget 10s / วันละ 4s -> ทำ {chunk_days} วัน, cursor ค้างที่ {j['cursor_date']}")

print("\n[3] เรียกต่อจน completed")
rounds = 0
while j['status'] != 'completed':
    rounds += 1
    assert rounds < 20, "วนไม่จบ"
    with patch.object(A, '_load_backfill_job', fake_load), \
         patch.object(A, '_save_backfill_progress', fake_save), \
         patch.object(AE, 'run_daily_export', fe.run), \
     patch.object(AE, 'clear_sync_progress', lambda d: True), \
         patch.object(A.time, 'time', fe.now):
        j, cd, cr = A._run_backfill_chunk(dict(j))

assert j['days_done'] == 10 and j['total_records'] == 1000, j
assert j['cursor_date'] is None and j['status'] == 'completed'
assert calls == [date(2026, 7, 1) + timedelta(days=i) for i in range(10)], calls
ok(f"ต่ออีก {rounds} รอบ -> ครบ 10 วัน, 1000 records, ไม่มีวันซ้ำ/ข้าม")

print("\n[4] รับประกันคืบหน้าอย่างน้อย 1 วัน แม้วันเดียวเกิน budget")
os.environ['BACKFILL_TIME_BUDGET'] = '1'
fe2 = FakeExport()
fe2.run = lambda force=False, target_dt=None, time_budget=None, resume=True: (
    setattr(fe2, 't', fe2.t + 999) or
    {'sync_completed': True, 'completed': True, 'total_records': 5, 'total_synced': 1,
     'total_errors': 0, 'total_warnings': 0})
job = new_job('J2', date(2026, 8, 1), date(2026, 8, 5))
with patch.object(A, '_load_backfill_job', fake_load), \
     patch.object(A, '_save_backfill_progress', fake_save), \
     patch.object(AE, 'run_daily_export', fe2.run), \
     patch.object(AE, 'clear_sync_progress', lambda d: True), \
     patch.object(A.time, 'time', fe2.now):
    j2, cd2, _ = A._run_backfill_chunk(job)
assert cd2 == 1 and j2['cursor_date'] == date(2026, 8, 2), (cd2, j2['cursor_date'])
ok("วันเดียวใช้ 999s เกิน budget 1s -> ยังทำได้ 1 วัน ไม่ค้างวนลูป")

print("\n[5] วันที่ล้มเหลวถูกนับ แต่ไม่หยุด job")
os.environ['BACKFILL_TIME_BUDGET'] = '10000'
def flaky(force=False, target_dt=None, time_budget=None, resume=True):
    if target_dt.date().day == 2:
        raise RuntimeError('Eve timeout')
    return {'sync_completed': True, 'completed': True, 'total_records': 7,
            'total_synced': 1, 'total_errors': 0, 'total_warnings': 0}
job = new_job('J3', date(2026, 9, 1), date(2026, 9, 3))
with patch.object(A, '_load_backfill_job', fake_load), \
     patch.object(A, '_save_backfill_progress', fake_save), \
     patch.object(AE, 'run_daily_export', flaky), \
     patch.object(AE, 'clear_sync_progress', lambda d: True):
    j3, _, _ = A._run_backfill_chunk(job)
assert j3['status'] == 'completed' and j3['days_done'] == 3
assert j3['days_failed'] == 1 and j3['total_records'] == 14, j3
assert 'Eve timeout' in j3['last_error']
ok(f"1/3 วันพัง -> job ยังจบ, days_failed={j3['days_failed']}, บันทึก error ไว้")

print("\n[6] _job_public")
p = A._job_public(j3)
assert p['completed'] is True and p['progress_pct'] == 100.0 and p['next_date'] is None
p2 = A._job_public(JOBS['J1'] | {'status': 'running', 'days_done': 3,
                                 'cursor_date': date(2026, 7, 4)})
assert p2['progress_pct'] == 30.0 and p2['next_date'] == '2026-07-04'
assert p2['days_remaining'] == 7
ok("progress_pct / next_date / days_remaining ถูกต้อง")

print("\n[7] endpoint validation")
A.app.config['TESTING'] = True
os.environ.pop('CRON_SECRET', None)
c = A.app.test_client()
assert c.post('/api/admin/backfill-range', json={}).status_code == 400
r = c.post('/api/admin/backfill-range',
           json={'date_start': '01/01/2026', 'date_end': '31/12/2027'})
assert r.status_code == 400 and 'ยาวเกินไป' in r.get_json()['error']
r = c.post('/api/admin/backfill-range',
           json={'date_start': '2026-07-01', 'date_end': '2026-07-31', 'dry_run': True})
d = r.get_json()
assert d['total_days'] == 31 and d['dates'][-1] == '31/07/2026'
assert 'time_budget_seconds' in d
ok(f"dry_run ok (31 วัน), เพดานใหม่ 366 วัน, บอก budget = {d['time_budget_seconds']}s")

print("\n[8] auth ของ endpoint ใหม่")
os.environ['CRON_SECRET'] = 's3cr3t'
assert c.post('/api/admin/backfill-continue', json={}).status_code == 401
assert c.post('/api/admin/backfill-range',
              json={'date_start': '01/07/2026', 'date_end': '02/07/2026'}).status_code == 401
ok("backfill-range / backfill-continue ต้องมี CRON_SECRET")

print("\n[9] วันที่ sync ไม่ครบทุก zone -> ห้ามขยับ cursor ไปวันถัดไป")
os.environ['BACKFILL_TIME_BUDGET'] = '10000'
JOBS.clear()
cleared = []
seen = []
state = {'zones_left': 3}

def partial(force=False, target_dt=None, time_budget=None, resume=True):
    """จำลอง: วันแรกต้องใช้ 3 รอบถึงจะครบทุก zone"""
    seen.append(target_dt.date())
    state['zones_left'] -= 1
    done = state['zones_left'] <= 0
    if done and target_dt.date() == date(2026, 10, 1):
        state['zones_left'] = 1   # วันถัดไปจบในรอบเดียว
    return {'sync_completed': True, 'completed': done, 'total_records': 10,
            'total_synced': 1, 'total_errors': 0, 'total_warnings': 0,
            'zones_remaining': max(0, state['zones_left'])}

job = new_job('J9', date(2026, 10, 1), date(2026, 10, 2))
with patch.object(A, '_load_backfill_job', fake_load), \
     patch.object(A, '_save_backfill_progress', fake_save), \
     patch.object(AE, 'run_daily_export', partial), \
     patch.object(AE, 'clear_sync_progress', lambda d: cleared.append(d) or True):
    j9, _, _ = A._run_backfill_chunk(job)

# รอบแรก: วันที่ 1 ต.ค. ยังไม่ครบ -> cursor ต้องค้างที่ 1 ต.ค. ไม่ใช่ 2 ต.ค.
assert j9['cursor_date'] == date(2026, 10, 1), j9['cursor_date']
assert j9['days_done'] == 0, j9['days_done']
assert seen == [date(2026, 10, 1)], seen
assert cleared == [date(2026, 10, 1)], cleared
ok("วันแรกไม่ครบ -> cursor ค้างวันเดิม, ยังไม่นับ days_done")

# เรียกต่อจนจบทั้ง job
rounds = 0
while j9['status'] != 'completed':
    rounds += 1
    assert rounds < 10, "วนไม่จบ"
    with patch.object(A, '_load_backfill_job', fake_load), \
         patch.object(A, '_save_backfill_progress', fake_save), \
         patch.object(AE, 'run_daily_export', partial), \
         patch.object(AE, 'clear_sync_progress', lambda d: cleared.append(d) or True):
        j9, _, _ = A._run_backfill_chunk(dict(j9))

assert j9['days_done'] == 2, j9['days_done']
assert seen.count(date(2026, 10, 1)) == 3, seen
assert cleared.count(date(2026, 10, 1)) == 1, f"ล้าง sync_progress ซ้ำ: {cleared}"
assert cleared.count(date(2026, 10, 2)) == 1, cleared
ok(f"วนต่อจนครบ 2 วัน (วันแรกใช้ 3 รอบ), ล้าง sync_progress วันละครั้งเท่านั้น")

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 9 กลุ่มทดสอบ (chunking + resume)")
print("=" * 58)
