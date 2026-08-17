"""ทดสอบว่าสาขาที่ดึงไม่สำเร็จถูกจับได้ ไม่ถูกเหมาว่าสำเร็จแล้วลบข้อมูลทิ้ง"""
import os, sys
from datetime import date, datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('POSTGRES_URL_NON_POOLING', '')
os.environ['TURSO_DATABASE_URL'] = 'libsql://fake'
os.environ['TURSO_AUTH_TOKEN'] = 'x'

import app as A
import auto_daily_export as AE

ok = lambda m: print(f"  ✅ {m}")

print("\n[1] fetch_all_for_branch: Eve error -> strict ต้อง raise")
with patch.object(A, 'fetch_data_with_retry', return_value={'error': 'session expired'}):
    assert A.fetch_all_for_branch({'branch_id': '231'}) == []          # เดิม
    try:
        A.fetch_all_for_branch({'branch_id': '231'}, strict=True)
        raise AssertionError("ควร raise BranchFetchError")
    except A.BranchFetchError as e:
        assert 'session expired' in str(e)
ok("strict=False คืน [] (เหมือนเดิม) / strict=True raise พร้อมสาเหตุ")

print("\n[2] ดึงได้ไม่ครบตามที่ Eve บอก -> strict ต้อง raise")
resp = {'data': [{'trade_in_id': i} for i in range(500)], 'recordsFiltered': 500}
resp2 = {'data': [], 'recordsFiltered': 900}
seq = [dict(resp, recordsFiltered=900), resp2]
def paged(**kw):
    return seq.pop(0) if seq else resp2
with patch.object(A, 'fetch_data_with_retry', side_effect=paged):
    try:
        A.fetch_all_for_branch({'branch_id': '231'}, strict=True)
        raise AssertionError("ควร raise เพราะได้ 500/900")
    except A.BranchFetchError as e:
        assert '500/900' in str(e), str(e)
ok("Eve บอกมี 900 แต่ได้ 500 -> raise ไม่ปล่อยผ่านเงียบๆ")

print("\n[3] ไม่มีรายการจริงๆ -> ต้องไม่ raise")
with patch.object(A, 'fetch_data_with_retry', return_value={'data': [], 'recordsFiltered': 0}):
    assert A.fetch_all_for_branch({'branch_id': '231'}, strict=True) == []
ok("สาขาไม่มีเทรดจริง -> คืน [] ไม่ raise (แยกจากกรณีดึงพลาดได้)")

print("\n[4] fetch_zone_daily_data บอกได้ว่าสาขาไหนพลาด")
zone = {'zone_name': 'Z', 'branch_ids': ['1', '2', '3']}
def flaky(filters, strict=False):
    if filters['branch_id'] == '2':
        raise A.BranchFetchError('Branch 2: timeout')
    return [{'trade_in_id': f"{filters['branch_id']}-1",
             'branch_name': f"ID{filters['branch_id']} : x"}]
with patch.object(A, 'fetch_all_for_branch', flaky):
    items, all_ok, failed = AE.fetch_zone_daily_data(zone, datetime(2026, 8, 14))
assert all_ok is False, all_ok
assert [f['branch_id'] for f in failed] == ['2'], failed
assert len(items) == 2, len(items)
ok(f"สาขา 2 พลาด -> all_success=False, failed={[f['branch_id'] for f in failed]}, ได้ข้อมูล 2 สาขา")

print("\n[5] สาขาที่พลาดชั่วคราว -> ลองใหม่รอบ 2 แล้วสำเร็จ")
calls = {'n': 0}
def flaky_once(filters, strict=False):
    if filters['branch_id'] == '2':
        calls['n'] += 1
        if calls['n'] == 1:
            raise A.BranchFetchError('ชั่วคราว')
    return [{'trade_in_id': f"{filters['branch_id']}-1",
             'branch_name': f"ID{filters['branch_id']} : x"}]
with patch.object(A, 'fetch_all_for_branch', flaky_once):
    items, all_ok, failed = AE.fetch_zone_daily_data(zone, datetime(2026, 8, 14))
assert all_ok is True and failed == [], (all_ok, failed)
assert len(items) == 3, len(items)
ok("พลาดรอบแรก -> retry ทีละสาขา -> สำเร็จครบ 3 สาขา")

print("\n[6] reconcile_branches จับสาขาที่เขียนไม่ครบ")
import turso_handler as T
class FakeT(T.TursoHandler):
    def __init__(s, turso_rows):
        s.url='libsql://f'; s.token='x'; s.client=None; s._rows = turso_rows
    def _execute_sql(s, sql, params=None):
        class R: pass
        r = R(); r.columns = ['real_branch_id', 'c']; r.rows = s._rows
        return r
eve_items = ([{'trade_in_id': f'a{i}', 'branch_name': '00645 : ID645 : Westgate'} for i in range(33)]
             + [{'trade_in_id': f'b{i}', 'branch_name': '00231 : ID231 : Other'} for i in range(10)])
res = FakeT([('645', 33), ('231', 10)]).reconcile_branches(eve_items, 'Z', '2026-08-14')
assert res['mismatches'] == [], res
res2 = FakeT([('231', 10)]).reconcile_branches(eve_items, 'Z', '2026-08-14')
assert len(res2['mismatches']) == 1
assert res2['mismatches'][0] == {'branch_id': '645', 'eve': 33, 'turso': 0}, res2
ok(f"Eve มี 33 แต่ Turso มี 0 -> จับได้: {res2['mismatches'][0]}")

print("\n[7] มีสาขาพลาด -> zone ต้องไม่ถูก mark ว่า done")
PROGRESS = {}
def fake_save(d, zid, zname, status, records=0, attempts=1, last_error=''):
    PROGRESS[(d, str(zid))] = {'status': status, 'attempts': attempts}
    return True
class FakeTurso2:
    def __init__(s, *a, **k): pass
    def init_db(s): return True
    def delete_zone_records(s, *a): PROGRESS['deleted'] = True; return True
    def insert_trades_batch(s, data, zone): return len(data)
    def reconcile_snapshot(s, data, zone, d):
        return {'success': True, 'turso_count': len(data), 'missing_count': 0,
                'extra_count': 0, 'checksum_match': True}
    def reconcile_branches(s, data, zone, d): return {'mismatches': [], 'branches_checked': 1}
    def close(s): pass

ZONES = [{'zone_id': 'Z1', 'zone_name': 'Zone1', 'branch_ids': ['1', '2']}]
patches = [
    patch.object(AE, 'get_auto_export_config', lambda: {'enabled': True, 'zone_ids': []}),
    patch.object(AE, 'TursoHandler', FakeTurso2),
    patch.object(AE, 'get_sync_progress', lambda d: {}),
    patch.object(AE, 'save_sync_progress', fake_save),
    patch.object(AE, 'save_auto_sync_log', lambda x: None),
    patch.object(AE, 'fetch_zone_daily_data',
                 lambda z, t: ([{'trade_in_id': '1', 'branch_name': 'ID1 : a'}],
                               False, [{'branch_id': '2', 'error': 'timeout'}])),
    patch.object(A, 'load_custom_zones_from_file', lambda: list(ZONES)),
    patch.object(A, 'get_branches_from_db', lambda: []),
    patch.object(A, 'get_auto_cancel_config', lambda: {}),
]
for p in patches: p.start()
try:
    r = AE.run_daily_export(force=True, target_dt=datetime(2026, 8, 14), time_budget=9999)
finally:
    for p in patches: p.stop()

st = PROGRESS.get((date(2026, 8, 14), 'Z1'), {}).get('status')
assert st == 'failed', f"ควรเป็น failed เพื่อให้ลองใหม่ ได้ {st}"
assert 'deleted' not in PROGRESS, "ห้ามลบข้อมูลเดิมเมื่อมีสาขาดึงไม่สำเร็จ"
assert r['completed'] is False, r['completed']
assert r['total_warnings'] == 1, r['total_warnings']
ok(f"สาขาพลาด -> zone status='{st}', ไม่ลบข้อมูลเดิม, completed=False")

print("\n[8] ทุกสาขาสำเร็จ -> done ตามปกติ")
PROGRESS.clear()
patches[5] = patch.object(AE, 'fetch_zone_daily_data',
                          lambda z, t: ([{'trade_in_id': '1', 'branch_name': 'ID1 : a'}], True, []))
for p in patches: p.start()
try:
    r = AE.run_daily_export(force=True, target_dt=datetime(2026, 8, 14), time_budget=9999)
finally:
    for p in patches: p.stop()
st = PROGRESS.get((date(2026, 8, 14), 'Z1'), {}).get('status')
assert st == 'done', st
assert PROGRESS.get('deleted') is True, "ทุกสาขาสำเร็จควรลบของเก่าก่อนเขียนใหม่"
ok("ทุกสาขาสำเร็จ -> status='done' และลบของเก่าก่อนเขียนทับตามปกติ")

print("\n" + "=" * 60)
print("✅ ผ่านทั้งหมด 8 กลุ่มทดสอบ (สาขาดึงไม่สำเร็จ)")
print("=" * 60)
