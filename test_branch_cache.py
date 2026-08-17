"""ทดสอบ cache รายชื่อสาขา — ต้องเห็นสาขาใหม่จาก DB ไม่ใช่แค่ไฟล์เก่า"""
import os, sys, time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('POSTGRES_URL_NON_POOLING', '')

import app as A

ok = lambda m: print(f"  ✅ {m}")

# สาขาใหม่ที่มีเฉพาะใน DB (เกิน branch_id 1504 ของไฟล์เก่า)
DB_BRANCHES = [
    {'branch_id': '107',  'branch_name': '00352 : ID352 : Studio 7-ITplaza-Ubon Ratchathani'},
    {'branch_id': '1748', 'branch_name': '03067 : ID3067 : Studio7-Lotus-Bangna'},
    {'branch_id': '1781', 'branch_name': '02880 : ID2880 : Studio7-Lotus-Maesai-Chiang Rai'},
]

print("\n[1] เดิม: ไฟล์อย่างเดียว -> สาขาใหม่หาไม่เจอ")
A.invalidate_branches_cache()
with patch.object(A, 'get_branches_from_db', return_value=[]):
    old_new = A.find_branch_by_sequential_id('1748')
    old_legacy = A.find_branch_by_sequential_id('107')
assert old_new is None, old_new
assert old_legacy and 'ID352' in old_legacy['branch_name']
ok("DB ว่าง -> 1748 หาไม่เจอ (เหมือนบั๊กเดิม) แต่ 107 ยังเจอจากไฟล์")

print("\n[2] ใหม่: DB มีข้อมูล -> เจอสาขาใหม่")
A.invalidate_branches_cache()
with patch.object(A, 'get_branches_from_db', return_value=DB_BRANCHES):
    b = A.find_branch_by_sequential_id('1748')
    b2 = A.find_branch_by_sequential_id('1781')
assert b and 'ID3067' in b['branch_name'], b
assert b2 and 'ID2880' in b2['branch_name'], b2
ok(f"1748 -> {b['branch_name'][:40]}")
ok(f"1781 -> {b2['branch_name'][:40]}")

print("\n[3] สาขาเก่าที่ไฟล์มีแต่ DB ไม่มี ต้องยังหาเจอ (ไม่ regress)")
A.invalidate_branches_cache()
with patch.object(A, 'get_branches_from_db', return_value=DB_BRANCHES):
    b = A.find_branch_by_sequential_id('1')
assert b is not None, "สาขาเก่าหายไป = regression"
ok(f"branch_id 1 -> {b['branch_name'][:45]}")

print("\n[4] DB ทับไฟล์เมื่อข้อมูลไม่ตรงกัน")
A.invalidate_branches_cache()
changed = [{'branch_id': '1', 'branch_name': '99999 : ID99999 : ชื่อใหม่จาก DB'}]
with patch.object(A, 'get_branches_from_db', return_value=changed):
    b = A.find_branch_by_sequential_id('1')
assert 'ID99999' in b['branch_name'], b
ok("DB เป็น source of truth ทับค่าจากไฟล์")

print("\n[5] DB ล่ม -> ยังใช้ไฟล์ได้ ไม่ crash")
A.invalidate_branches_cache()
def boom():
    raise RuntimeError('DB down')
with patch.object(A, 'get_branches_from_db', side_effect=boom):
    b = A.find_branch_by_sequential_id('107')
assert b and 'ID352' in b['branch_name']
ok("DB ล่ม -> fallback ไปไฟล์ ทำงานต่อได้")

print("\n[6] cache หมดอายุแล้วโหลดใหม่")
A.invalidate_branches_cache()
calls = []
def counting():
    calls.append(1)
    return DB_BRANCHES
with patch.object(A, 'get_branches_from_db', side_effect=counting):
    A.find_branch_by_sequential_id('107')
    A.find_branch_by_sequential_id('107')
    A.find_branch_by_sequential_id('107')
    assert len(calls) == 1, f"ควรเรียก DB ครั้งเดียว ได้ {len(calls)}"
    A._BRANCHES_CACHE_TS = time.time() - (A._BRANCHES_CACHE_TTL + 1)
    A.find_branch_by_sequential_id('107')
    assert len(calls) == 2, f"หมดอายุแล้วควรโหลดใหม่ ได้ {len(calls)}"
ok(f"เรียก DB {len(calls)} ครั้ง (cache ทำงาน + หมดอายุแล้วโหลดใหม่)")

print("\n[7] อัปเดตสาขาแล้ว cache ถูกล้างทันที")
A.invalidate_branches_cache()
with patch.object(A, 'get_branches_from_db', return_value=[]):
    assert A.find_branch_by_sequential_id('1748') is None
class FakeCur:
    def execute(s, *a): pass
    def close(s): pass
class FakeConn:
    def cursor(s): return FakeCur()
    def commit(s): pass
    def close(s): pass
with patch.object(A, 'get_db_connection', return_value=FakeConn()):
    A.save_branches_to_db(DB_BRANCHES)
assert A._BRANCHES_DICT_CACHE is None, "save_branches_to_db ต้องล้าง cache"
with patch.object(A, 'get_branches_from_db', return_value=DB_BRANCHES):
    assert A.find_branch_by_sequential_id('1748') is not None
ok("หลังบันทึกสาขาใหม่ cache ถูกล้าง สาขาใหม่ใช้ได้ทันที")

print("\n[8] get_real_branch_id แปลง ID ได้ถูกต้อง")
A.invalidate_branches_cache()
with patch.object(A, 'get_branches_from_db', return_value=DB_BRANCHES):
    b = A.find_branch_by_sequential_id('1748')
    real = A.get_real_branch_id(b)
assert real == '3067', real
ok(f"zone id 1748 -> real_branch_id {real} (เดิมได้ 1748 ซึ่งหาใน Turso ไม่เจอ)")

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 8 กลุ่มทดสอบ (branch cache)")
print("=" * 58)
