"""
audit_zones.py — ตรวจสอบความครบถ้วนของสาขาใน Zone

ใช้หาสาเหตุที่ยอดเทรดใน Turso ไม่ตรงกับ techswop โดยตรวจ 4 เรื่อง:
  1. branch_id ใน zone ที่ resolve ไม่เจอในรายชื่อสาขาจริง (orphan)
  2. branch_id ที่ resolve ได้แต่ "คนละ ID scheme" (seq index ปนกับ real ID) -> ID drift
  3. สาขาที่มีอยู่จริงแต่ไม่ได้อยู่ใน zone ไหนเลย (สาขาหลุด)
  4. timeline จาก auto_export_log ว่ายอด record ของแต่ละ zone เริ่มตกวันไหน

การใช้งาน:
    python3 audit_zones.py                  # ใช้รายชื่อสาขาจาก DB (cached_branches)
    python3 audit_zones.py --refresh        # login Eve ดึงรายชื่อสาขาสดก่อนตรวจ (แนะนำ)
    python3 audit_zones.py --days 60        # ดู timeline ย้อนหลัง 60 วัน (ค่าเริ่มต้น 45)
    python3 audit_zones.py --json report.json   # บันทึกผลเป็นไฟล์ JSON

สคริปต์นี้เป็น read-only ทั้งหมด ยกเว้น --refresh ที่จะเขียน cached_branches ใหม่
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- helpers

def extract_real_id(branch_name):
    """ดึง real ID จากชื่อสาขา เช่น 249 จาก '00249 : ID249 : ...'"""
    if not branch_name:
        return None
    m = re.search(r'ID(\d+)', branch_name)
    if m:
        return m.group(1)
    m = re.search(r'FC[BP](\d+)', branch_name)
    if m:
        return m.group(1)
    return None


def build_index(branches):
    """สร้าง index สำหรับค้นหาสาขา"""
    by_branch_id = {}
    by_real_id = {}
    for b in branches or []:
        bid = str(b.get('branch_id', '')).strip()
        bname = str(b.get('branch_name', '') or '')
        if bid:
            by_branch_id[bid] = b
        rid = extract_real_id(bname)
        if rid:
            by_real_id.setdefault(rid, b)
    return by_branch_id, by_real_id


def load_legacy_branches():
    """โหลดรายชื่อสาขาชุดเก่าจากไฟล์ (ชุดที่ frontend fallback ไปใช้)"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'extracted_branches.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ อ่าน extracted_branches.json ไม่ได้: {e}")
        return []


def fetch_export_timeline(days):
    """ดึงยอด record ต่อ zone ต่อวัน จาก auto_export_log"""
    from app import get_db_connection
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT zone_name, date_exported, total_records, status, run_at
            FROM auto_export_log
            WHERE run_at >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY zone_name, date_exported
            """ % int(days)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ อ่าน auto_export_log ไม่ได้: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return {}

    timeline = defaultdict(list)
    for r in rows:
        d = dict(r)
        timeline[d.get('zone_name') or '(ไม่ระบุ zone)'].append({
            'date': str(d.get('date_exported') or ''),
            'records': int(d.get('total_records') or 0),
            'status': d.get('status') or '',
        })
    return dict(timeline)


def detect_drop(entries, drop_ratio=0.6):
    """หาวันที่ยอด record ตกฮวบเมื่อเทียบกับค่าเฉลี่ย 7 วันก่อนหน้า"""
    ok = [e for e in entries if e.get('status') == 'success']
    ok.sort(key=lambda e: e['date'])
    drops = []
    for i in range(7, len(ok)):
        window = [e['records'] for e in ok[i - 7:i]]
        baseline = sum(window) / len(window) if window else 0
        current = ok[i]['records']
        if baseline > 0 and current < baseline * drop_ratio:
            drops.append({
                'date': ok[i]['date'],
                'records': current,
                'baseline_avg': round(baseline, 1),
                'drop_pct': round((1 - current / baseline) * 100, 1),
            })
    return drops


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description='ตรวจสอบความครบถ้วนของสาขาใน Zone')
    parser.add_argument('--refresh', action='store_true',
                        help='login Eve แล้วดึงรายชื่อสาขาสดก่อนตรวจ')
    parser.add_argument('--days', type=int, default=45,
                        help='จำนวนวันย้อนหลังของ timeline (default 45)')
    parser.add_argument('--json', dest='json_out', default='',
                        help='บันทึกผลเป็นไฟล์ JSON')
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from app import (
        load_custom_zones_from_file,
        get_branches_from_db,
        get_eve_session,
        trigger_branch_update,
    )

    print("=" * 70)
    print("🔍 Zone Branch Audit")
    print("=" * 70)

    # --- 1. รายชื่อสาขาที่ใช้อ้างอิง ---
    if args.refresh:
        print("\n🔄 กำลัง login Eve เพื่อดึงรายชื่อสาขาล่าสุด...")
        session_id = get_eve_session(force_refresh=True)
        if session_id:
            ok, count = trigger_branch_update(session_id)
            print(f"   {'✅' if ok else '❌'} อัปเดตสาขา: {count} สาขา")
        else:
            print("   ❌ Login ไม่สำเร็จ — จะใช้ข้อมูลใน DB แทน")

    branches = get_branches_from_db()
    source = 'database (cached_branches)'
    if not branches:
        branches = load_legacy_branches()
        source = 'extracted_branches.json (fallback — ข้อมูลอาจเก่า!)'

    print(f"\n📋 รายชื่อสาขาอ้างอิง: {len(branches)} สาขา จาก {source}")
    if 'fallback' in source:
        print("   ⚠️ ไม่มีข้อมูลใน DB — ผลตรวจอาจไม่แม่นยำ ลองรันด้วย --refresh")

    by_branch_id, by_real_id = build_index(branches)

    legacy = load_legacy_branches()
    legacy_by_id, _ = build_index(legacy)
    print(f"📋 รายชื่อสาขาชุดเก่า (ที่ frontend fallback ไปใช้): {len(legacy)} สาขา")

    # --- 2. ตรวจแต่ละ zone ---
    zones = load_custom_zones_from_file()
    print(f"🗺️  Zone ทั้งหมด: {len(zones)}")

    report = {
        'branch_source': source,
        'total_branches': len(branches),
        'total_zones': len(zones),
        'zones': [],
        'unassigned_branches': [],
        'timeline': {},
    }

    assigned_real_ids = set()
    total_orphan = 0
    total_drift = 0

    for zone in zones:
        zone_name = zone.get('zone_name', '?')
        raw_ids = zone.get('branch_ids') or []
        if isinstance(raw_ids, str):
            try:
                raw_ids = json.loads(raw_ids)
            except Exception:
                raw_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]

        resolved, drifted, orphans, dupes = [], [], [], []
        seen = set()

        for bid in raw_ids:
            s = str(bid).strip()
            if s in seen:
                dupes.append(s)
                continue
            seen.add(s)

            hit = by_branch_id.get(s)
            if hit:
                rid = extract_real_id(hit.get('branch_name'))
                if rid:
                    assigned_real_ids.add(rid)
                # เช็ค ID drift: id เดียวกันในชุดเก่าชี้ไปคนละสาขา
                old = legacy_by_id.get(s)
                if old and old.get('branch_name') != hit.get('branch_name'):
                    drifted.append({
                        'branch_id': s,
                        'current_name': hit.get('branch_name'),
                        'legacy_name': old.get('branch_name'),
                    })
                else:
                    resolved.append({'branch_id': s, 'branch_name': hit.get('branch_name')})
                continue

            # ไม่เจอใน branch_id — ลองมองเป็น real ID
            hit2 = by_real_id.get(s.lstrip('0') or s)
            if hit2:
                rid = extract_real_id(hit2.get('branch_name'))
                if rid:
                    assigned_real_ids.add(rid)
                drifted.append({
                    'branch_id': s,
                    'current_name': hit2.get('branch_name'),
                    'legacy_name': None,
                    'note': 'เก็บเป็น real ID แทน branch_id (คนละ scheme)',
                })
                continue

            old = legacy_by_id.get(s)
            orphans.append({
                'branch_id': s,
                'legacy_name': old.get('branch_name') if old else None,
                'note': ('เคยมีในชุดเก่า แต่ไม่มีในรายชื่อปัจจุบัน'
                         if old else 'ไม่พบทั้งในชุดปัจจุบันและชุดเก่า'),
            })

        total_orphan += len(orphans)
        total_drift += len(drifted)

        report['zones'].append({
            'zone_id': zone.get('zone_id'),
            'zone_name': zone_name,
            'total_ids': len(raw_ids),
            'resolved': len(resolved),
            'drifted': drifted,
            'orphans': orphans,
            'duplicates': dupes,
        })

        status = '✅' if not orphans and not drifted and not dupes else '⚠️'
        print(f"\n{status} Zone: {zone_name}  ({len(raw_ids)} ids -> ok {len(resolved)})")
        if dupes:
            print(f"   🔁 ID ซ้ำ {len(dupes)} รายการ: {dupes[:10]}")
        for d in drifted:
            print(f"   🔀 ID {d['branch_id']} -> {d.get('current_name')}")
            if d.get('legacy_name'):
                print(f"      เดิมชี้ไป: {d['legacy_name']}")
            if d.get('note'):
                print(f"      {d['note']}")
        for o in orphans:
            print(f"   ❌ ID {o['branch_id']} หาไม่เจอ — {o['note']}")
            if o.get('legacy_name'):
                print(f"      ชื่อเดิม: {o['legacy_name']}")

    # --- 3. สาขาที่ไม่อยู่ใน zone ไหนเลย ---
    unassigned = []
    for b in branches:
        rid = extract_real_id(b.get('branch_name'))
        if rid and rid not in assigned_real_ids:
            unassigned.append({
                'branch_id': str(b.get('branch_id')),
                'branch_name': b.get('branch_name'),
            })
    report['unassigned_branches'] = unassigned

    print("\n" + "-" * 70)
    print(f"🏪 สาขาที่ไม่อยู่ใน zone ไหนเลย: {len(unassigned)} สาขา")
    for b in unassigned[:40]:
        print(f"   • {b['branch_id']} : {b['branch_name']}")
    if len(unassigned) > 40:
        print(f"   ... และอีก {len(unassigned) - 40} สาขา (ดูใน --json)")

    # --- 4. timeline ---
    print("\n" + "-" * 70)
    print(f"📉 ตรวจ timeline ย้อนหลัง {args.days} วัน (auto_export_log)")
    timeline = fetch_export_timeline(args.days)
    for zone_name, entries in timeline.items():
        drops = detect_drop(entries)
        report['timeline'][zone_name] = {
            'points': entries,
            'drops': drops,
        }
        if drops:
            print(f"\n   ⚠️ {zone_name} — ยอดตกผิดปกติ {len(drops)} วัน:")
            for d in drops[:10]:
                print(f"      {d['date']}: {d['records']:,} records "
                      f"(ค่าเฉลี่ย 7 วันก่อน {d['baseline_avg']:,} = ลดลง {d['drop_pct']}%)")
        else:
            print(f"   ✅ {zone_name} — ยอดต่อวันคงที่")
    if not timeline:
        print("   (ไม่มีข้อมูลใน auto_export_log)")

    # --- สรุป ---
    print("\n" + "=" * 70)
    print("📊 สรุป")
    print(f"   ID ที่ resolve ไม่ได้ (orphan): {total_orphan}")
    print(f"   ID ที่ scheme ไม่ตรง (drift):  {total_drift}")
    print(f"   สาขาที่ยังไม่อยู่ zone ไหน:     {len(unassigned)}")
    if total_orphan or total_drift:
        print("\n   👉 ID เหล่านี้คือสาเหตุที่ดึงข้อมูลเข้า Turso ไม่ครบ")
        print("      แก้ zone ให้ถูกต้องแล้วรัน backfill ย้อนหลังตามช่วงวันที่ที่ยอดตก")
    elif unassigned:
        print("\n   👉 zone ทุกอันใช้ ID ถูกต้อง แต่ยังมีสาขาที่ไม่ได้ถูกเก็บเข้า zone ไหนเลย")
    else:
        print("\n   ✅ ไม่พบความผิดปกติของสาขาใน zone")
    print("=" * 70)

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 บันทึกรายงานแล้ว: {args.json_out}")


if __name__ == '__main__':
    main()
