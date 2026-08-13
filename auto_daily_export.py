# Auto Daily Turso Sync Engine
# ระบบ Sync ข้อมูล trade รายวันอัตโนมัติเข้าสู่ Turso Database (ยกเลิก Google Drive ถาวร)

import json
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from turso_handler import TursoHandler


def get_auto_export_config():
    """ดึง config auto-sync จาก DB"""
    try:
        from app import get_db_connection
        conn = get_db_connection()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT * FROM auto_export_config ORDER BY id LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return dict(row)
        return None
    except Exception as e:
        print(f"❌ Error getting config: {e}")
        return None


def save_auto_sync_log(log_data):
    """บันทึก log การ sync ข้อมูลเข้า Turso"""
    try:
        from app import get_db_connection
        conn = get_db_connection()
        if not conn:
            return
        cur = conn.cursor()
        # ใช้ตารางเดิม แต่เปลี่ยนความหมายของฟิลด์บางส่วน
        cur.execute("""
            INSERT INTO auto_export_log 
            (zone_id, zone_name, date_exported, total_records, status, error_message, duration_seconds)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            log_data.get('zone_id', ''),
            log_data.get('zone_name', ''),
            log_data.get('date_sync', ''),
            log_data.get('total_records', 0),
            log_data.get('status', 'success'),
            log_data.get('error_message', ''),
            log_data.get('duration_seconds', 0)
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error saving sync log: {e}")


# ==========================================
# sync_progress — สถานะ sync ราย zone ต่อวัน
# ------------------------------------------
# Vercel ฆ่า function ที่ 300 วินาที ถ้า sync ทั้งวันไม่จบใน request เดียว
# จะโดนตัดกลางคัน เดิมไม่มีที่จำว่าทำถึงไหน ทำให้
#   - ping ถัดไปเริ่มใหม่ทั้งหมด แล้วโดนตัดอีก วนไม่จบทั้งวัน
#   - หรือถ้า zone แรกๆ เสร็จ guard เดิม (ดู log status='success' ล่าสุด)
#     จะติดแล้วข้ามทั้งวัน -> zone ที่เหลือไม่มีข้อมูลเลย
# ตารางนี้แก้ทั้งสองเคส
# ==========================================

# สถานะที่ถือว่า "ไม่ต้องทำ zone นี้ซ้ำแล้ว"
SYNC_DONE_STATUSES = ('done', 'done_warning', 'failed_final')
MAX_ZONE_ATTEMPTS = 3


def _sync_time_budget():
    """งบเวลาต่อ 1 request (วินาที) — Vercel maxDuration 300s เผื่อไว้ 240s"""
    override = os.environ.get('SYNC_TIME_BUDGET', '').strip()
    if override.isdigit():
        return int(override)
    return 240 if os.environ.get('VERCEL') else 3000


def get_sync_progress(sync_date):
    """ดึงสถานะ sync ของวันที่ระบุ -> {zone_id: {...}}"""
    try:
        from app import get_db_connection
        conn = get_db_connection()
        if not conn:
            return {}
        cur = conn.cursor()
        cur.execute("""
            SELECT zone_id, zone_name, status, records, attempts, last_error
            FROM sync_progress WHERE sync_date = %s
        """, (sync_date,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {str(dict(r)['zone_id']): dict(r) for r in rows}
    except Exception as e:
        print(f"⚠️ get_sync_progress error: {e}")
        return {}


def save_sync_progress(sync_date, zone_id, zone_name, status, records=0,
                       attempts=1, last_error=''):
    """บันทึกสถานะ sync ของ zone (upsert)"""
    try:
        from app import get_db_connection
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sync_progress
            (sync_date, zone_id, zone_name, status, records, attempts, last_error, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (sync_date, zone_id)
            DO UPDATE SET
                zone_name = EXCLUDED.zone_name,
                status = EXCLUDED.status,
                records = EXCLUDED.records,
                attempts = sync_progress.attempts + 1,
                last_error = EXCLUDED.last_error,
                updated_at = CURRENT_TIMESTAMP
        """, (sync_date, str(zone_id), zone_name, status, records,
              attempts, (last_error or '')[:1000]))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ save_sync_progress error: {e}")
        return False


def clear_sync_progress(sync_date):
    """ล้างสถานะ sync ของวันนั้น เพื่อบังคับให้ sync ใหม่ทุก zone

    ใช้ตอน backfill ที่ต้องการเขียนทับข้อมูลเดิมทั้งวัน
    (ถ้าไม่ล้าง resume จะข้าม zone ที่ daily sync ทำไปแล้ว)
    """
    try:
        from app import get_db_connection
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("DELETE FROM sync_progress WHERE sync_date = %s", (sync_date,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"🗑️ ล้างสถานะ sync ของ {sync_date} เพื่อ re-sync ใหม่ทั้งวัน")
        return True
    except Exception as e:
        print(f"⚠️ clear_sync_progress error: {e}")
        return False


def is_sync_complete(sync_date, zones=None):
    """เช็คว่า sync ของวันนั้นครบทุก zone แล้วหรือยัง

    ใช้แทน guard เดิมที่ดู auto_export_log แถวล่าสุดที่ status='success'
    Returns: (complete: bool, done: int, total: int, pending_zone_names: list)
    """
    try:
        from app import load_custom_zones_from_file, get_db_connection

        if zones is None:
            config = get_auto_export_config() or {}
            zone_ids_config = config.get('zone_ids', [])
            if isinstance(zone_ids_config, str):
                try:
                    zone_ids_config = json.loads(zone_ids_config)
                except Exception:
                    zone_ids_config = []
            all_zones = load_custom_zones_from_file()
            zones = ([z for z in all_zones if z['zone_id'] in zone_ids_config]
                     if zone_ids_config else all_zones)

        if not zones:
            return False, 0, 0, []

        progress = get_sync_progress(sync_date)
        pending = [z['zone_name'] for z in zones
                   if progress.get(str(z['zone_id']), {}).get('status') not in SYNC_DONE_STATUSES]
        done = len(zones) - len(pending)
        return len(pending) == 0, done, len(zones), pending
    except Exception as e:
        print(f"⚠️ is_sync_complete error: {e}")
        return False, 0, 0, []


def _extract_real_id(branch_name):
    """ดึง real ID จากชื่อสาขา เช่น 249 จาก '00249 : ID249 : ...'"""
    import re
    if not branch_name:
        return None
    m = re.search(r'ID(\d+)', branch_name)
    if m:
        return m.group(1)
    m = re.search(r'FC[BP](\d+)', branch_name)
    if m:
        return m.group(1)
    return None


def verify_zone_branches(zone, reference_branches=None):
    """ตรวจว่า branch_id ทุกตัวใน zone ยัง resolve เจอในรายชื่อสาขาจริงหรือไม่

    ถ้า resolve ไม่เจอ = สาขานั้นจะถูกดึงข้อมูลไม่ได้ และหายจากยอดแบบเงียบๆ
    ซึ่งเป็นสาเหตุที่ยอดใน Turso ไม่ตรงกับ techswop

    Returns:
        dict: {'total', 'resolved', 'unresolved': [{'branch_id', 'reason'}], 'real_ids': set}
    """
    from app import get_branches_from_db, find_branch_by_sequential_id

    branch_ids = zone.get('branch_ids') or []
    if isinstance(branch_ids, str):
        try:
            branch_ids = json.loads(branch_ids)
        except Exception:
            branch_ids = [x.strip() for x in branch_ids.split(',') if x.strip()]

    if reference_branches is None:
        reference_branches = get_branches_from_db()

    by_id = {str(b.get('branch_id', '')).strip(): b for b in (reference_branches or [])}

    unresolved = []
    resolved = 0
    real_ids = set()

    for bid in branch_ids:
        s = str(bid).strip()
        hit = by_id.get(s)
        if not hit:
            # เผื่อ DB ว่าง ให้ลอง fallback ผ่าน cache ของ app
            try:
                hit = find_branch_by_sequential_id(s)
            except Exception:
                hit = None
        if hit:
            resolved += 1
            rid = _extract_real_id(hit.get('branch_name'))
            if rid:
                real_ids.add(rid)
        else:
            unresolved.append({
                'branch_id': s,
                'reason': 'ไม่พบ branch_id นี้ในรายชื่อสาขาปัจจุบัน'
            })

    return {
        'total': len(branch_ids),
        'resolved': resolved,
        'unresolved': unresolved,
        'real_ids': real_ids,
    }


def find_unassigned_branches(zones, reference_branches=None):
    """หาสาขาที่มีอยู่จริงแต่ไม่ได้อยู่ใน zone ไหนเลย (= ยอดสาขานี้จะไม่เคยถูก sync)"""
    from app import get_branches_from_db

    if reference_branches is None:
        reference_branches = get_branches_from_db()
    if not reference_branches:
        return []

    assigned = set()
    for z in zones or []:
        assigned |= verify_zone_branches(z, reference_branches)['real_ids']

    unassigned = []
    for b in reference_branches:
        rid = _extract_real_id(b.get('branch_name'))
        if rid and rid not in assigned:
            unassigned.append({
                'branch_id': str(b.get('branch_id')),
                'branch_name': b.get('branch_name'),
            })
    return unassigned


def fetch_zone_daily_data(zone, target_date):
    """ดึงข้อมูลของโซนเฉพาะวันที่ระบุจาก API ของ Eve (แบบ Parallel)"""
    from app import fetch_all_for_branch
    
    date_str = target_date.strftime("%d/%m/%Y")
    branch_ids = zone.get('branch_ids', [])
    all_items = []
    
    print(f"📊 Fetching data for Zone '{zone['zone_name']}' on {date_str} (Parallel)")
    
    all_success = True
    
    def fetch_single_branch(branch_id):
        try:
            filters = {
                'date_start': date_str,
                'date_end': date_str,
                'sale_code': '',
                'customer_sign': '',
                'branch_id': branch_id
            }
            items = fetch_all_for_branch(filters)
            for item in items:
                item['_branch_id'] = branch_id
            return items, True
        except Exception as e:
            print(f"   ❌ Branch {branch_id} error: {e}")
            return [], False

    # ใช้ ThreadPoolExecutor ดึงข้อมูลสาขาพร้อมกัน (Max 15 workers)
    max_workers = min(15, len(branch_ids)) if branch_ids else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_branch = {executor.submit(fetch_single_branch, bid): bid for bid in branch_ids}
        for future in as_completed(future_to_branch):
            items, success = future.result()
            if not success:
                all_success = False
            all_items.extend(items)
    
    return all_items, all_success


def run_daily_export(force=False, target_dt=None, time_budget=None, resume=True):
    """ฟังก์ชันหลัก: Sync ข้อมูลรายวันเข้า Turso Database (ทำต่อได้)

    รันเท่าที่ทันใน time budget แล้วบันทึกว่า zone ไหนเสร็จแล้วลง sync_progress
    การเรียกครั้งถัดไปจะข้าม zone ที่ทำแล้วและทำต่อจากที่ค้าง จึงไม่โดน
    Vercel ตัดกลางคันแล้วต้องเริ่มใหม่

    Args:
        force: True = บังคับรัน (ไม่ตรวจสอบว่า auto-sync เปิดอยู่ไหม)
        target_dt: วันที่ต้องการรัน (ถ้าไม่ระบุจะรันเมื่อวาน)
        time_budget: งบเวลาต่อการเรียก 1 ครั้ง (วินาที) ไม่ระบุ = อัตโนมัติ
        resume: True = ข้าม zone ที่ทำเสร็จแล้วของวันนั้น
                False = ทำใหม่ทุก zone (ใช้ตอน backfill ที่ต้องการเขียนทับ)
    Returns:
        dict: ผลการรัน — มี 'completed' บอกว่าครบทุก zone แล้วหรือยัง
    """
    import pytz
    
    print("\n" + "=" * 60)
    print(f"🗄️ Auto Turso Sync Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    start_time = time.time()
    
    # 1. ดึง config
    config = get_auto_export_config()
    if not config:
        print("⚠️ No auto-sync config found")
        return {'success': False, 'message': 'ไม่พบ config กรุณาตั้งค่าก่อน'}
    
    if not force and not config.get('enabled'):
        print("⚠️ Auto-sync is disabled")
        return {'success': False, 'message': 'ระบบ auto-sync ปิดอยู่'}
    
    # 2. Initialize Turso handler
    turso_url = os.getenv('TURSO_DATABASE_URL')
    turso_token = os.getenv('TURSO_AUTH_TOKEN')
    
    if not turso_url or not turso_token:
        print("❌ Turso credentials not found in environment")
        return {'success': False, 'message': 'กรุณาตั้งค่า Turso URL และ Token ใน environment'}
        
    turso = TursoHandler(turso_url, turso_token)
    if not turso.init_db():
        print("❌ Turso initialization failed")
        return {'success': False, 'message': 'เชื่อมต่อ Turso Database ไม่สำเร็จ'}
    
    print("✅ Turso Database connected and ready")
    
    # 3. กำหนดวันที่ที่จะ sync (วันก่อนหน้า)
    bkk_tz = pytz.timezone('Asia/Bangkok')
    now_bkk = datetime.now(bkk_tz)
    
    if target_dt is None:
        target_date = (now_bkk - timedelta(days=1)).date()
        target_date_dt = datetime.combine(target_date, datetime.min.time())
    else:
        target_date_dt = target_dt
        target_date = target_dt.date() if isinstance(target_dt, datetime) else target_dt
    
    date_str_display = target_date.strftime("%d/%m/%Y")
    print(f"📅 Sync date: {date_str_display}")
    
    # 4. ดึง Zone list
    from app import load_custom_zones_from_file
    
    zone_ids_config = config.get('zone_ids', [])
    if isinstance(zone_ids_config, str):
        try:
            zone_ids_config = json.loads(zone_ids_config)
        except:
            zone_ids_config = []
    
    all_zones = load_custom_zones_from_file()
    
    if zone_ids_config:
        zones_to_sync = [z for z in all_zones if z['zone_id'] in zone_ids_config]
    else:
        zones_to_sync = all_zones
    
    if not zones_to_sync:
        print("⚠️ No zones to sync")
        return {'success': False, 'completed': False, 'message': 'ไม่มี zone ที่ต้องการ sync'}

    all_zone_count = len(zones_to_sync)
    all_zones_for_check = list(zones_to_sync)   # เก็บรายการเต็มไว้เช็คความครบตอนจบ

    # 4.2 ข้าม zone ที่ทำเสร็จแล้วของวันนี้ (resume)
    progress_map = get_sync_progress(target_date) if resume else {}
    skipped_done = 0
    if resume and progress_map:
        pending_zones = []
        for z in zones_to_sync:
            st = progress_map.get(str(z['zone_id']), {})
            if st.get('status') in SYNC_DONE_STATUSES:
                skipped_done += 1
            else:
                pending_zones.append(z)
        zones_to_sync = pending_zones
        if skipped_done:
            print(f"⏭️ ข้าม {skipped_done} zone ที่ sync วันนี้ไปแล้ว")

    if not zones_to_sync:
        print(f"✅ Zone ทั้งหมด ({all_zone_count}) sync ครบแล้วสำหรับ {date_str_display}")
        turso.close()
        return {
            'success': True, 'completed': True, 'sync_completed': True,
            'data_consistent': True,
            'total_zones': all_zone_count, 'total_synced': 0,
            'zones_skipped_done': skipped_done, 'zones_remaining': 0,
            'total_records': 0, 'total_errors': 0, 'total_warnings': 0,
            'warnings': [], 'results': [], 'duration': '0.0s',
            'message': 'sync ของวันนี้ครบทุก zone แล้ว',
        }

    budget = time_budget if time_budget is not None else _sync_time_budget()
    print(f"📋 Zones to sync: {len(zones_to_sync)}/{all_zone_count} (budget {budget}s)")

    # 4.5 ตรวจความครบถ้วนของสาขาใน zone ก่อนเริ่ม sync
    # จุดนี้คือกันปัญหา "สาขาหลุดจาก zone แล้วยอดหายเงียบๆ"
    reference_branches = []
    branch_audit = {'zones': {}, 'unassigned': []}
    try:
        from app import get_branches_from_db
        reference_branches = get_branches_from_db()
        if reference_branches:
            branch_audit['unassigned'] = find_unassigned_branches(zones_to_sync, reference_branches)
            if branch_audit['unassigned']:
                print(f"⚠️ [Branch Audit] พบ {len(branch_audit['unassigned'])} สาขาที่ไม่อยู่ใน zone ไหนเลย:")
                for b in branch_audit['unassigned'][:15]:
                    print(f"      • {b['branch_id']} : {b['branch_name']}")
                if len(branch_audit['unassigned']) > 15:
                    print(f"      ... และอีก {len(branch_audit['unassigned']) - 15} สาขา")
        else:
            print("⚠️ [Branch Audit] ไม่มีรายชื่อสาขาใน DB — ข้ามการตรวจสอบ")
    except Exception as audit_err:
        print(f"⚠️ [Branch Audit] ตรวจสอบไม่สำเร็จ: {audit_err}")

    # 5. Sync แต่ละ Zone
    results = []
    total_records = 0
    total_synced_zones = 0
    total_errors = 0
    total_warnings = 0
    warnings = []
    
    zone_durations = []
    stopped_early = False

    for zone_idx, zone in enumerate(zones_to_sync):
        zone_name = zone['zone_name']
        zone_id = zone['zone_id']
        zone_start = time.time()

        # เช็คงบเวลา "ก่อน" เริ่ม zone — ไม่เริ่ม zone ที่คาดว่าจะทำไม่ทัน
        # เพราะถ้าโดนตัดกลางคันหลัง delete ข้อมูล zone นั้นจะเหลือศูนย์
        elapsed_so_far = time.time() - start_time
        avg_zone = (sum(zone_durations) / len(zone_durations)) if zone_durations else 0
        if zone_durations and (elapsed_so_far + avg_zone) > budget:
            stopped_early = True
            remaining = len(zones_to_sync) - zone_idx
            print(f"\n⏸️ หยุดที่ zone ที่ {zone_idx + 1} "
                  f"(ใช้ไป {elapsed_so_far:.0f}s/{budget}s) — เหลืออีก {remaining} zone")
            print(f"   การเรียกครั้งถัดไปจะทำต่อจาก '{zone_name}' โดยอัตโนมัติ")
            break

        print(f"\n📦 [{zone_idx+1}/{len(zones_to_sync)}] Syncing Zone: {zone_name}")

        try:
            # 0. ตรวจว่า branch_id ทุกตัวใน zone ยังใช้ได้จริง
            zone_branch_check = {'total': 0, 'resolved': 0, 'unresolved': []}
            if reference_branches:
                try:
                    zone_branch_check = verify_zone_branches(zone, reference_branches)
                    branch_audit['zones'][zone_name] = {
                        'total': zone_branch_check['total'],
                        'resolved': zone_branch_check['resolved'],
                        'unresolved': zone_branch_check['unresolved'],
                    }
                    if zone_branch_check['unresolved']:
                        bad = [u['branch_id'] for u in zone_branch_check['unresolved']]
                        print(f"   ⚠️ [Branch Audit] Zone '{zone_name}' มี ID ที่ resolve ไม่ได้ "
                              f"{len(bad)}/{zone_branch_check['total']} ตัว: {bad[:20]}")
                        print(f"      -> สาขาเหล่านี้จะไม่ถูกดึงข้อมูล ทำให้ยอดไม่ตรงกับ techswop")
                except Exception as ze:
                    print(f"   ⚠️ [Branch Audit] ตรวจ zone '{zone_name}' ไม่สำเร็จ: {ze}")

            # 1. ดึงข้อมูลวันนี้จาก Eve
            trade_data, all_success = fetch_zone_daily_data(zone, target_date_dt)
            
            # 2. บันทึกลง Turso
            eve_count = len(trade_data)
            inserted = 0
            
            # 🛡️ กันข้อมูลหาย: ถ้า Eve คืน 0 รายการ แต่ Turso มีข้อมูลอยู่แล้ว
            # อย่าลบทิ้ง เพราะมักเป็นอาการ Eve ล่ม/session หลุด ไม่ใช่วันที่ไม่มีเทรดจริง
            wiped_guard = False
            if all_success and not trade_data:
                try:
                    existing = turso.reconcile_snapshot([], zone_name,
                                                        target_date.strftime("%Y-%m-%d"))
                    existing_count = int(existing.get('turso_count') or 0)
                except Exception:
                    existing_count = 0
                if existing_count > 0:
                    wiped_guard = True
                    print(f"   🛡️ Eve คืน 0 รายการ แต่ Turso มี {existing_count:,} รายการ "
                          f"— ไม่ลบข้อมูลเดิม (น่าจะดึงข้อมูลไม่สำเร็จ ไม่ใช่วันที่ไม่มีเทรด)")

            # ถ้าดึงสำเร็จครบทุกสาขา ให้ล้างข้อมูลเก่าของโซนนั้นในวันนี้ก่อน เพื่อความถูกต้อง 100%
            if all_success and not wiped_guard:
                turso.delete_zone_records(zone_name, target_date_dt)
            elif not all_success:
                print(f"   ⚠️ Warning: Some branches in Zone '{zone_name}' failed to fetch. Updating without clearing.")

            if trade_data:
                inserted = turso.insert_trades_batch(trade_data, zone_name)
                print(f"   ✅ Saved {inserted} records to Turso Database")
            else:
                print("   ℹ️ No data found for this zone on target date")

            # 3. Reconcile: Eve snapshot vs Turso snapshot after write
            reconcile = turso.reconcile_snapshot(trade_data, zone_name, target_date.strftime("%Y-%m-%d"))
            unresolved_branches = zone_branch_check.get('unresolved', [])
            is_consistent = (bool(reconcile.get('success'))
                             and inserted == eve_count
                             and not unresolved_branches
                             and not wiped_guard)
            if is_consistent:
                print(f"   ✅ Reconcile OK: Eve={eve_count} / Turso={reconcile.get('turso_count')}")
                status = 'success'
                error_message = ''
            else:
                total_warnings += 1
                status = 'warning'
                error_message = (
                    f"Reconcile mismatch: Eve={eve_count}, inserted={inserted}, "
                    f"Turso={reconcile.get('turso_count')}, "
                    f"missing={reconcile.get('missing_count')}, extra={reconcile.get('extra_count')}"
                )
                if wiped_guard:
                    error_message += " | ข้ามการเขียนทับเพราะ Eve คืน 0 รายการ (ข้อมูลเดิมยังอยู่)"
                if unresolved_branches:
                    bad_ids = [u['branch_id'] for u in unresolved_branches]
                    error_message += (
                        f" | branch_id ที่ resolve ไม่ได้ "
                        f"{len(bad_ids)}/{zone_branch_check.get('total', 0)}: {bad_ids[:20]}"
                    )
                warnings.append({
                    'zone_name': zone_name,
                    'date': target_date.strftime("%Y-%m-%d"),
                    'expected_count': eve_count,
                    'inserted_count': inserted,
                    'turso_count': reconcile.get('turso_count'),
                    'missing_count': reconcile.get('missing_count'),
                    'extra_count': reconcile.get('extra_count'),
                    'missing_ids_sample': reconcile.get('missing_ids_sample', []),
                    'extra_ids_sample': reconcile.get('extra_ids_sample', []),
                    'checksum_match': reconcile.get('checksum_match'),
                    'unresolved_branch_ids': [u['branch_id'] for u in unresolved_branches],
                    'branches_total': zone_branch_check.get('total', 0),
                    'branches_resolved': zone_branch_check.get('resolved', 0),
                })
                print(f"   ⚠️ {error_message}")

            zone_duration = time.time() - zone_start
            zone_durations.append(zone_duration)

            # บันทึกความคืบหน้าราย zone — จุดสำคัญที่ทำให้ resume ได้
            # 'warning' ก็ถือว่าทำแล้ว ไม่งั้นจะวนทำ zone เดิมซ้ำไม่จบ
            save_sync_progress(
                target_date, zone_id, zone_name,
                'done' if status == 'success' else 'done_warning',
                inserted, 1, error_message,
            )

            # บันทึก log
            save_auto_sync_log({
                'zone_id': zone_id,
                'zone_name': zone_name,
                'date_sync': date_str_display,
                'total_records': inserted,
                'status': status,
                'error_message': error_message,
                'duration_seconds': zone_duration
            })
            
            total_records += inserted
            total_synced_zones += 1
            
            results.append({
                'zone_name': zone_name,
                'records': inserted,
                'eve_records': eve_count,
                'turso_records': reconcile.get('turso_count'),
                'status': status,
                'reconcile': reconcile,
                'duration': f"{zone_duration:.1f}s"
            })
            
        except Exception as e:
            zone_duration = time.time() - zone_start
            zone_durations.append(zone_duration)
            error_msg = str(e)
            print(f"❌ Zone '{zone_name}' sync failed: {error_msg}")

            # ลองใหม่ได้ไม่เกิน MAX_ZONE_ATTEMPTS ครั้ง แล้วปล่อยผ่านไป zone อื่น
            # กันไม่ให้ zone เดียวที่พังค้างบล็อกทั้งวัน
            prev_attempts = int((progress_map.get(str(zone_id), {}) or {}).get('attempts') or 0)
            fail_status = 'failed_final' if prev_attempts + 1 >= MAX_ZONE_ATTEMPTS else 'failed'
            if fail_status == 'failed_final':
                print(f"   ⛔ Zone '{zone_name}' ล้มเหลวครบ {MAX_ZONE_ATTEMPTS} ครั้ง — ข้ามไปก่อน")
            save_sync_progress(target_date, zone_id, zone_name, fail_status,
                               0, 1, error_msg)

            save_auto_sync_log({
                'zone_id': zone_id,
                'zone_name': zone_name,
                'date_sync': date_str_display,
                'total_records': 0,
                'status': 'failed',
                'error_message': error_msg,
                'duration_seconds': zone_duration
            })
            
            total_errors += 1
            results.append({
                'zone_name': zone_name,
                'records': 0,
                'status': 'failed',
                'error': error_msg,
                'duration': f"{zone_duration:.1f}s"
            })
    
    total_duration = time.time() - start_time
    turso.close()

    # 5.5 เช็คว่าครบทุก zone ของวันนี้แล้วหรือยัง (จาก sync_progress)
    try:
        completed, zones_done, zones_total, pending_names = is_sync_complete(
            target_date, zones=all_zones_for_check)
    except Exception as ce:
        print(f"⚠️ ตรวจสถานะ sync ไม่สำเร็จ: {ce}")
        completed, zones_done, zones_total, pending_names = (not stopped_early), 0, all_zone_count, []

    zones_remaining = max(0, zones_total - zones_done) if zones_total else 0

    if completed:
        print(f"✅ sync ครบทุก zone แล้วสำหรับ {date_str_display} ({zones_done}/{zones_total})")
    else:
        print(f"⏳ ยังไม่ครบ: {zones_done}/{zones_total} zone — "
              f"เหลือ {zones_remaining} zone ({', '.join(pending_names[:5])})")

    # 6. ส่ง Telegram notification
    # ส่งเฉพาะตอนจบวัน หรือมี error เพื่อไม่ให้สแปมทุก chunk
    try:
        from app import get_auto_cancel_config, send_telegram_notification
        
        cancel_config = get_auto_cancel_config()
        if cancel_config:
            bot_token = cancel_config.get('telegram_bot_token', '')
            chat_id = cancel_config.get('telegram_chat_id', '')
            
            should_notify = completed or total_errors > 0
            if bot_token and chat_id and should_notify:
                msg = f"""🗄️ <b>Auto Turso Sync Report</b>
📅 ข้อมูลวันที่: {date_str_display}
⏰ เวลารัน: {now_bkk.strftime('%d/%m/%Y %H:%M')}

📊 <b>สรุป:</b>
🗺️ Zone ทั้งหมด: {zones_total or all_zone_count}
{'✅ ครบทุก zone แล้ว' if completed else f'⏳ ยังไม่ครบ — เหลือ {zones_remaining} zone'}
✅ สำเร็จรอบนี้: {total_synced_zones} zone
❌ ล้มเหลว: {total_errors} zone
⚠️ ข้อมูลไม่ตรง: {total_warnings} zone
📋 รายการใหม่: {total_records:,} records
⏱️ ใช้เวลา: {total_duration:.1f} วินาที

📋 <b>รายละเอียด:</b>"""
                
                for r in results:
                    if r['status'] == 'success':
                        msg += f"\n✅ {r['zone_name']}: {r['records']:,} records"
                    elif r['status'] == 'warning':
                        rec = r.get('reconcile', {})
                        msg += f"\n⚠️ {r['zone_name']}: Eve {r.get('eve_records', 0):,} / Turso {rec.get('turso_count', 0):,}"
                    else:
                        msg += f"\n❌ {r['zone_name']}: {r.get('error', 'error')}"

                # แจ้งเตือนปัญหาสาขาหลุด (สาเหตุที่ยอดไม่ตรงแบบเงียบๆ)
                bad_zones = {
                    zn: info for zn, info in branch_audit.get('zones', {}).items()
                    if info.get('unresolved')
                }
                if bad_zones:
                    msg += "\n\n🚨 <b>สาขาใน Zone ที่ใช้ไม่ได้:</b>"
                    for zn, info in list(bad_zones.items())[:10]:
                        ids = [u['branch_id'] for u in info['unresolved']]
                        msg += (f"\n• {zn}: {len(ids)}/{info['total']} ID resolve ไม่ได้"
                                f" → {', '.join(ids[:10])}")
                    msg += "\n<i>สาขาเหล่านี้ไม่ถูกดึงข้อมูล ยอดจะต่ำกว่าความจริง</i>"

                unassigned = branch_audit.get('unassigned') or []
                if unassigned:
                    msg += f"\n\n🏪 <b>สาขาที่ยังไม่อยู่ใน Zone ไหนเลย: {len(unassigned)} สาขา</b>"
                    for b in unassigned[:10]:
                        msg += f"\n• {b['branch_name']}"
                    if len(unassigned) > 10:
                        msg += f"\n<i>... และอีก {len(unassigned) - 10} สาขา</i>"

                send_telegram_notification(bot_token, chat_id, msg)
    except Exception as tg_err:
        print(f"⚠️ Telegram notification error: {tg_err}")
    
    print(f"\n{'=' * 60}")
    print(f"🗄️ Auto Turso Sync Completed in {total_duration:.1f}s")
    print(f"   Zones: {total_synced_zones}, Records: {total_records}, Errors: {total_errors}, Warnings: {total_warnings}")
    print(f"{'=' * 60}\n")
    
    return {
        'success': completed and total_errors == 0 and total_warnings == 0,
        'completed': completed,
        'zones_done': zones_done,
        'zones_remaining': zones_remaining,
        'zones_pending_names': pending_names[:20],
        'zones_skipped_done': skipped_done,
        'stopped_early': stopped_early,
        'sync_date': date_str_display,
        'branch_audit': branch_audit,
        'sync_completed': total_errors == 0,
        'data_consistent': total_warnings == 0,
        'total_zones': zones_total or all_zone_count,
        'total_synced': total_synced_zones,
        'total_records': total_records,
        'total_errors': total_errors,
        'total_warnings': total_warnings,
        'warnings': warnings,
        'duration': f"{total_duration:.1f}s",
        'results': results
    }
