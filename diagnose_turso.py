"""
diagnose_turso.py — ตรวจข้อมูลจริงใน Turso หาว่ายอดหายไปตรงไหนและเท่าไร

ตรวจ 6 เรื่อง (อ่านอย่างเดียว ไม่แก้ไขอะไรทั้งสิ้น):

  1. ภาพรวมฐานข้อมูล — จำนวนแถว ช่วงวันที่ สาขา zone
  2. วันที่ไม่มีข้อมูลเลยสักแถว = วันที่ไม่เคย sync สำเร็จ (หลักฐานตรงที่สุด)
  3. ความครบรายสาขา×เดือน — เทียบกับค่ากลางของสาขาอื่นในเดือนเดียวกัน
  4. sync_history ที่ใช้คีย์ช่วงวันที่ — ตัวที่ทำให้ระบบเชื่อผิดว่า "ครบแล้ว"
  5. real_branch_id ผิดปกติ — แถวที่ query ด้วย real_branch_id หาไม่เจอ
  6. รูปแบบ document_date — เช็คว่ามี timezone เพี้ยนหรือมีเวลาปนไหม

การใช้งาน:
    python3 diagnose_turso.py                    # ย้อนหลัง 6 เดือน
    python3 diagnose_turso.py --months 12        # ย้อนหลัง 12 เดือน
    python3 diagnose_turso.py --json report.json # บันทึกผลเป็นไฟล์

ต้องมี .env ที่มี TURSO_DATABASE_URL และ TURSO_AUTH_TOKEN
(ถ้ามี POSTGRES_URL_NON_POOLING ด้วยจะเทียบกับรายชื่อสาขาใน zone ให้)
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


def days_in_month(y, m):
    return (add_months(date(y, m, 1), 1) - timedelta(days=1)).day


def rows(res):
    """แปลงผล query เป็น list ของ tuple"""
    if not res:
        return []
    return [tuple(r) for r in res.rows]


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser(description='ตรวจข้อมูลใน Turso')
    ap.add_argument('--months', type=int, default=6, help='ย้อนหลังกี่เดือน (default 6)')
    ap.add_argument('--json', dest='json_out', default='', help='บันทึกผลเป็นไฟล์ JSON')
    ap.add_argument('--min-coverage', type=float, default=0.5,
                    help='ต่ำกว่ากี่เท่าของค่ากลางถือว่าน่าสงสัย (default 0.5)')
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from turso_handler import TursoHandler

    turso = TursoHandler()
    if not (turso.url and turso.token):
        print("❌ ไม่พบ TURSO_DATABASE_URL / TURSO_AUTH_TOKEN ใน environment")
        return 1

    today = date.today()
    start_d = add_months(month_start(today), -(args.months - 1))
    iso_start = start_d.strftime('%Y-%m-%d')
    iso_end = today.strftime('%Y-%m-%d')

    report = {'range': [iso_start, iso_end]}

    print(f"🔍 ตรวจข้อมูล Turso ช่วง {iso_start} ถึง {iso_end} ({args.months} เดือน)")

    # ---------------- 1. ภาพรวม ----------------
    section("1. ภาพรวมฐานข้อมูล")

    res = turso._execute_sql(
        "SELECT COUNT(*), MIN(document_date), MAX(document_date), "
        "COUNT(DISTINCT real_branch_id), COUNT(DISTINCT zone_name) FROM trades")
    r = rows(res)
    if not r:
        print("❌ อ่านข้อมูลจาก Turso ไม่ได้ — ตรวจ URL/TOKEN")
        return 1
    total, dmin, dmax, nbranch, nzone = r[0]
    print(f"   แถวทั้งหมด      : {int(total):,}")
    print(f"   ช่วงวันที่       : {dmin} ถึง {dmax}")
    print(f"   จำนวนสาขา       : {nbranch}")
    print(f"   จำนวน zone      : {nzone}")
    report['overview'] = {'total_rows': int(total), 'min_date': dmin,
                          'max_date': dmax, 'branches': int(nbranch),
                          'zones': int(nzone)}

    # ---------------- 2. วันที่ไม่มีข้อมูลเลย ----------------
    section("2. วันที่ไม่มีข้อมูลเลยสักแถว (= ไม่เคย sync สำเร็จ)")

    res = turso._execute_sql(
        "SELECT document_date, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? GROUP BY document_date",
        [iso_start, iso_end])
    per_day = {str(d): int(c) for d, c in rows(res)}

    missing_days = []
    weak_days = []
    counts = sorted(per_day.values())
    median_day = counts[len(counts) // 2] if counts else 0

    d = start_d
    while d <= today:
        key = d.strftime('%Y-%m-%d')
        c = per_day.get(key, 0)
        if c == 0:
            missing_days.append(key)
        elif median_day and c < median_day * 0.2:
            weak_days.append((key, c))
        d += timedelta(days=1)

    print(f"   ค่ากลางรายวัน   : {median_day:,} รายการ/วัน")
    print(f"   วันที่ไม่มีข้อมูล : {len(missing_days)} วัน")
    for k in missing_days[:40]:
        wd = ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'][datetime.strptime(k, '%Y-%m-%d').weekday()]
        print(f"      • {k} ({wd})")
    if len(missing_days) > 40:
        print(f"      ... และอีก {len(missing_days) - 40} วัน")

    if weak_days:
        print(f"\n   วันที่ข้อมูลน้อยผิดปกติ (< 20% ของค่ากลาง): {len(weak_days)} วัน")
        for k, c in weak_days[:20]:
            print(f"      • {k}: {c:,} รายการ")

    report['missing_days'] = missing_days
    report['weak_days'] = weak_days
    report['median_per_day'] = median_day

    # ---------------- 3. ความครบรายสาขา×เดือน ----------------
    section("3. ความครบของข้อมูล รายสาขา × เดือน")

    res = turso._execute_sql(
        "SELECT real_branch_id, substr(document_date,1,7) AS ym, "
        "COUNT(DISTINCT document_date), COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? "
        "GROUP BY real_branch_id, ym", [iso_start, iso_end])

    by_month = defaultdict(dict)     # {ym: {branch: (days, records)}}
    for bid, ym, days, recs in rows(res):
        by_month[str(ym)][str(bid)] = (int(days), int(recs))

    suspicious = []
    for ym in sorted(by_month):
        entry = by_month[ym]
        day_counts = sorted(v[0] for v in entry.values())
        if not day_counts:
            continue
        median_days = day_counts[len(day_counts) // 2]
        y, m = int(ym[:4]), int(ym[5:7])
        cal_days = days_in_month(y, m)
        if (y, m) == (today.year, today.month):
            cal_days = today.day

        print(f"\n   📅 {ym}  (มี {cal_days} วันในเดือน, สาขาส่วนใหญ่มีข้อมูล {median_days} วัน)")
        bad = [(b, v) for b, v in entry.items()
               if median_days and v[0] < median_days * args.min_coverage]
        if bad:
            for b, (dd, rr) in sorted(bad, key=lambda x: x[1][0]):
                pct = dd / median_days * 100 if median_days else 0
                print(f"      ⚠️ สาขา {b:>6}: มีข้อมูล {dd:>2}/{median_days} วัน "
                      f"({pct:.0f}% ของค่ากลาง), {rr:,} รายการ")
                suspicious.append({'month': ym, 'branch_id': b, 'days': dd,
                                   'median_days': median_days, 'records': rr})
        else:
            print(f"      ✅ ทุกสาขาข้อมูลใกล้เคียงกัน ({len(entry)} สาขา)")

    report['suspicious_branch_months'] = suspicious

    # ---------------- 4. sync_history คีย์ช่วงวันที่ ----------------
    section("4. sync_history ที่ใช้คีย์ช่วงวันที่ (ตัวที่ทำให้เชื่อผิดว่าครบ)")

    res = turso._execute_sql("SELECT COUNT(*) FROM sync_history")
    sh_total = int(rows(res)[0][0]) if rows(res) else 0

    res = turso._execute_sql(
        "SELECT branch_id, sync_date, record_count, synced_at FROM sync_history "
        "WHERE sync_date LIKE '%/%' ORDER BY synced_at DESC")
    range_rows = rows(res)

    print(f"   แถวทั้งหมดใน sync_history : {sh_total:,}")
    print(f"   แถวที่คีย์เป็นช่วงวันที่     : {len(range_rows):,}")
    if range_rows:
        print("\n   ทุกแถวข้างล่างนี้คือการประทับตรา 'sync ครบแล้ว' ที่เชื่อถือไม่ได้")
        print("   ระบบจะใช้แถวเหล่านี้ตอบทันทีโดยไม่ไปถาม Eve อีก\n")
        for bid, sd, cnt, at in range_rows[:30]:
            print(f"      • สาขา {str(bid):>6} | ช่วง {sd} | อ้างว่ามี {cnt} รายการ | {at}")
        if len(range_rows) > 30:
            print(f"      ... และอีก {len(range_rows) - 30} แถว")
    else:
        print("   ✅ ไม่พบแถวที่ใช้คีย์ช่วงวันที่")

    report['sync_history_total'] = sh_total
    report['sync_history_range_keys'] = [
        {'branch_id': str(b), 'sync_date': str(s), 'record_count': c, 'synced_at': str(a)}
        for b, s, c, a in range_rows]

    # ---------------- 5. real_branch_id ผิดปกติ ----------------
    section("5. real_branch_id ที่ผิดปกติ (แถวที่รายงานมองไม่เห็น)")

    res = turso._execute_sql(
        "SELECT real_branch_id, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? "
        "GROUP BY real_branch_id ORDER BY COUNT(*) DESC", [iso_start, iso_end])
    branch_rows = rows(res)

    weird = []
    for bid, cnt in branch_rows:
        s = str(bid).strip() if bid is not None else ''
        if not s or not s.isdigit():
            weird.append((s or '(ว่าง)', int(cnt)))

    if weird:
        print("   ⚠️ พบแถวที่ real_branch_id ไม่ใช่ตัวเลข")
        print("      รายงานกรองด้วย `real_branch_id IN (...)` ที่ส่งแต่ตัวเลข")
        print("      แถวเหล่านี้จึงไม่ถูกนับในยอดเลย\n")
        for s, c in weird:
            print(f"      • '{s}' : {c:,} รายการ")
    else:
        print(f"   ✅ real_branch_id เป็นตัวเลขทั้งหมด ({len(branch_rows)} สาขา)")

    report['weird_branch_ids'] = weird

    # เทียบกับสาขาใน zone
    try:
        from app import load_custom_zones_from_file, find_branch_by_sequential_id
        import re
        zones = load_custom_zones_from_file()
        if zones:
            in_db = {str(b[0]) for b in branch_rows}
            print()
            for z in zones:
                expected = set()
                for bid in (z.get('branch_ids') or []):
                    info = find_branch_by_sequential_id(bid)
                    if info:
                        mm = re.search(r'ID(\d+)', info.get('branch_name', ''))
                        expected.add(mm.group(1) if mm else str(bid))
                    else:
                        expected.add(str(bid))
                never = sorted(expected - in_db)
                print(f"   🗺️ Zone {z['zone_name']}: {len(expected)} สาขาใน zone, "
                      f"{len(expected) - len(never)} สาขามีข้อมูลใน Turso")
                if never:
                    print(f"      ❌ ไม่มีข้อมูลเลยสักแถว {len(never)} สาขา: {never[:20]}")
                    report.setdefault('branches_never_synced', []).extend(never)
    except Exception as e:
        print(f"   (ข้ามการเทียบกับ zone: {e})")

    # ---------------- 6. รูปแบบ document_date ----------------
    section("6. รูปแบบ document_date")

    res = turso._execute_sql(
        "SELECT LENGTH(document_date) AS L, COUNT(*) FROM trades GROUP BY L ORDER BY COUNT(*) DESC")
    len_rows = rows(res)
    print("   ความยาวของค่า document_date:")
    for L, c in len_rows:
        note = ''
        if L == 10:
            note = '← YYYY-MM-DD (ถูกต้อง)'
        elif L and int(L) > 10:
            note = '⚠️ มีเวลาปนมาด้วย -> BETWEEN จะตัดวันสุดท้ายทิ้ง'
        else:
            note = '⚠️ รูปแบบผิด'
        print(f"      • ยาว {L} ตัวอักษร : {int(c):,} แถว  {note}")

    res = turso._execute_sql(
        "SELECT document_date, COUNT(*) FROM trades WHERE LENGTH(document_date) != 10 "
        "GROUP BY document_date LIMIT 10")
    odd = rows(res)
    if odd:
        print("\n   ตัวอย่างค่าที่ผิดรูปแบบ:")
        for v, c in odd:
            print(f"      • '{v}' : {int(c):,} แถว")

    report['date_formats'] = [{'length': int(L) if L else None, 'rows': int(c)}
                              for L, c in len_rows]

    # เช็คสัญญาณ timezone เพี้ยน: เทียบยอดวันแรก/วันสุดท้ายของเดือน
    res = turso._execute_sql(
        "SELECT substr(document_date,9,2) AS dd, COUNT(*) FROM trades "
        "WHERE document_date BETWEEN ? AND ? GROUP BY dd ORDER BY dd",
        [iso_start, iso_end])
    dom = {str(d): int(c) for d, c in rows(res)}
    if dom:
        vals = sorted(dom.values())
        med = vals[len(vals) // 2]
        odd_dom = [(k, v) for k, v in sorted(dom.items()) if med and v < med * 0.4]
        if odd_dom:
            print("\n   ⚠️ วันที่ในเดือนที่ยอดต่ำผิดปกติ (อาจเป็นสัญญาณวันที่เลื่อน):")
            for k, v in odd_dom:
                print(f"      • วันที่ {k} ของเดือน : {v:,} รายการ (ค่ากลาง {med:,})")
        else:
            print("\n   ✅ การกระจายยอดตามวันที่ในเดือนปกติ ไม่พบสัญญาณวันที่เลื่อน")

    # ---------------- สรุป ----------------
    section("สรุป")
    issues = []
    if missing_days:
        issues.append(f"{len(missing_days)} วันไม่มีข้อมูลเลย")
    if suspicious:
        issues.append(f"{len(suspicious)} คู่ (สาขา×เดือน) ข้อมูลน้อยผิดปกติ")
    if range_rows:
        issues.append(f"{len(range_rows)} แถว sync_history ที่ประทับตราผิด")
    if weird:
        issues.append(f"{sum(c for _, c in weird):,} แถวที่ real_branch_id ผิดรูปแบบ")
    if report.get('branches_never_synced'):
        issues.append(f"{len(report['branches_never_synced'])} สาขาไม่มีข้อมูลเลย")

    if issues:
        print("   พบปัญหา:")
        for i in issues:
            print(f"      • {i}")
        print("\n   👉 ส่งผลนี้ให้ผมดู จะได้วางแผนแก้และคำนวณว่าต้อง backfill ช่วงไหนบ้าง")
    else:
        print("   ✅ ไม่พบความผิดปกติในข้อมูล")

    turso.close()

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n💾 บันทึกรายงานแล้ว: {args.json_out}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
