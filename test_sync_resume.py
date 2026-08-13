"""ทดสอบ daily sync แบบ resume + guard ใหม่ — mock DB/Turso/Eve ทั้งหมด"""
import os, sys, json
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('POSTGRES_URL_NON_POOLING', '')
os.environ['TURSO_DATABASE_URL'] = 'libsql://fake'
os.environ['TURSO_AUTH_TOKEN'] = 'fake'

import app as A
import auto_daily_export as AE

ok = lambda m: print(f"  ✅ {m}")

ZONES = [{'zone_id': f'Z{i}', 'zone_name': f'Zone{i}', 'branch_ids': ['101']} for i in (1, 2, 3, 4)]
PROGRESS = {}          # {(date, zone_id): row}
SYNC_DATE = date(2026, 8, 12)


def fake_get_progress(d):
    return {zid: dict(v) for (dd, zid), v in PROGRESS.items() if dd == d}

def fake_save_progress(d, zid, zname, status, records=0, attempts=1, last_error=''):
    key = (d, str(zid))
    prev = PROGRESS.get(key, {})
    PROGRESS[key] = {'zone_id': str(zid), 'zone_name': zname, 'status': status,
                     'records': records, 'attempts': int(prev.get('attempts', 0)) + 1,
                     'last_error': last_error}
    return True

def fake_clear(d):
    for k in [k for k in PROGRESS if k[0] == d]:
        del PROGRESS[k]
    return True


class FakeTurso:
    def __init__(s, *a, **k): pass
    def init_db(s): return True
    def delete_zone_records(s, *a): return True
    def insert_trades_batch(s, data, zone): return len(data)
    def reconcile_snapshot(s, data, zone, d):
        n = len({str(i.get('trade_in_id')) for i in data})
        return {'success': True, 'turso_count': n, 'missing_count': 0,
                'extra_count': 0, 'checksum_match': True}
    def close(s): pass


def make_fetch(records_per_zone=3, slow_zones=(), seconds=1.0, clock=None):
    def fetch(zone, target_date):
        if clock and zone['zone_name'] in slow_zones:
            clock[0] += seconds
        elif clock:
            clock[0] += 1.0
        return ([{'trade_in_id': f"{zone['zone_id']}-{i}", 'document_no': str(i),
                  'net_price': 100} for i in range(records_per_zone)], True)
    return fetch


def run(clock=None, branches=None, turso_cls=None, **kw):
    """เรียก run_daily_export ด้วย mock ครบชุด"""
    patches = [
        patch.object(AE, 'get_auto_export_config', lambda: {'enabled': True, 'zone_ids': []}),
        patch.object(AE, 'TursoHandler', turso_cls or FakeTurso),
        patch.object(AE, 'get_sync_progress', fake_get_progress),
        patch.object(AE, 'save_sync_progress', fake_save_progress),
        patch.object(AE, 'save_auto_sync_log', lambda x: None),
        patch.object(A, 'load_custom_zones_from_file', lambda: list(ZONES)),
        patch.object(A, 'get_branches_from_db', lambda: list(branches or [])),
        patch.object(A, 'get_auto_cancel_config', lambda: {}),
    ]
    if clock is not None:
        patches.append(patch.object(AE.time, 'time', lambda: clock[0]))
    for p in patches: p.start()
    try:
        return AE.run_daily_export(force=True,
                                   target_dt=datetime.combine(SYNC_DATE, datetime.min.time()),
                                   **kw)
    finally:
        for p in patches: p.stop()


print("\n[1] sync ครบใน request เดียว (budget เหลือเฟือ)")
PROGRESS.clear()
clock = [1000.0]
with patch.object(AE, 'fetch_zone_daily_data', make_fetch(clock=clock)):
    r = run(clock=clock, time_budget=10000)
assert r['completed'] is True, r
assert r['zones_done'] == 4 and r['zones_remaining'] == 0, r
assert r['total_records'] == 12, r
ok(f"4 zone เสร็จรวดเดียว, {r['total_records']} records, completed=True")

print("\n[2] budget หมดกลางทาง -> หยุด + จำว่าทำถึง zone ไหน")
PROGRESS.clear()
clock = [1000.0]
with patch.object(AE, 'fetch_zone_daily_data', make_fetch(seconds=3.0, clock=clock)):
    r = run(clock=clock, time_budget=3)   # ~1s/zone -> ทำได้ราว 2-3 zone
assert r['completed'] is False, r
assert r['stopped_early'] is True, r
assert 0 < r['zones_done'] < 4, r
done_first = r['zones_done']
ok(f"budget 3s -> ทำได้ {done_first}/4 zone, completed=False, บันทึกไว้แล้ว")

print("\n[3] เรียกซ้ำ -> ทำต่อจาก zone ที่ค้าง ไม่ทำซ้ำ")
calls = []
def counting_fetch(zone, td):
    calls.append(zone['zone_name'])
    clock[0] += 1.0
    return ([{'trade_in_id': f"{zone['zone_id']}-x", 'document_no': '1', 'net_price': 1}], True)

rounds = 0
while not r['completed']:
    rounds += 1
    assert rounds < 10, "วนไม่จบ"
    with patch.object(AE, 'fetch_zone_daily_data', counting_fetch):
        r = run(clock=clock, time_budget=10000)
assert r['completed'] is True and r['zones_done'] == 4, r
assert len(calls) == 4 - done_first, (calls, done_first)
assert len(set(calls)) == len(calls), f"มี zone ถูก sync ซ้ำ: {calls}"
ok(f"อีก {rounds} รอบทำต่อเฉพาะ {len(calls)} zone ที่เหลือ ({calls}) ไม่ซ้ำเลย")

print("\n[4] เรียกอีกครั้งหลังครบ -> ข้ามทันที ไม่แตะ Eve")
called = []
with patch.object(AE, 'fetch_zone_daily_data',
                  lambda z, t: called.append(z) or ([], True)):
    r2 = run(clock=clock)
assert r2['completed'] is True and not called, (r2, called)
assert r2['zones_skipped_done'] == 4, r2
ok("ครบแล้วเรียกซ้ำ -> ข้าม 4 zone, ไม่ยิง Eve เลย")

print("\n[5] is_sync_complete ใช้เป็น guard ได้")
with patch.object(AE, 'get_sync_progress', fake_get_progress):
    c, done, total, pending = AE.is_sync_complete(SYNC_DATE, zones=ZONES)
assert c is True and done == 4 and pending == [], (c, done, pending)
del PROGRESS[(SYNC_DATE, 'Z3')]
with patch.object(AE, 'get_sync_progress', fake_get_progress):
    c, done, total, pending = AE.is_sync_complete(SYNC_DATE, zones=ZONES)
assert c is False and done == 3 and pending == ['Zone3'], (c, done, pending)
ok("ครบ -> True / ขาด 1 zone -> False พร้อมบอกชื่อ zone ที่ค้าง")

print("\n[6] zone ที่ warning ต้องถือว่าทำแล้ว (กันวนซ้ำไม่จบ)")
PROGRESS.clear()
clock = [1000.0]
def unresolved_fetch(zone, td):
    clock[0] += 1.0
    return ([{'trade_in_id': f"{zone['zone_id']}-1", 'document_no': '1', 'net_price': 1}], True)
with patch.object(AE, 'fetch_zone_daily_data', unresolved_fetch), \
     patch.object(AE, 'verify_zone_branches',
                  lambda z, ref: {'total': 1, 'resolved': 0,
                                  'unresolved': [{'branch_id': '999', 'reason': 'x'}],
                                  'real_ids': set()}), \
     patch.object(AE, 'find_unassigned_branches', lambda z, ref: []):
    r = run(clock=clock, time_budget=10000,
            branches=[{'branch_id': '101', 'branch_name': '00009 : ID9 : x'}])
statuses = {v['status'] for v in fake_get_progress(SYNC_DATE).values()}
assert r['total_warnings'] == 4, r['total_warnings']
assert statuses == {'done_warning'}, statuses
assert r['completed'] is True, r
ok("zone ที่มีสาขา resolve ไม่ได้ -> warning แต่ mark done_warning, guard ยังทำงาน")

print("\n[7] กันข้อมูลหาย: Eve คืน 0 รายการ แต่ Turso มีข้อมูลอยู่")
PROGRESS.clear()
clock = [1000.0]
deleted = []
class GuardTurso(FakeTurso):
    def delete_zone_records(s, zone, d):
        deleted.append(zone); return True
    def reconcile_snapshot(s, data, zone, d):
        # จำลองว่า Turso มีข้อมูลเดิม 500 รายการอยู่แล้ว
        return {'success': not data, 'turso_count': 500, 'missing_count': 0,
                'extra_count': 0, 'checksum_match': False}
with patch.object(AE, 'fetch_zone_daily_data', lambda z, t: ([], True)):
    r = run(clock=clock, time_budget=10000, turso_cls=GuardTurso)
assert deleted == [], f"ไม่ควรลบข้อมูลเดิม แต่ลบไป: {deleted}"
assert r['total_warnings'] == 4, r
statuses = {v['status'] for v in fake_get_progress(SYNC_DATE).values()}
assert statuses == {'done_warning'}, statuses
ok("Eve คืน 0 แต่ Turso มี 500 -> ไม่ลบ, ขึ้น warning แทน")

print("\n[8] วันที่ไม่มีเทรดจริง (Turso ก็ว่าง) -> ลบได้ตามปกติ")
PROGRESS.clear()
clock = [1000.0]
deleted = []
class EmptyTurso(FakeTurso):
    def delete_zone_records(s, zone, d):
        deleted.append(zone); return True
    def reconcile_snapshot(s, data, zone, d):
        return {'success': True, 'turso_count': 0, 'missing_count': 0,
                'extra_count': 0, 'checksum_match': True}
with patch.object(AE, 'fetch_zone_daily_data', lambda z, t: ([], True)):
    r = run(clock=clock, time_budget=10000, turso_cls=EmptyTurso)
assert len(deleted) == 4, deleted
assert r['completed'] is True and r['total_warnings'] == 0, r
ok("Turso ว่างอยู่แล้ว -> ลบตามปกติ ไม่ขึ้น warning")

print("\n" + "=" * 60)
print("✅ ผ่านทั้งหมด 8 กลุ่มทดสอบ (resume + guard + กันข้อมูลหาย)")
print("=" * 60)
