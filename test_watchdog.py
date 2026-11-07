"""ทดสอบ sync-watchdog และการวน chunk ของ cron — mock DB ทั้งหมด"""
import os, sys
from datetime import datetime, timedelta, date, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('POSTGRES_URL_NON_POOLING', '')

import app as A
import pytz

ok = lambda m: print(f"  ✅ {m}")
BKK = pytz.timezone('Asia/Bangkok')
NOW = datetime.now(BKK)


class FakeCur:
    """คืนค่าตามลำดับ query: last sync_progress, last log, แล้วตารางรายวัน"""
    def __init__(s, last_sp, last_log, per_day):
        s.last_sp, s.last_log, s.per_day = last_sp, last_log, per_day
        s.mode = None
    def execute(s, sql, params=None):
        if 'MAX(updated_at)' in sql: s.mode = 'sp'
        elif 'MAX(run_at)' in sql: s.mode = 'log'
        else: s.mode = 'days'
    def fetchone(s):
        return {'v': s.last_sp if s.mode == 'sp' else s.last_log}
    def fetchall(s):
        return [{'sync_date': d, 'done': dn, 'total': t} for d, dn, t in s.per_day]
    def close(s): pass


class FakeConn:
    def __init__(s, cur): s.cur = cur
    def cursor(s): return s.cur
    def close(s): pass


def call(last_sp=None, last_log=None, per_day=(), qs='', secret=None, tg=True):
    A.app.config['TESTING'] = True
    if secret is None:
        os.environ.pop('CRON_SECRET', None)
    else:
        os.environ['CRON_SECRET'] = secret
    sent = []
    cfg = {'telegram_bot_token': 'T', 'telegram_chat_id': 'C'} if tg else {}
    with patch.object(A, 'get_db_connection',
                      return_value=FakeConn(FakeCur(last_sp, last_log, list(per_day)))), \
         patch.object(A, 'get_auto_cancel_config', return_value=cfg), \
         patch.object(A, 'send_telegram_notification',
                      side_effect=lambda b, c, m: sent.append(m) or True):
        headers = {'Authorization': f'Bearer {secret}'} if secret else {}
        r = A.app.test_client().get('/api/admin/sync-watchdog' + qs, headers=headers)
    return r.get_json(), sent


def utc(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


print("\n[1] sync ปกติเมื่อ 2 ชั่วโมงก่อน -> OK ไม่แจ้งเตือน")
days = [(NOW.date() - timedelta(days=i), 1, 1) for i in range(1, 8)]
d, sent = call(last_sp=utc(NOW - timedelta(hours=2)), per_day=days)
assert d['status'] == 'OK' and d['stale'] is False, d
assert d['incomplete_days'] == [] and not sent, d
ok(f"เงียบ {d['hours_since']} ชม. -> OK, ไม่ส่ง Telegram")

print("\n[2] เงียบ 6 วัน (เคสจริง 1-7 พ.ย.) -> ALERT")
d, sent = call(last_sp=utc(NOW - timedelta(hours=144)), per_day=[], secret='s1')
assert d['stale'] is True and d['status'] == 'ALERT', d
assert d['hours_since'] >= 143, d
assert len(sent) == 1, sent
assert 'เงียบมาแล้ว' in sent[0] and 'ชั่วโมง' in sent[0]
assert 'disabled_inactivity' in sent[0], 'ข้อความควรบอกให้เช็ค GitHub ก่อน'
ok(f"เงียบ {d['hours_since']:.0f} ชม. -> แจ้งเตือน + บอกวิธีตรวจ")

print("\n[3] บอกได้ว่าวันไหนข้อมูลไม่ครบ")
assert len(d['incomplete_days']) == 7, d['incomplete_days']
assert all(x['note'] == 'ไม่เคยเริ่ม sync' for x in d['incomplete_days'])
ok(f"ไล่ย้อน 7 วัน เจอไม่ครบ {len(d['incomplete_days'])} วัน")

print("\n[4] sync ล่าสุดปกติ แต่มีวันที่ค้างกลางทาง -> ยัง ALERT")
mixed = [(NOW.date() - timedelta(days=1), 1, 1),
         (NOW.date() - timedelta(days=2), 0, 1),
         (NOW.date() - timedelta(days=3), 1, 1)]
d, sent = call(last_sp=utc(NOW - timedelta(hours=3)), per_day=mixed,
               qs='?days=3', secret='s1')
assert d['stale'] is False, d
assert d['status'] == 'ALERT', d
dates = [x['date'] for x in d['incomplete_days']]
assert str(NOW.date() - timedelta(days=2)) in dates, d['incomplete_days']
assert len(sent) == 1 and 'ข้อมูลไม่ครบ' in sent[0]
ok('sync ยังเดินอยู่ แต่จับวันที่ zone ค้างได้ -> ยังเตือน')

print("\n[5] ไม่เคย sync สำเร็จเลย")
d, sent = call(last_sp=None, last_log=None, per_day=[], secret='s1')
assert d['hours_since'] is None and d['stale'] is True
assert 'ไม่พบประวัติ sync' in sent[0]
ok('ไม่มีประวัติเลย -> แจ้งเตือนด้วยข้อความคนละแบบ')

print("\n[6] ใช้ log เป็นตัวเทียบถ้าใหม่กว่า sync_progress")
d, _ = call(last_sp=utc(NOW - timedelta(hours=50)),
            last_log=utc(NOW - timedelta(hours=2)), per_day=days)
assert d['last_sync_source'] == 'auto_export_log', d
assert d['stale'] is False
ok('เลือกค่าที่ใหม่กว่าระหว่าง sync_progress กับ auto_export_log')

print("\n[7] ไม่มี CRON_SECRET -> อ่านได้ แต่ไม่ส่ง Telegram")
d, sent = call(last_sp=utc(NOW - timedelta(hours=100)), per_day=[], secret='s1')
assert sent, 'มี secret ควรส่ง'
A_sent = len(sent)
os.environ['CRON_SECRET'] = 's1'
with patch.object(A, 'get_db_connection',
                  return_value=FakeConn(FakeCur(utc(NOW - timedelta(hours=100)), None, []))), \
     patch.object(A, 'get_auto_cancel_config',
                  return_value={'telegram_bot_token': 'T', 'telegram_chat_id': 'C'}), \
     patch.object(A, 'send_telegram_notification', side_effect=AssertionError('ไม่ควรส่ง')):
    r = A.app.test_client().get('/api/admin/sync-watchdog')
d2 = r.get_json()
assert d2['authorized'] is False and d2['will_notify'] is False
assert d2['stale'] is True, d2
ok('ไม่มี secret -> ดูสถานะได้ ไม่มี side effect')

print("\n[8] notify=0 ปิดการแจ้งเตือนได้")
d, sent = call(last_sp=utc(NOW - timedelta(hours=100)), per_day=[],
               qs='?notify=0', secret='s1')
assert d['will_notify'] is False and not sent
ok('notify=0 -> ตรวจเฉยๆ ไม่ส่ง')

print("\n[9] threshold ปรับได้")
d, _ = call(last_sp=utc(NOW - timedelta(hours=20)), per_day=days, qs='?hours=12')
assert d['stale'] is True, d
d, _ = call(last_sp=utc(NOW - timedelta(hours=20)), per_day=days, qs='?hours=48')
assert d['stale'] is False, d
ok('hours=12 -> stale / hours=48 -> ปกติ')

print("\n[10] vercel.json มี cron ครบและถูกรูปแบบ")
import json
vj = json.load(open('vercel.json'))
paths = {c['path'] for c in vj['crons']}
assert paths == {'/api/admin/auto-export-cron', '/api/admin/sync-watchdog'}, paths
for c in vj['crons']:
    f = c['schedule'].split()
    assert len(f) == 5, c
    assert f[1] != '*' and f[2] == '*', f'ต้องเป็นวันละครั้ง (Hobby): {c}'
ok('2 cron วันละครั้ง ตามข้อจำกัด Hobby plan')

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 10 กลุ่มทดสอบ (watchdog + vercel cron)")
print("=" * 58)
