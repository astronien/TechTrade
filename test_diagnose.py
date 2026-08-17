"""ทดสอบ collect_report + endpoint ด้วย SQLite จำลอง"""
import os, sys, sqlite3, json
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['TURSO_DATABASE_URL'] = 'libsql://fake'
os.environ['TURSO_AUTH_TOKEN'] = 'x'

db = '/tmp/fake2.db'
if os.path.exists(db): os.remove(db)
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE trades (trade_in_id TEXT, real_branch_id TEXT, document_date TEXT, zone_name TEXT);
CREATE TABLE sync_history (branch_id TEXT, sync_date TEXT, record_count INT, synced_at TEXT);
""")
today = date.today(); start = today - timedelta(days=59); i = 0; d = start
while d <= today:
    ds = d.strftime('%Y-%m-%d')
    for _ in range(30):
        i += 1; con.execute("INSERT INTO trades VALUES (?,?,?,?)", (f'T{i}','645',ds,'Z'))
    if (d - start).days < 5:
        for _ in range(28):
            i += 1; con.execute("INSERT INTO trades VALUES (?,?,?,?)", (f'T{i}','700',ds,'Z'))
    d += timedelta(days=1)
gap = (start + timedelta(days=20)).strftime('%Y-%m-%d')
con.execute("DELETE FROM trades WHERE document_date = ?", (gap,))
con.execute("INSERT INTO sync_history VALUES ('700','01/06/2026-31/07/2026',140,'2026-08-01')")
con.commit(); con.close()

class FakeRes:
    def __init__(s, cur, rows): s.columns=[c[0] for c in (cur.description or [])]; s.rows=rows

import turso_handler as T
class FakeTurso(T.TursoHandler):
    def __init__(s, *a, **k):
        s.url='libsql://fake'; s.token='x'; s.client=None; s.con=sqlite3.connect(db)
    def _execute_sql(s, sql, params=None):
        cur = s.con.execute(sql, params or []); return FakeRes(cur, cur.fetchall())
    def close(s):
        try: s.con.close()
        except Exception: pass

ok = lambda m: print(f"  ✅ {m}")

print("\n[1] collect_report คืน dict ที่มีข้อมูลครบ")
import diagnose_turso as D
rep = D.collect_report(FakeTurso(), months=3)
assert rep['overview']['total_rows'] > 0
assert len(rep['missing_days']) >= 1
assert any(m['date'] == gap for m in rep['missing_days']), gap
assert len(rep['sync_history_range_keys']) == 1
assert rep['sync_history_range_keys'][0]['branch_id'] == '700'
assert rep['issues']
ok(f"เจอ {len(rep['missing_days'])} วันที่ขาด, {len(rep['sync_history_range_keys'])} คีย์ช่วงวันที่")

print("\n[2] เจอสาขาที่ข้อมูลน้อยผิดปกติ")
assert any(s['branch_id'] == '700' for s in rep['suspicious_branch_months']), rep['suspicious_branch_months']
ok(f"สาขา 700 ถูกจับได้ ({len(rep['suspicious_branch_months'])} คู่สาขาxเดือน)")

print("\n[3] print_report ไม่ crash")
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    D.print_report(rep)
out = buf.getvalue()
assert 'sync_history' in out and 'สรุป' in out
ok(f"พิมพ์ได้ {len(out.splitlines())} บรรทัด")

print("\n[4] endpoint /api/admin/diagnose-turso — JSON")
import app as A
A.app.config['TESTING'] = True
c = A.app.test_client()
with patch.object(A, 'TursoHandler', FakeTurso):
    r = c.get('/api/admin/diagnose-turso?months=3')
d = r.get_json()
assert r.status_code == 200 and d['success'], d
assert 'missing_days' in d and 'sync_history_range_keys' in d
assert 'per_day' not in d, "ควรตัดข้อมูลดิบออกเมื่อไม่ใส่ full=1"
ok(f"ตอบ JSON ({len(json.dumps(d))} ไบต์), ตัดข้อมูลดิบออกแล้ว")

print("\n[5] full=1 มีข้อมูลดิบ")
with patch.object(A, 'TursoHandler', FakeTurso):
    d2 = c.get('/api/admin/diagnose-turso?months=3&full=1').get_json()
assert 'per_day' in d2 and 'branches_in_turso' in d2
ok("full=1 แนบ per_day และ branches_in_turso มาด้วย")

print("\n[6] format=text อ่านง่าย")
with patch.object(A, 'TursoHandler', FakeTurso):
    r = c.get('/api/admin/diagnose-turso?months=3&format=text')
txt = r.get_data(as_text=True)
assert r.status_code == 200 and 'สรุป' in txt
assert 'text/plain' in r.headers['Content-Type']
ok(f"ตอบข้อความ {len(txt.splitlines())} บรรทัด")

print("\n[7] months ถูกจำกัด 1-24")
with patch.object(A, 'TursoHandler', FakeTurso):
    assert c.get('/api/admin/diagnose-turso?months=999').get_json()['months'] == 24
    assert c.get('/api/admin/diagnose-turso?months=0').get_json()['months'] == 1
ok("months=999 -> 24, months=0 -> 1")

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 7 กลุ่มทดสอบ (diagnose)")
print("=" * 58)
