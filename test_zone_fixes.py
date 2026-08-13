"""Smoke test สำหรับการแก้ไข — ใช้ mock DB ทั้งหมด ไม่แตะ production"""
import os, sys, json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('POSTGRES_URL_NON_POOLING', '')

import app as A
import auto_daily_export as AE

FAKE_BRANCHES = [
    {'branch_id': '101', 'branch_name': '00009 : ID9 : BN-Zeer-Rangsit'},
    {'branch_id': '102', 'branch_name': '00013 : ID13 : BN-ITmall-Fortune'},
    {'branch_id': '103', 'branch_name': '00024 : ID24 : BN-Zeer-2'},
]

ok = lambda m: print(f"  ✅ {m}")

print("\n[1] _normalize_branch_ids")
assert A._normalize_branch_ids(None) == []
assert A._normalize_branch_ids([1, 2, '3']) == ['1', '2', '3']
assert A._normalize_branch_ids('[4,5]') == ['4', '5']
assert A._normalize_branch_ids('6, 7') == ['6', '7']
ok("รองรับ list / JSON string / comma string")

print("\n[2] verify_zone_branches")
with patch.object(A, 'get_branches_from_db', return_value=FAKE_BRANCHES), \
     patch.object(A, 'find_branch_by_sequential_id', return_value=None):
    r = AE.verify_zone_branches({'branch_ids': ['101', '102']}, FAKE_BRANCHES)
    assert r['resolved'] == 2 and r['unresolved'] == [], r
    assert r['real_ids'] == {'9', '13'}, r
    ok("resolve ครบ -> ไม่มี unresolved")

    r = AE.verify_zone_branches({'branch_ids': ['101', '999']}, FAKE_BRANCHES)
    assert r['resolved'] == 1 and len(r['unresolved']) == 1, r
    assert r['unresolved'][0]['branch_id'] == '999'
    ok("จับ ID ที่ resolve ไม่ได้ (999)")

print("\n[3] find_unassigned_branches")
with patch.object(A, 'get_branches_from_db', return_value=FAKE_BRANCHES), \
     patch.object(A, 'find_branch_by_sequential_id', return_value=None):
    zones = [{'zone_name': 'Z1', 'branch_ids': ['101']}]
    un = AE.find_unassigned_branches(zones, FAKE_BRANCHES)
    assert {b['branch_id'] for b in un} == {'102', '103'}, un
    ok("เจอสาขาที่ไม่อยู่ใน zone ไหนเลย: 102, 103")

print("\n[4] save_custom_zones_to_file — ปฏิเสธ payload ว่าง")
class FakeCur:
    def __init__(s, rows): s.rows, s.executed = rows, []
    def execute(s, sql, params=None): s.executed.append((sql, params))
    def fetchall(s): return s.rows
    def close(s): pass
class FakeConn:
    def __init__(s, rows): s.cur = FakeCur(rows); s.committed = False
    def cursor(s): return s.cur
    def commit(s): s.committed = True
    def rollback(s): pass
    def close(s): pass

existing_rows = [{'zone_id': 'Z1', 'zone_name': 'Zone1', 'branch_ids': ['101', '102']}]
conn = FakeConn(existing_rows)
with patch.object(A, 'get_db_connection', return_value=conn):
    res = A.save_custom_zones_to_file([])
assert res is False and not conn.committed
ok("payload ว่าง + DB มี zone -> ปฏิเสธ ไม่ commit")

print("\n[5] save_custom_zones_to_file — ตรวจจับสาขาหาย (suspicious)")
conn = FakeConn([{'zone_id': 'Z1', 'zone_name': 'Zone1',
                  'branch_ids': ['101', '102', '103', '104', '105']}])
logged = []
with patch.object(A, 'get_db_connection', return_value=conn), \
     patch.object(A, 'log_zone_change', side_effect=lambda e: logged.append(e)):
    res = A.save_custom_zones_to_file([{'zone_id': 'Z1', 'zone_name': 'Zone1',
                                        'branch_ids': ['101', '102']}])
assert res is True and conn.committed
assert len(logged) == 1, logged
e = logged[0]
assert e['action'] == 'updated' and e['suspicious'] is True
assert e['removed'] == ['103', '104', '105'] and e['branches_before'] == 5
ok(f"บันทึก audit: -3 สาขา, suspicious={e['suspicious']}, removed={e['removed']}")

print("\n[6] save_custom_zones_to_file — zone ใหม่ + ไม่แตะ zone อื่น")
conn = FakeConn([{'zone_id': 'Z1', 'zone_name': 'Zone1', 'branch_ids': ['101']}])
logged = []
with patch.object(A, 'get_db_connection', return_value=conn), \
     patch.object(A, 'log_zone_change', side_effect=lambda e: logged.append(e)):
    A.save_custom_zones_to_file([
        {'zone_id': 'Z1', 'zone_name': 'Zone1', 'branch_ids': ['101']},   # unchanged
        {'zone_id': 'Z2', 'zone_name': 'Zone2', 'branch_ids': ['102']},   # created
    ])
actions = [e['action'] for e in logged]
assert actions == ['created'], actions
deletes = [s for s, p in conn.cur.executed if 'DELETE' in s.upper()]
assert not deletes, deletes
ok("zone เดิมไม่ถูก DELETE, log เฉพาะที่เปลี่ยนจริง")

print("\n[7] backfill-range — validation")
A.app.config['TESTING'] = True
os.environ.pop('CRON_SECRET', None)
c = A.app.test_client()
r = c.post('/api/admin/backfill-range', json={})
assert r.status_code == 400, r.status_code
ok("ไม่ส่งวันที่ -> 400")

r = c.post('/api/admin/backfill-range', json={'date_start': '31/07/2026', 'date_end': '01/07/2026'})
assert r.status_code == 400 and 'ไม่เกิน' in r.get_json()['error']
ok("date_start > date_end -> 400")

r = c.post('/api/admin/backfill-range', json={'date_start': '01/01/2026', 'date_end': '31/12/2027'})
assert r.status_code == 400 and 'ยาวเกินไป' in r.get_json()['error']
ok("ช่วงเกิน 366 วัน -> 400")

r = c.post('/api/admin/backfill-range',
           json={'date_start': '2026-07-01', 'date_end': '2026-07-31', 'dry_run': True})
d = r.get_json()
assert d['total_days'] == 31, d
assert d['dates'][0] == '01/07/2026' and d['dates'][-1] == '31/07/2026'
ok(f"dry_run รับ YYYY-MM-DD ได้ -> {d['total_days']} วัน ({d['dates'][0]} .. {d['dates'][-1]})")

print("\n[8] backfill-range — auth")
os.environ['CRON_SECRET'] = 'secret123'
r = c.post('/api/admin/backfill-range', json={'date_start': '01/07/2026', 'date_end': '02/07/2026'})
assert r.status_code == 401
r = c.post('/api/admin/backfill-range',
           json={'date_start': '01/07/2026', 'date_end': '02/07/2026', 'dry_run': True},
           headers={'Authorization': 'Bearer secret123'})
assert r.status_code == 200
ok("ไม่มี token -> 401 / มี token -> 200")

print("\n[9] refresh-branches-cron — time guard")
with patch.object(A, 'get_system_setting', return_value='23:59'):
    r = c.get('/api/admin/refresh-branches-cron', headers={'Authorization': 'Bearer secret123'})
    d = r.get_json()
assert r.status_code == 200 and d.get('skipped'), d
ok(f"ยังไม่ถึงเวลา -> skip ({d['message']})")

print("\n" + "=" * 55)
print("✅ ผ่านทั้งหมด 9 กลุ่มทดสอบ")
print("=" * 55)
