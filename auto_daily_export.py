# Auto Daily Turso Sync Engine
# ระบบ Sync ข้อมูล trade รายวันอัตโนมัติเข้าสู่ Turso Database (ยกเลิก Google Drive ถาวร)

import json
import os
import time
from datetime import datetime, timedelta
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


def fetch_zone_daily_data(zone, target_date):
    """ดึงข้อมูลของโซนเฉพาะวันที่ระบุจาก API ของ Eve"""
    from app import fetch_all_for_branch
    
    date_str = target_date.strftime("%d/%m/%Y")
    branch_ids = zone.get('branch_ids', [])
    all_items = []
    
    print(f"📊 Fetching data for Zone '{zone['zone_name']}' on {date_str}")
    
    for branch_id in branch_ids:
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
            all_items.extend(items)
        except Exception as e:
            print(f"   ❌ Branch {branch_id} error: {e}")
    
    return all_items


def run_daily_export(force=False):
    """ฟังก์ชันหลัก: Sync ข้อมูลรายวันเข้า Turso Database
    Args:
        force: True = บังคับรัน (ไม่ตรวจสอบว่ารันไปแล้วหรือยัง)
    Returns:
        dict: ผลการรัน
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
    target_date = (now_bkk - timedelta(days=1)).date()
    target_date_dt = datetime.combine(target_date, datetime.min.time())
    
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
        return {'success': False, 'message': 'ไม่มี zone ที่ต้องการ sync'}
    
    print(f"📋 Zones to sync: {len(zones_to_sync)}")
    
    # 5. Sync แต่ละ Zone
    results = []
    total_records = 0
    total_synced_zones = 0
    total_errors = 0
    total_warnings = 0
    warnings = []
    
    for zone_idx, zone in enumerate(zones_to_sync):
        zone_name = zone['zone_name']
        zone_id = zone['zone_id']
        zone_start = time.time()
        
        print(f"\n📦 [{zone_idx+1}/{len(zones_to_sync)}] Syncing Zone: {zone_name}")
        
        try:
            # 1. ดึงข้อมูลวันนี้จาก Eve
            trade_data = fetch_zone_daily_data(zone, target_date_dt)
            
            # 2. บันทึกลง Turso
            eve_count = len(trade_data)
            inserted = 0
            if trade_data:
                inserted = turso.insert_trades_batch(trade_data, zone_name)
                print(f"   ✅ Saved {inserted} records to Turso Database")
            else:
                print("   ℹ️ No data found for this zone on target date")

            # 3. Reconcile: Eve snapshot vs Turso snapshot after write
            reconcile = turso.reconcile_snapshot(trade_data, zone_name, target_date.strftime("%Y-%m-%d"))
            is_consistent = bool(reconcile.get('success')) and inserted == eve_count
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
                    'checksum_match': reconcile.get('checksum_match')
                })
                print(f"   ⚠️ {error_message}")

            zone_duration = time.time() - zone_start
            
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
            error_msg = str(e)
            print(f"❌ Zone '{zone_name}' sync failed: {error_msg}")
            
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
        
    # 6. ส่ง Telegram notification
    try:
        from app import get_auto_cancel_config, send_telegram_notification
        
        cancel_config = get_auto_cancel_config()
        if cancel_config:
            bot_token = cancel_config.get('telegram_bot_token', '')
            chat_id = cancel_config.get('telegram_chat_id', '')
            
            if bot_token and chat_id:
                msg = f"""🗄️ <b>Auto Turso Sync Report</b>
📅 ข้อมูลวันที่: {date_str_display}
⏰ เวลารัน: {now_bkk.strftime('%d/%m/%Y %H:%M')}

📊 <b>สรุป:</b>
🗺️ Zone ทั้งหมด: {len(zones_to_sync)}
✅ สำเร็จ: {total_synced_zones} zone
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
                
                send_telegram_notification(bot_token, chat_id, msg)
    except Exception as tg_err:
        print(f"⚠️ Telegram notification error: {tg_err}")
    
    print(f"\n{'=' * 60}")
    print(f"🗄️ Auto Turso Sync Completed in {total_duration:.1f}s")
    print(f"   Zones: {total_synced_zones}, Records: {total_records}, Errors: {total_errors}, Warnings: {total_warnings}")
    print(f"{'=' * 60}\n")
    
    return {
        'success': total_errors == 0 and total_warnings == 0,
        'total_zones': len(zones_to_sync),
        'total_synced': total_synced_zones,
        'total_records': total_records,
        'total_errors': total_errors,
        'total_warnings': total_warnings,
        'warnings': warnings,
        'duration': f"{total_duration:.1f}s",
        'results': results
    }
