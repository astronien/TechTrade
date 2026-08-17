"""
diagnose_turso.py — ตรวจข้อมูลจริงใน Turso หาว่ายอดหายไปตรงไหนและเท่าไร

ตรวจ 6 เรื่อง (อ่านอย่างเดียว ไม่แก้ไขอะไรทั้งสิ้น):

  1. ภาพรวมฐานข้อมูล — จำนวนแถว ช่วงวันที่ สาขา zone
  2. วันที่ไม่มีข้อมูลเลยสักแถว = วันที่ไม่เคย sync สำเร็จ (หลักฐานตรงที่สุด)
  3. ความครบรายสาขา×เดือน — เทียบกับค่ากลางของสาขาอื่นในเดือนเดียวกัน
  4. sync_history ที่ใช้คีย์ช่วงวันที่ — ตัวที่ทำให้ระบบเชื่อผิดว่า "ครบแล้ว"
  5. real_branch_id ผิดปกติ — แถวที่ query ด้วย real_branch_id หาไม่เจอ
  6. รูปแบบ document_date — เช็คว่ามี timezone เพี้ยนหรือมีเวลาปนไหม

ใช้ได้ 2 ทาง:

  A) รันจากเครื่องที่มี Turso credential
        python3 diagnose_turso.py --months 6 --json diag.json

  B) เรียกผ่าน endpoint บนเซิร์ฟเวอร์ (credential อยู่บนนั้นอยู่แล้ว)
        GET /api/admin/diagnose-turso?months=6
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta


# ============================================================
# helpers
# ============================================================

def _load_env_file(path):
    """อ่านไฟล์ .env เอง — ไม่พึ่ง python-dotenv เพราะเครื่องอาจไม่ได้ติดตั้ง

    ค่าที่ตั้งไว้ใน environment อยู่แล้วจะไม่ถูกเขียนทับ
    """
    if not os.path.exists(path):
        return []
    keys = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                if line.lower().startswith('export '):
                    line = line[7:].strip()
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    keys.append(key)
                    os.environ.setdefault(key, val)
    except Exception as e:
        print(f"⚠️ อ่าน .env ไม่สำเร็จ: {e}")
    return keys


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


def days_in_month(y, m):
    return (add_months(date(y, m, 1), 1) - timedelta(days=1)).day


def _rows(res):
    if not res:
        return []
    return [tuple(r) for r in res.rows]


THAI_WD = ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา']


# ============================================================
# ตัวตรวจหลัก — คืนผลเป็น dict ล้วนๆ ใช้ได้ทั้ง CLI และ API
# ============================================================

def collect_report(turso, months=6, min_coverage=0.5):
    """ตรวจข้อมูลใน Turso แล้วคืนผลเป็น dict (ไม่พิมพ์อะไร ไม่แก้ข้อมูล)"""
    today = date.today()
    start_d = add_months(month_start(today), -(months - 1))
    iso_start = start_d.strftime('%Y-%m-%d')
    iso_end = today.strftime('%Y-%m-%d')

    report = {'range': [iso_start, iso_end], 'months': months}

    # ---- 1. ภาพรวม ----
    res = turso._execute_sql(
        "SELECT COUNT(*), MIN(document_date), MAX(document_date), "
        "COUNT(DISTINCT real_branch_id), COUNT(DISTINCT zone_name) FROM trades")
    r = _rows(res)
    if not r:
        report['error'] = 'อ่านข้อมูลจาก Turso ไม่ได้'
        return report

    total, dmin, dmax, nbranch, nzone = r[0]
    report['overview'] = {
        'total_rows': int(total or 0), 'min_date': dmin, 'max_date': dmax,
        'branches': int(nbranch or 0), 'zones': int(nzone or 0),
    }

    # ---- 2. วันที่ไม่มีข้อมูล ----
    res = turso._execute_sql(
        "SELECT document_date, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? GROUP BY document_date",
        [iso_start, iso_end])
    per_day = {str(d): int(c) for d, c in _rows(res)}

    counts = sorted(per_day.values())
    median_day = counts[len(counts) // 2] if counts else 0

    missing_days, weak_days = [], []
    d = start_d
    while d <= today:
        key = d.strftime('%Y-%m-%d')
        c = per_day.get(key, 0)
        if c == 0:
            missing_days.append({'date': key, 'weekday': THAI_WD[d.weekday()]})
        elif median_day and c < median_day * 0.2:
            weak_days.append({'date': key, 'records': c})
        d += timedelta(days=1)

    report['median_per_day'] = median_day
    report['missing_days'] = missing_days
    report['weak_days'] = weak_days
    report['per_day'] = per_day

    # ---- 3. ความครบรายสาขา x เดือน ----
    res = turso._execute_sql(
        "SELECT real_branch_id, substr(document_date,1,7) AS ym, "
        "COUNT(DISTINCT document_date), COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? "
        "GROUP BY real_branch_id, ym", [iso_start, iso_end])

    by_month = defaultdict(dict)
    for bid, ym, days, recs in _rows(res):
        by_month[str(ym)][str(bid)] = (int(days), int(recs))

    months_summary, suspicious = [], []
    for ym in sorted(by_month):
        entry = by_month[ym]
        day_counts = sorted(v[0] for v in entry.values())
        if not day_counts:
            continue
        median_days = day_counts[len(day_counts) // 2]
        y, m = int(ym[:4]), int(ym[5:7])
        cal_days = today.day if (y, m) == (today.year, today.month) else days_in_month(y, m)

        bad = []
        for b, (dd, rr) in entry.items():
            if median_days and dd < median_days * min_coverage:
                item = {'month': ym, 'branch_id': b, 'days': dd,
                        'median_days': median_days, 'records': rr,
                        'coverage_pct': round(dd / median_days * 100, 1)}
                bad.append(item)
                suspicious.append(item)

        months_summary.append({
            'month': ym, 'calendar_days': cal_days, 'median_days': median_days,
            'branches': len(entry), 'suspicious': sorted(bad, key=lambda x: x['days']),
        })

    report['months_summary'] = months_summary
    report['suspicious_branch_months'] = suspicious

    # ---- 4. sync_history คีย์ช่วงวันที่ ----
    res = turso._execute_sql("SELECT COUNT(*) FROM sync_history")
    sh_total = int(_rows(res)[0][0]) if _rows(res) else 0

    res = turso._execute_sql(
        "SELECT branch_id, sync_date, record_count, synced_at FROM sync_history "
        "WHERE sync_date LIKE '%/%' ORDER BY synced_at DESC")
    range_rows = [{'branch_id': str(b), 'sync_date': str(s),
                   'record_count': int(c) if c is not None else None,
                   'synced_at': str(a)} for b, s, c, a in _rows(res)]

    report['sync_history_total'] = sh_total
    report['sync_history_range_keys'] = range_rows

    # ---- 5. real_branch_id ผิดปกติ ----
    res = turso._execute_sql(
        "SELECT real_branch_id, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? "
        "GROUP BY real_branch_id ORDER BY COUNT(*) DESC", [iso_start, iso_end])
    branch_rows = [(str(b) if b is not None else '', int(c)) for b, c in _rows(res)]

    weird = [{'value': s or '(ว่าง)', 'rows': c}
             for s, c in branch_rows if not s.strip() or not s.strip().isdigit()]
    report['branches_in_turso'] = [{'branch_id': s, 'rows': c} for s, c in branch_rows]
    report['weird_branch_ids'] = weird

    # เทียบกับสาขาใน zone
    try:
        from app import load_custom_zones_from_file, find_branch_by_sequential_id
        import re
        zones = load_custom_zones_from_file()
        in_db = {s for s, _ in branch_rows}
        zone_cov = []
        for z in zones or []:
            expected = set()
            for bid in (z.get('branch_ids') or []):
                info = find_branch_by_sequential_id(bid)
                if info:
                    mm = re.search(r'ID(\d+)', info.get('branch_name', ''))
                    expected.add(mm.group(1) if mm else str(bid))
                else:
                    expected.add(str(bid))
            never = sorted(expected - in_db)
            zone_cov.append({'zone_name': z.get('zone_name'),
                             'expected': len(expected),
                             'with_data': len(expected) - len(never),
                             'never_synced': never})
        report['zone_coverage'] = zone_cov
    except Exception as e:
        report['zone_coverage_error'] = str(e)

    # ---- 6. รูปแบบ document_date ----
    res = turso._execute_sql(
        "SELECT LENGTH(document_date) AS L, COUNT(*) FROM trades GROUP BY L ORDER BY COUNT(*) DESC")
    report['date_formats'] = [{'length': int(L) if L is not None else None, 'rows': int(c)}
                              for L, c in _rows(res)]

    res = turso._execute_sql(
        "SELECT document_date, COUNT(*) FROM trades WHERE LENGTH(document_date) != 10 "
        "GROUP BY document_date LIMIT 10")
    report['odd_date_values'] = [{'value': str(v), 'rows': int(c)} for v, c in _rows(res)]

    res = turso._execute_sql(
        "SELECT substr(document_date,9,2) AS dd, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? GROUP BY dd ORDER BY dd",
        [iso_start, iso_end])
    dom = {str(d): int(c) for d, c in _rows(res)}
    report['day_of_month'] = dom
    if dom:
        vals = sorted(dom.values())
        med = vals[len(vals) // 2]
        report['day_of_month_median'] = med
        report['day_of_month_outliers'] = [
            {'day': k, 'records': v} for k, v in sorted(dom.items())
            if med and v < med * 0.4]

    # ---- สรุป ----
    issues = []
    if missing_days:
        issues.append(f"{len(missing_days)} วันไม่มีข้อมูลเลย")
    if suspicious:
        issues.append(f"{len(suspicious)} คู่ (สาขา×เดือน) ข้อมูลน้อยผิดปกติ")
    if range_rows:
        issues.append(f"{len(range_rows)} แถว sync_history ที่ประทับตราผิด")
    if weird:
        issues.append(f"{sum(w['rows'] for w in weird):,} แถวที่ real_branch_id ผิดรูปแบบ")
    never_total = sum(len(z['never_synced']) for z in report.get('zone_coverage', []))
    if never_total:
        issues.append(f"{never_total} สาขาไม่มีข้อมูลเลย")
    report['issues'] = issues

    return report


# ============================================================
# พิมพ์ผลแบบอ่านง่าย (ใช้ตอนรันเป็นสคริปต์)
# ============================================================

def _section(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def print_report(rep):
    if rep.get('error'):
        print(f"❌ {rep['error']}")
        return

    ov = rep['overview']
    _section("1. ภาพรวมฐานข้อมูล")
    print(f"   แถวทั้งหมด      : {ov['total_rows']:,}")
    print(f"   ช่วงวันที่       : {ov['min_date']} ถึง {ov['max_date']}")
    print(f"   จำนวนสาขา       : {ov['branches']}")
    print(f"   จำนวน zone      : {ov['zones']}")

    _section("2. วันที่ไม่มีข้อมูลเลยสักแถว (= ไม่เคย sync สำเร็จ)")
    print(f"   ค่ากลางรายวัน   : {rep['median_per_day']:,} รายการ/วัน")
    print(f"   วันที่ไม่มีข้อมูล : {len(rep['missing_days'])} วัน")
    for m in rep['missing_days'][:40]:
        print(f"      • {m['date']} ({m['weekday']})")
    if len(rep['missing_days']) > 40:
        print(f"      ... และอีก {len(rep['missing_days']) - 40} วัน")
    if rep['weak_days']:
        print(f"\n   วันที่ข้อมูลน้อยผิดปกติ (< 20% ของค่ากลาง): {len(rep['weak_days'])} วัน")
        for w in rep['weak_days'][:20]:
            print(f"      • {w['date']}: {w['records']:,} รายการ")

    _section("3. ความครบของข้อมูล รายสาขา × เดือน")
    for ms in rep['months_summary']:
        print(f"\n   📅 {ms['month']}  (มี {ms['calendar_days']} วันในเดือน, "
              f"สาขาส่วนใหญ่มีข้อมูล {ms['median_days']} วัน)")
        if ms['suspicious']:
            for b in ms['suspicious']:
                print(f"      ⚠️ สาขา {b['branch_id']:>6}: มีข้อมูล {b['days']:>2}/"
                      f"{b['median_days']} วัน ({b['coverage_pct']:.0f}% ของค่ากลาง), "
                      f"{b['records']:,} รายการ")
        else:
            print(f"      ✅ ทุกสาขาข้อมูลใกล้เคียงกัน ({ms['branches']} สาขา)")

    _section("4. sync_history ที่ใช้คีย์ช่วงวันที่ (ตัวที่ทำให้เชื่อผิดว่าครบ)")
    rk = rep['sync_history_range_keys']
    print(f"   แถวทั้งหมดใน sync_history : {rep['sync_history_total']:,}")
    print(f"   แถวที่คีย์เป็นช่วงวันที่     : {len(rk):,}")
    if rk:
        print("\n   ทุกแถวข้างล่างนี้คือการประทับตรา 'sync ครบแล้ว' ที่เชื่อถือไม่ได้")
        print("   ระบบจะใช้แถวเหล่านี้ตอบทันทีโดยไม่ไปถาม Eve อีก\n")
        for r in rk[:30]:
            print(f"      • สาขา {r['branch_id']:>6} | ช่วง {r['sync_date']} | "
                  f"อ้างว่ามี {r['record_count']} รายการ | {r['synced_at']}")
        if len(rk) > 30:
            print(f"      ... และอีก {len(rk) - 30} แถว")
    else:
        print("   ✅ ไม่พบแถวที่ใช้คีย์ช่วงวันที่")

    _section("5. real_branch_id ที่ผิดปกติ (แถวที่รายงานมองไม่เห็น)")
    if rep['weird_branch_ids']:
        print("   ⚠️ พบแถวที่ real_branch_id ไม่ใช่ตัวเลข")
        print("      รายงานกรองด้วย `real_branch_id IN (...)` ที่ส่งแต่ตัวเลข")
        print("      แถวเหล่านี้จึงไม่ถูกนับในยอดเลย\n")
        for w in rep['weird_branch_ids']:
            print(f"      • '{w['value']}' : {w['rows']:,} รายการ")
    else:
        print(f"   ✅ real_branch_id เป็นตัวเลขทั้งหมด "
              f"({len(rep['branches_in_turso'])} สาขา)")

    for z in rep.get('zone_coverage', []):
        print(f"\n   🗺️ Zone {z['zone_name']}: {z['expected']} สาขาใน zone, "
              f"{z['with_data']} สาขามีข้อมูลใน Turso")
        if z['never_synced']:
            print(f"      ❌ ไม่มีข้อมูลเลยสักแถว {len(z['never_synced'])} สาขา: "
                  f"{z['never_synced'][:20]}")
    if rep.get('zone_coverage_error'):
        print(f"   (ข้ามการเทียบกับ zone: {rep['zone_coverage_error']})")

    _section("6. รูปแบบ document_date")
    print("   ความยาวของค่า document_date:")
    for f in rep['date_formats']:
        L = f['length']
        if L == 10:
            note = '← YYYY-MM-DD (ถูกต้อง)'
        elif L and L > 10:
            note = '⚠️ มีเวลาปนมาด้วย -> BETWEEN จะตัดวันสุดท้ายทิ้ง'
        else:
            note = '⚠️ รูปแบบผิด'
        print(f"      • ยาว {L} ตัวอักษร : {f['rows']:,} แถว  {note}")
    if rep['odd_date_values']:
        print("\n   ตัวอย่างค่าที่ผิดรูปแบบ:")
        for o in rep['odd_date_values']:
            print(f"      • '{o['value']}' : {o['rows']:,} แถว")

    outliers = rep.get('day_of_month_outliers') or []
    if outliers:
        med = rep.get('day_of_month_median', 0)
        print("\n   ⚠️ วันที่ในเดือนที่ยอดต่ำผิดปกติ (อาจเป็นสัญญาณวันที่เลื่อน):")
        for o in outliers:
            print(f"      • วันที่ {o['day']} ของเดือน : {o['records']:,} รายการ "
                  f"(ค่ากลาง {med:,})")
    else:
        print("\n   ✅ การกระจายยอดตามวันที่ในเดือนปกติ ไม่พบสัญญาณวันที่เลื่อน")

    _section("สรุป")
    if rep['issues']:
        print("   พบปัญหา:")
        for i in rep['issues']:
            print(f"      • {i}")
        print("\n   👉 ส่งผลนี้ให้ผมดู จะได้วางแผนแก้และคำนวณว่าต้อง backfill ช่วงไหนบ้าง")
    else:
        print("   ✅ ไม่พบความผิดปกติในข้อมูล")


# ============================================================
# CLI
# ============================================================

def _locate_project():
    """หาโฟลเดอร์โปรเจกต์ที่มี turso_handler.py เพื่อให้รันจากที่ไหนก็ได้"""
    candidates = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    cur = os.getcwd()
    for _ in range(4):
        cur = os.path.dirname(cur)
        if cur and cur != '/':
            candidates.append(cur)

    env_dir = os.environ.get('TECHTRADE_DIR', '').strip()
    if env_dir:
        candidates.insert(0, os.path.abspath(os.path.expanduser(env_dir)))

    seen = []
    for d in candidates:
        if not d or d in seen:
            continue
        seen.append(d)
        if os.path.exists(os.path.join(d, 'turso_handler.py')):
            sys.path.insert(0, d)
            return d

    print("❌ หา turso_handler.py ไม่เจอ\n")
    print("   สคริปต์นี้ต้องรันจากโฟลเดอร์โปรเจกต์ TechTrade")
    print("   (โฟลเดอร์ที่มีไฟล์ app.py, turso_handler.py อยู่)\n")
    print("   วิธีแก้:")
    print("      cd /path/to/TechTrade && python3 diagnose_turso.py\n")
    print("   หรือ:  TECHTRADE_DIR=/path/to/TechTrade python3 diagnose_turso.py\n")
    print(f"   (ที่ลองหาแล้ว: {', '.join(seen)})")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description='ตรวจข้อมูลใน Turso')
    ap.add_argument('--months', type=int, default=6, help='ย้อนหลังกี่เดือน (default 6)')
    ap.add_argument('--json', dest='json_out', default='', help='บันทึกผลเป็นไฟล์ JSON')
    ap.add_argument('--min-coverage', type=float, default=0.5,
                    help='ต่ำกว่ากี่เท่าของค่ากลางถือว่าน่าสงสัย (default 0.5)')
    args = ap.parse_args()

    project_dir = _locate_project()
    print(f"📂 โปรเจกต์: {project_dir}")

    env_path = os.path.join(project_dir, '.env')
    loaded_keys = _load_env_file(env_path)
    if loaded_keys:
        print(f"🔑 อ่าน .env แล้ว ({len(loaded_keys)} ค่า)")

    from turso_handler import TursoHandler

    turso = TursoHandler()
    if not (turso.url and turso.token):
        print("\n❌ ไม่พบ TURSO_DATABASE_URL / TURSO_AUTH_TOKEN")
        if not os.path.exists(env_path):
            print(f"\n   ไม่มีไฟล์ .env ในโฟลเดอร์นี้: {env_path}")
        else:
            missing = [k for k in ('TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN')
                       if not os.environ.get(k)]
            print(f"\n   มีไฟล์ .env อยู่ แต่ไม่มีค่าเหล่านี้: {', '.join(missing)}")
        print("\n   ทางที่ง่ายกว่า — เรียกผ่านเซิร์ฟเวอร์ที่มี credential อยู่แล้ว:")
        print("      https://report-trade.vercel.app/api/admin/diagnose-turso?months=6\n")
        print("   หรือส่งค่าตอนรัน:")
        print("      TURSO_DATABASE_URL='libsql://xxx.turso.io' \\")
        print("      TURSO_AUTH_TOKEN='xxx' \\")
        print("      python3 diagnose_turso.py --months 6\n")
        return 1

    today = date.today()
    start_d = add_months(month_start(today), -(args.months - 1))
    print(f"🔍 ตรวจข้อมูล Turso ช่วง {start_d} ถึง {today} ({args.months} เดือน)")

    rep = collect_report(turso, months=args.months, min_coverage=args.min_coverage)
    print_report(rep)
    turso.close()

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n💾 บันทึกรายงานแล้ว: {args.json_out}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
