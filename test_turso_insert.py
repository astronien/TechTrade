"""ทดสอบการเขียนข้อมูลลง Turso — mock HTTP ทั้งหมด ไม่แตะ Turso จริง"""
import os, sys, json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['TURSO_DATABASE_URL'] = 'libsql://fake.turso.io'
os.environ['TURSO_AUTH_TOKEN'] = 'faketoken'
os.environ['TURSO_BATCH_SIZE'] = '200'
os.environ['TURSO_HTTP_TIMEOUT'] = '60'
os.environ['TURSO_MAX_RETRIES'] = '2'

import importlib
import turso_handler as T
importlib.reload(T)

ok = lambda m: print(f"  ✅ {m}")


def make_trades(n):
    return [{'trade_in_id': f'T{i}', 'branch_id': '645',
             'branch_name': '00645 : ID645 : Studio 7',
             'document_no': f'D{i}', 'document_date': '12/08/2026',
             'amount': 100, 'net_price': 100} for i in range(n)]


def resp(status=200, results=None, n=0):
    r = MagicMock()
    r.status_code = status
    r.text = 'error body'
    r.json.return_value = {'results': results if results is not None
                           else [{'type': 'ok'} for _ in range(n)]}
    return r


def handler():
    h = T.TursoHandler()
    h.client = None          # บังคับใช้ HTTP path
    return h


print("\n[1] เดิม: ส่ง 1885 รายการในคำขอเดียว -> timeout -> เขียนไม่ลงเลย")
print("    ใหม่: แบ่งเป็นก้อนละ 200")
calls = []
def capture(url, headers=None, json=None, timeout=None):
    calls.append({'n': len(json['requests']), 'timeout': timeout})
    return resp(n=len(json['requests']))

with patch.object(T.requests, 'post', side_effect=capture):
    written = handler().insert_trades_batch(make_trades(1885), 'Studio7')

assert written == 1885, written
assert len(calls) == 10, f"ควรแบ่ง 10 ก้อน แต่ได้ {len(calls)}"
assert max(c['n'] for c in calls) == 200, calls
assert calls[0]['timeout'] == 60, calls[0]
ok(f"1885 รายการ -> {len(calls)} ก้อน (สูงสุด 200/ก้อน), timeout 60s, เขียนสำเร็จ {written}")

print("\n[2] Turso ตอบ HTTP 500 -> ต้องคืน 0 ไม่ใช่หลอกว่าสำเร็จ")
with patch.object(T.requests, 'post', return_value=resp(status=500)):
    written = handler().insert_trades_batch(make_trades(50), 'Z')
assert written == 0, written
ok("HTTP 500 -> คืน 0 (ของเดิมคืน True แล้วรายงานว่าเขียนครบ)")

print("\n[3] Turso ตอบ 200 แต่มี error รายคำสั่ง -> ต้องไม่นับว่าสำเร็จ")
mixed = [{'type': 'ok'}] * 30 + [{'type': 'error',
         'error': {'message': 'SQLITE_FULL: database or disk is full'}}] * 20
with patch.object(T.requests, 'post', return_value=resp(results=mixed)):
    written = handler().insert_trades_batch(make_trades(50), 'Z')
assert written == 30, written
ok(f"30 ok + 20 error -> คืน 30 (ของเดิมคืน 50)")

print("\n[4] timeout -> retry ตามจำนวนที่ตั้งไว้ แล้วคืน 0")
attempts = []
def timeout_post(url, headers=None, json=None, timeout=None):
    attempts.append(1)
    raise T.requests.exceptions.Timeout('timed out')
with patch.object(T.requests, 'post', side_effect=timeout_post):
    written = handler().insert_trades_batch(make_trades(10), 'Z')
assert written == 0, written
assert len(attempts) == 3, f"ควรลอง 1+2 retry = 3 ครั้ง ได้ {len(attempts)}"
ok(f"timeout -> ลอง {len(attempts)} ครั้ง แล้วคืน 0")

print("\n[5] ก้อนแรกพัง ก้อนหลังผ่าน -> นับเฉพาะที่สำเร็จ")
state = {'i': 0}
def flaky(url, headers=None, json=None, timeout=None):
    state['i'] += 1
    n = len(json['requests'])
    # 3 ครั้งแรก = ก้อนที่ 1 (พังทุก retry), ที่เหลือผ่าน
    if state['i'] <= 3:
        raise T.requests.exceptions.ConnectionError('boom')
    return resp(n=n)
with patch.object(T.requests, 'post', side_effect=flaky):
    written = handler().insert_trades_batch(make_trades(500), 'Z')
assert written == 300, written
ok(f"ก้อนแรก (200) พัง, อีก 2 ก้อนผ่าน -> คืน {written} ไม่ใช่ 500")

print("\n[6] client.batch สำเร็จ -> ก็ต้องแบ่งก้อนเหมือนกัน")
batches = []
h = T.TursoHandler()
h.client = MagicMock()
h.client.batch.side_effect = lambda c: batches.append(len(c)) or [None] * len(c)
with patch.object(T, 'HAS_LIBSQL', True):
    written = h.insert_trades_batch(make_trades(450), 'Z')
assert written == 450, written
assert batches == [200, 200, 50], batches
ok(f"client.batch แบ่งเป็น {batches} รวม {written}")

print("\n[7] client.batch พัง -> fallback ไป HTTP และยังนับผลจริง")
h = T.TursoHandler()
h.client = MagicMock()
h.client.batch.side_effect = RuntimeError('event loop closed')
with patch.object(T, 'HAS_LIBSQL', True), \
     patch.object(T.requests, 'post', return_value=resp(status=500)):
    written = h.insert_trades_batch(make_trades(20), 'Z')
assert written == 0, written
ok("client พัง -> ใช้ HTTP fallback, HTTP พังด้วย -> คืน 0 ตามจริง")

print("\n[8] ไม่มีข้อมูล -> คืน 0 ไม่ยิง HTTP")
posted = []
with patch.object(T.requests, 'post', side_effect=lambda *a, **k: posted.append(1)):
    assert handler().insert_trades_batch([], 'Z') == 0
assert not posted
ok("รายการว่าง -> คืน 0 ไม่ยิง HTTP")

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 8 กลุ่มทดสอบ (การเขียนลง Turso)")
print("=" * 58)
