# LINE Bot Message Handler
from datetime import datetime, timedelta
from collections import defaultdict
import json
import os
import pytz

import hmac
import hashlib
import base64
import requests

from constants import CONFIRMED_STATUSES, is_pretrade, pick_campaign_name

BKK_TZ = pytz.timezone('Asia/Bangkok')


def now_bkk():
    """เวลาปัจจุบันตามโซนเวลาไทย (เซิร์ฟเวอร์ deploy อาจรันเป็น UTC เช่น Vercel/Render)"""
    return datetime.now(BKK_TZ)


def fetch_all_pages(fetch_data_func, filters, page_size=1000, max_records=20000):
    """ดึงข้อมูลวนทุกหน้าจนครบ (ป้องกันไม่ให้รายการเกิน 1 หน้าถูกตัดทิ้งแบบเงียบๆ)
    คืนค่ารูปแบบเดียวกับ fetch_data_func ปกติ แต่ 'data' รวมทุกหน้าแล้ว
    """
    data = fetch_data_func(start=0, length=page_size, **filters)
    if not data or 'error' in data:
        return data

    items = data.get('data', [])
    total = data.get('recordsFiltered', len(items))

    while len(items) < total and len(items) < max_records:
        more = fetch_data_func(start=len(items), length=page_size, **filters)
        more_items = more.get('data', []) if more else []
        if not more_items:
            break
        items.extend(more_items)

    if len(items) < total:
        print(f"⚠️ [fetch_all_pages] ดึงได้ {len(items)}/{total} รายการ (ชนขีดจำกัด {max_records})")

    data['data'] = items
    return data


def load_supersale_config():
    """โหลด config สาขา supersale จาก DB (standalone, ไม่ import จาก app.py)"""
    try:
        import psycopg2
        import psycopg2.extras
        database_url = os.environ.get('POSTGRES_URL_NON_POOLING') or os.environ.get('DATABASE_URL')
        if not database_url:
            return []
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_settings WHERE key = 'supersale_branch_ids'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return json.loads(row['value'])
        return []
    except Exception as e:
        print(f"⚠️ load_supersale_config error: {e}")
        return []

def get_sale_key(item, branch_id, supersale_ids):
    """ดึงรหัสพนักงานตาม supersale config
    - สาขาปกติ: ใช้ SALE_CODE
    - สาขา supersale: ใช้ SALE_NAME (เพราะรหัส sale ปกติอยู่ในช่องนี้)
    """
    try:
        if int(branch_id) in supersale_ids:
            return item.get('SALE_NAME', '') or item.get('SALE_CODE', '')
    except (ValueError, TypeError):
        pass
    return item.get('SALE_CODE', '')

def verify_line_signature(channel_secret, body, signature):
    """Verify LINE Webhook signature manually (HMAC-SHA256)"""
    hash = hmac.new(channel_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash).decode('utf-8')
    return hmac.compare_digest(expected_signature, signature)

def send_line_reply(channel_access_token, reply_token, messages):
    """Send reply message to LINE API manually (supports auto-chunking for long text)"""
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {channel_access_token}'
    }
    
    final_messages = []
    
    # ถ้าส่งมาเป็น string ให้แปลงเป็น list ของ dict
    if isinstance(messages, str):
        # 🛡️ Chunking Logic: LINE จำกัด 5,000 ตัวอักษรต่อ 1 ข้อความ และ 5 ข้อความต่อ 1 Reply
        if len(messages) > 5000:
            print(f"📏 Message too long ({len(messages)} chars). Splitting into chunks...")
            text = messages
            while text and len(final_messages) < 5:
                if len(text) <= 5000:
                    final_messages.append({'type': 'text', 'text': text})
                    break
                
                # พยายามตัดที่บรรทัดใหม่เพื่อความสวยงาม
                chunk_limit = 4900
                split_pos = text.rfind('\n', 0, chunk_limit)
                if split_pos == -1: split_pos = chunk_limit
                
                final_messages.append({'type': 'text', 'text': text[:split_pos].strip()})
                text = text[split_pos:].strip()
                
            # ถ้ายังเหลือข้อความอีกแต่ครบ 5 ข้อความแล้ว ให้ Truncate และใส่ ...
            if text and len(final_messages) == 5:
                last_msg = final_messages[-1]['text']
                if len(last_msg) > 4900: last_msg = last_msg[:4890]
                final_messages[-1]['text'] = last_msg + "\n\n...(ข้อความถูกตัดเพราะยาวเกินไป)"
        else:
            final_messages = [{'type': 'text', 'text': messages}]
    elif isinstance(messages, dict):
        final_messages = [messages]
    else:
        final_messages = messages
        
    data = {
        'replyToken': reply_token,
        'messages': final_messages
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error_msg = f"❌ Error sending LINE reply: {e}"
        if hasattr(e, 'response') and e.response is not None:
             error_msg += f" | Response: {e.response.text}"
        print(error_msg)
        return {"success": False, "error": error_msg}
def handle_line_message(user_message, fetch_data_func, load_zones_func, find_zone_func, find_branch_func, parse_month_func, get_date_range_func, fetch_batch_func=None):
    """
    จัดการข้อความจาก LINE และส่งกลับ response message
    
    คำสั่งที่รองรับ:
    1. รายงาน zone [ชื่อโซน] - รายงานวันนี้ของ Zone
    2. รายงาน [เดือน] zone [ชื่อโซน] - รายงานทั้งเดือนของ Zone
    3. รายงาน [branch_id] รายวัน - รายงานวันนี้ของสาขา แยกตามพนักงาน
    4. รายงาน [branch_id] [เดือน] - รายงานทั้งเดือนของสาขา แยกตามพนักงาน
    5. รายงาน excel รายปี [ปี] [branch_id] - รายงาน Excel รายปี
    """
    
    clean_message = user_message.strip()
    
    # ตรวจสอบคำสั่ง "วิธีใช้"
    if clean_message in ['วิธีใช้', 'help', 'ช่วยเหลือ']:
        return get_help_message()
    
    if not clean_message.startswith('รายงาน'):
        return None
    
    # ลบคำว่า "รายงาน" ออก
    command = clean_message[7:].strip()  # ตัดคำว่า "รายงาน " (7 ตัวอักษร)
    
    if not command:
        return "❌ กรุณาระบุคำสั่ง\n\nตัวอย่าง:\n• รายงาน zone พี่โอ๊ค\n• รายงาน 9 รายวัน (สาขา ID9)\n• รายงาน 13 พฤศจิกายน (สาขา ID13)\n• รายงาน พฤศจิกายน zone พี่โอ๊ค\n• รายงาน excel รายปี 2024"
    
    # แยกคำสั่ง
    parts = command.split()
    
    # ---- คำสั่ง pre trade ----
    if parts and parts[0].lower() in ('pretrade', 'pre-trade', 'pre_trade'):
        return handle_pretrade_command(
            parts[1:], find_zone_func, find_branch_func, fetch_data_func,
            parse_month_func, get_date_range_func, fetch_batch_func)
    if len(parts) >= 2 and parts[0].lower() == 'pre' and parts[1].lower() == 'trade':
        return handle_pretrade_command(
            parts[2:], find_zone_func, find_branch_func, fetch_data_func,
            parse_month_func, get_date_range_func, fetch_batch_func)

    # ตรวจสอบคำสั่ง Excel รายปี
    if 'excel' in parts and 'รายปี' in parts:
        # รายงาน excel รายปี [ปี] [branch_id]
        return {'type': 'excel_annual', 'parts': parts}
    
    # ตรวจสอบรูปแบบคำสั่งอื่นๆ
    if 'zone' in parts:
        # คำสั่งเกี่ยวกับ Zone
        zone_index = parts.index('zone')
        
        if zone_index == 0:
            # รายงาน zone [ชื่อโซน] - วันนี้
            zone_name = ' '.join(parts[1:])
            return generate_zone_daily_report(zone_name, find_zone_func, fetch_data_func, fetch_batch_func)
        else:
            # รายงาน [เดือน] zone [ชื่อโซน] - ทั้งเดือน
            month_name = ' '.join(parts[:zone_index])
            zone_name = ' '.join(parts[zone_index+1:])
            return generate_zone_monthly_report(zone_name, month_name, find_zone_func, fetch_data_func, parse_month_func, get_date_range_func, fetch_batch_func)
    
    elif 'รายวัน' in parts:
        # รายงาน [branch_id] รายวัน
        branch_id = parts[0]
        return generate_branch_daily_report(branch_id, find_branch_func, fetch_data_func)
    
    elif len(parts) >= 2:
        # รายงาน [branch_id] [เดือน]
        branch_id = parts[0]
        month_name = ' '.join(parts[1:])
        return generate_branch_monthly_report(branch_id, month_name, find_branch_func, fetch_data_func, parse_month_func, get_date_range_func)
    
    else:
        return "❌ คำสั่งไม่ถูกต้อง\n\nตัวอย่าง:\n• รายงาน zone พี่โอ๊ค\n• รายงาน 9 รายวัน (สาขา ID9)\n• รายงาน 13 พฤศจิกายน (สาขา ID13)\n• รายงาน พฤศจิกายน zone พี่โอ๊ค\n• รายงาน excel รายปี 2024"


def generate_zone_daily_report(zone_name, find_zone_func, fetch_data_func, fetch_batch_func=None):
    """สร้างรายงานวันนี้ของ Zone (แยกตามสาขา)"""
    zone = find_zone_func(zone_name)
    
    if not zone:
        return f"❌ ไม่พบ Zone: {zone_name}"
    
    today = now_bkk().strftime('%d/%m/%Y')
    branch_ids = zone['branch_ids']

    # โหลดข้อมูลสาขา
    branches_map = load_branches_map()

    message = f"📊 รายงานยอดเทรด\n"
    message += f"📅 วันที่: {today}\n"
    message += f"🗺️ Zone: {zone['zone_name']}\n"
    message += f"🏢 จำนวนสาขา: {len(branch_ids)} สาขา\n"
    message += f"━━━━━━━━━━━━\n\n"
    
    total_all = 0
    confirmed_all = 0
    last_source = "unknown"
    
    # ลองใช้ Batch Fetch ถ้ามี
    batch_data = None
    if fetch_batch_func:
        batch_data = fetch_batch_func(branch_ids, today, today)
    
    for branch_id in branch_ids:
        data = None
        if batch_data and str(branch_id) in batch_data:
            data = batch_data[str(branch_id)]
        else:
            filters = {
                'date_start': today,
                'date_end': today,
                'sale_code': '',
                'customer_sign': '',
                'session_id': '',
                'branch_id': str(branch_id)
            }
            
            data = fetch_all_pages(fetch_data_func, filters, page_size=1000)

        last_source = data.get('source', 'unknown')
        
        branch_name = branches_map.get(str(branch_id), f"สาขา {branch_id}")
        if ' : ' in branch_name:
            branch_name = branch_name.split(' : ', 2)[-1]
        
        if 'error' not in data:
            items = data.get('data', [])
            total_count = len(items)
            confirmed_count = sum(1 for item in items
                                 if item.get('BIDDING_STATUS_NAME', '') in CONFIRMED_STATUSES)
            not_confirmed_count = total_count - confirmed_count

            total_all += total_count
            confirmed_all += confirmed_count
        else:
            total_count = 0
            confirmed_count = 0
            not_confirmed_count = 0
        
        # คำนวณเปอร์เซ็นต์ของสาขา
        confirmed_percent = (confirmed_count / total_count * 100) if total_count > 0 else 0
        not_confirmed_percent = (not_confirmed_count / total_count * 100) if total_count > 0 else 0
        
        message += f"🏪 {branch_name}\n"
        message += f"  • ทั้งหมด: {total_count} รายการ\n"
        if total_count > 0:
            message += f"  • ตกลง: ✅{confirmed_count} ({confirmed_percent:.0f}%) ❌{not_confirmed_count} ({not_confirmed_percent:.0f}%)\n\n"
        else:
            message += f"  • ตกลง: ✅{confirmed_count} ❌{not_confirmed_count}\n\n"
    
    message += f"━━━━━━━━━━━━\n"
    message += f"📈 สรุปรวมทั้ง Zone\n"
    message += f"• รายการทั้งหมด: {total_all} รายการ\n"
    
    if total_all > 0:
        confirm_percent = (confirmed_all / total_all) * 100
        message += f"• ลูกค้าตกลง: {confirmed_all} รายการ ({confirm_percent:.0f}%)\n"
        message += f"• ลูกค้าไม่ตกลง: {total_all - confirmed_all} รายการ ({100-confirm_percent:.0f}%)"
    else:
        message += f"• ลูกค้าตกลง: {confirmed_all} รายการ\n"
        message += f"• ลูกค้าไม่ตกลง: {total_all - confirmed_all} รายการ"
    
    # เพิ่มแหล่งที่มา
    source_display = "📦 Turso" if last_source == 'turso' else "🌐 Real-time"
    message += f"\n\n(Source: {source_display})"
    
    return message


def generate_branch_daily_report(branch_id_input, find_branch_func, fetch_data_func):
    """สร้างรายงานวันนี้ของสาขา (แยกตามพนักงาน)"""
    branch = find_branch_func(branch_id_input)
    
    if not branch:
        return f"❌ ไม่พบสาขา ID: {branch_id_input}\n\nตัวอย่าง: รายงาน 9 รายวัน (สำหรับสาขา ID9)"
    
    today = now_bkk().strftime('%d/%m/%Y')
    thai_date = format_thai_date(now_bkk())

    # โหลด supersale config
    supersale_ids = load_supersale_config()

    filters = {
        'date_start': today,
        'date_end': today,
        'sale_code': '',
        'customer_sign': '',
        'session_id': '',
        'branch_id': str(branch['branch_id'])
    }

    data = fetch_all_pages(fetch_data_func, filters, page_size=1000)

    if not data or 'error' in data:
        return f"❌ ไม่สามารถดึงข้อมูลได้: {data.get('error') if data else 'ไม่ทราบสาเหตุ'}"

    items = data.get('data', [])

    # จัดกลุ่มตามพนักงาน
    sales_summary = defaultdict(lambda: {
        'name': '',
        'count': 0,
        'confirmed': 0,
        'not_confirmed': 0,
        'amount': 0.0
    })

    for item in items:
        sale_key = get_sale_key(item, branch['branch_id'], supersale_ids)
        if not sale_key:
            continue

        status = item.get('BIDDING_STATUS_NAME', '')
        is_confirmed = status in CONFIRMED_STATUSES

        amount_value = item.get('amount')
        try:
            amount = float(amount_value) if amount_value else 0.0
        except:
            amount = 0.0
        
        sales_summary[sale_key]['name'] = ''
        sales_summary[sale_key]['count'] += 1
        sales_summary[sale_key]['amount'] += amount
        
        if is_confirmed:
            sales_summary[sale_key]['confirmed'] += 1
        else:
            sales_summary[sale_key]['not_confirmed'] += 1
    
    # สร้างข้อความ
    import re
    branch_name = branch['branch_name'].split(' : ', 2)[-1] if ' : ' in branch['branch_name'] else branch['branch_name']
    
    # ดึง ID number จาก branch_name (เช่น ID9 -> 9)
    id_match = re.search(r'ID(\d+)', branch['branch_name'])
    id_display = f"ID{id_match.group(1)}" if id_match else branch_id_input
    
    message = f"📊 รายงานรายวัน (trade-in)\n"
    message += f"🏪 สาขา: {branch_name} ({id_display})\n"
    message += f"📅 วันที่: {thai_date}\n"
    message += f"━━━━━━━━━━━━\n\n"
    
    if not sales_summary:
        message += "ไม่มีข้อมูลในวันนี้"
        return message
    
    # เรียงตามจำนวนรายการ
    sorted_sales = sorted(sales_summary.items(), key=lambda x: x[1]['count'], reverse=True)
    
    total_count = 0
    total_confirmed = 0
    total_amount = 0.0
    
    for sale_code, info in sorted_sales:
        message += f"👤 {sale_code}\n"
        message += f"  • ทั้งหมด: {info['count']} รายการ\n"
        message += f"  • ตกลง: ✅{info['confirmed']} ❌{info['not_confirmed']}\n\n"
        
        total_count += info['count']
        total_confirmed += info['confirmed']
        total_amount += info['amount']
    
    message += f"━━━━━━━━━━━━\n"
    message += f"📈 สรุปรวมสาขา\n"
    message += f"• รายการทั้งหมด: {total_count} รายการ\n"
    
    if total_count > 0:
        confirm_percent = (total_confirmed / total_count) * 100
        message += f"• ลูกค้าตกลง: {total_confirmed} รายการ ({confirm_percent:.0f}%)\n"
        message += f"• ลูกค้าไม่ตกลง: {total_count - total_confirmed} รายการ ({100-confirm_percent:.0f}%)"
    
    # เพิ่มแหล่งที่มา
    source = data.get('source', 'unknown')
    source_display = "📦 Turso" if source == 'turso' else "🌐 Real-time"
    message += f"\n\n(Source: {source_display})"
    
    return message


def calculate_forecast(total_so_far, month_number, year=None):
    """คำนวณ Forecast ยอดประเมินเมื่อครบเดือน (ประมาณการแบบเส้นตรงตามสัดส่วนวันที่ผ่านมา)
    คืนค่า None ถ้าไม่ใช่เดือนปัจจุบัน หรือเดือนนั้นจบไปแล้ว (ไม่มีอะไรต้องคาดการณ์เพิ่ม)
    """
    import calendar
    now = now_bkk()
    if year is None:
        year = now.year

    if month_number != now.month or year != now.year:
        return None

    days_in_month = calendar.monthrange(year, month_number)[1]
    days_elapsed = now.day

    if days_elapsed <= 0 or days_elapsed >= days_in_month:
        return None

    forecast_total = total_so_far / days_elapsed * days_in_month

    return {
        'forecast_total': forecast_total,
        'days_elapsed': days_elapsed,
        'days_in_month': days_in_month
    }


def generate_zone_monthly_report(zone_name, month_name, find_zone_func, fetch_data_func, parse_month_func, get_date_range_func, fetch_batch_func=None):
    """สร้างรายงานทั้งเดือนของ Zone (แยกตามสาขา)"""
    zone = find_zone_func(zone_name)
    
    if not zone:
        return f"❌ ไม่พบ Zone: {zone_name}"
    
    month_number = parse_month_func(month_name)
    if not month_number:
        return f"❌ ไม่รู้จักเดือน: {month_name}\n\nตัวอย่าง: มกราคม, กุมภาพันธ์, มีนาคม"
    
    date_start, date_end = get_date_range_func(month_number)
    branch_ids = zone['branch_ids']
    year = int(date_start.split('/')[-1]) + 543  # ปีจริงของช่วงวันที่ (เผื่อข้ามปี) แปลงเป็น พ.ศ.
    
    # โหลดข้อมูลสาขา
    branches_map = load_branches_map()
    
    message = f"📊 รายงานยอดเทรด\n"
    message += f"📅 เดือน: {month_name} {year}\n"
    message += f"🗺️ Zone: {zone['zone_name']}\n"
    message += f"🏢 จำนวนสาขา: {len(branch_ids)} สาขา\n"
    message += f"━━━━━━━━━━━━\n\n"
    
    total_all = 0
    confirmed_all = 0
    last_source = "unknown"
    
    # ลองใช้ Batch Fetch ถ้ามี
    batch_data = None
    if fetch_batch_func:
        batch_data = fetch_batch_func(branch_ids, date_start, date_end)
    
    for branch_id in branch_ids:
        data = None
        if batch_data and str(branch_id) in batch_data:
            data = batch_data[str(branch_id)]
        
        # ถ้าไม่มีใน batch หรือ batch return None -> fallback ดึงทีละสาขา
        if not data:
            filters = {
                'date_start': date_start,
                'date_end': date_end,
                'sale_code': '',
                'customer_sign': '',
                'session_id': '',
                'branch_id': str(branch_id)
            }
            data = fetch_all_pages(fetch_data_func, filters, page_size=5000)

        if not data:
            data = {'data': [], 'source': 'unknown'}

        last_source = data.get('source', 'unknown')

        branch_name = branches_map.get(str(branch_id), f"สาขา {branch_id}")
        if ' : ' in branch_name:
            branch_name = branch_name.split(' : ', 2)[-1]

        if 'error' not in data:
            items = data.get('data', [])
            total_count = len(items)
            confirmed_count = sum(1 for item in items
                                 if item.get('BIDDING_STATUS_NAME', '') in CONFIRMED_STATUSES)
            not_confirmed_count = total_count - confirmed_count
            
            total_all += total_count
            confirmed_all += confirmed_count
        else:
            total_count = 0
            confirmed_count = 0
            not_confirmed_count = 0
        
        # คำนวณเปอร์เซ็นต์ของสาขา
        confirmed_percent = (confirmed_count / total_count * 100) if total_count > 0 else 0
        not_confirmed_percent = (not_confirmed_count / total_count * 100) if total_count > 0 else 0
        
        message += f"🏪 {branch_name}\n"
        message += f"  • ทั้งหมด: {total_count} รายการ\n"
        if total_count > 0:
            message += f"  • ตกลง: ✅{confirmed_count} ({confirmed_percent:.0f}%) ❌{not_confirmed_count} ({not_confirmed_percent:.0f}%)\n\n"
        else:
            message += f"  • ตกลง: ✅{confirmed_count} ❌{not_confirmed_count}\n\n"
    
    message += f"━━━━━━━━━━━━\n"
    message += f"📈 สรุปรวมทั้ง Zone ({month_name[:3]}.)\n"
    message += f"• รายการทั้งหมด: {total_all} รายการ\n"
    
    if total_all > 0:
        confirm_percent = (confirmed_all / total_all) * 100
        message += f"• ลูกค้าตกลง: {confirmed_all} รายการ ({confirm_percent:.0f}%)\n"
        message += f"• ลูกค้าไม่ตกลง: {total_all - confirmed_all} รายการ ({100-confirm_percent:.0f}%)"
    else:
        message += f"• ลูกค้าตกลง: {confirmed_all} รายการ\n"
        message += f"• ลูกค้าไม่ตกลง: {total_all - confirmed_all} รายการ"

    forecast = calculate_forecast(total_all, month_number, year - 543)
    if forecast:
        message += f"\n\n🔮 คาดการณ์เมื่อครบเดือน: ~{forecast['forecast_total']:,.0f} รายการ"
        message += f"\n   (อิงจากข้อมูล {forecast['days_elapsed']}/{forecast['days_in_month']} วันที่ผ่านมา)"

    # เพิ่มแหล่งที่มา
    source_display = "📦 Turso" if last_source == 'turso' else "🌐 Real-time"
    message += f"\n\n(Source: {source_display})"

    return message


def generate_branch_monthly_report(branch_id, month_name, find_branch_func, fetch_data_func, parse_month_func, get_date_range_func):
    """สร้างรายงานทั้งเดือนของสาขา (แยกตามพนักงาน)"""
    branch = find_branch_func(branch_id)
    
    if not branch:
        return f"❌ ไม่พบสาขา: {branch_id}"
    
    month_number = parse_month_func(month_name)
    if not month_number:
        return f"❌ ไม่รู้จักเดือน: {month_name}\n\nตัวอย่าง: มกราคม, กุมภาพันธ์, มีนาคม"
    
    date_start, date_end = get_date_range_func(month_number)
    
    # โหลด supersale config
    supersale_ids = load_supersale_config()
    
    filters = {
        'date_start': date_start,
        'date_end': date_end,
        'sale_code': '',
        'customer_sign': '',
        'session_id': '',
        'branch_id': str(branch['branch_id'])
    }
    
    data = fetch_all_pages(fetch_data_func, filters, page_size=5000)

    if not data or 'error' in data:
        return f"❌ ไม่สามารถดึงข้อมูลได้: {data.get('error') if data else 'ไม่ทราบสาเหตุ'}"

    items = data.get('data', [])

    # จัดกลุ่มตามพนักงาน (เหมือน daily แต่ข้อมูลเยอะกว่า)
    sales_summary = defaultdict(lambda: {
        'name': '',
        'count': 0,
        'confirmed': 0,
        'not_confirmed': 0,
        'amount': 0.0
    })

    for item in items:
        sale_key = get_sale_key(item, branch['branch_id'], supersale_ids)
        if not sale_key:
            continue

        status = item.get('BIDDING_STATUS_NAME', '')
        is_confirmed = status in CONFIRMED_STATUSES
        
        amount_value = item.get('amount')
        try:
            amount = float(amount_value) if amount_value else 0.0
        except:
            amount = 0.0
        
        sales_summary[sale_key]['name'] = ''
        sales_summary[sale_key]['count'] += 1
        sales_summary[sale_key]['amount'] += amount
        
        if is_confirmed:
            sales_summary[sale_key]['confirmed'] += 1
        else:
            sales_summary[sale_key]['not_confirmed'] += 1
    
    # สร้างข้อความ
    import re
    branch_name = branch['branch_name'].split(' : ', 2)[-1] if ' : ' in branch['branch_name'] else branch['branch_name']
    year = int(date_start.split('/')[-1]) + 543  # ปีจริงของช่วงวันที่ (เผื่อข้ามปี) แปลงเป็น พ.ศ.
    
    # ดึง ID number จาก branch_name (เช่น ID9 -> 9)
    id_match = re.search(r'ID(\d+)', branch['branch_name'])
    id_display = f"ID{id_match.group(1)}" if id_match else branch_id
    
    message = f"📊 รายงานรายเดือน (Trade-in)\n"
    message += f"🏪 สาขา: {branch_name} ({id_display})\n"
    message += f"📅 เดือน: {month_name} {year}\n"
    message += f"━━━━━━━━━━━━\n\n"
    
    if not sales_summary:
        message += f"ไม่มีข้อมูลในเดือน{month_name}"
        return message
    
    # เรียงตามจำนวนรายการ
    sorted_sales = sorted(sales_summary.items(), key=lambda x: x[1]['count'], reverse=True)
    
    total_count = 0
    total_confirmed = 0
    total_amount = 0.0
    
    for sale_code, info in sorted_sales:
        message += f"👤 {sale_code}\n"
        message += f"  • ทั้งหมด: {info['count']} รายการ\n"
        message += f"  • ตกลง: ✅{info['confirmed']} ❌{info['not_confirmed']}\n\n"
        
        total_count += info['count']
        total_confirmed += info['confirmed']
        total_amount += info['amount']
    
    message += f"━━━━━━━━━━━━\n"
    message += f"📈 สรุปรวมสาขา ({month_name[:3]}.)\n"
    message += f"• รายการทั้งหมด: {total_count} รายการ\n"

    if total_count > 0:
        confirm_percent = (total_confirmed / total_count) * 100
        message += f"• ลูกค้าตกลง: {total_confirmed} รายการ ({confirm_percent:.0f}%)\n"
        message += f"• ลูกค้าไม่ตกลง: {total_count - total_confirmed} รายการ ({100-confirm_percent:.0f}%)"

    forecast = calculate_forecast(total_count, month_number, year - 543)
    if forecast:
        message += f"\n\n🔮 คาดการณ์เมื่อครบเดือน: ~{forecast['forecast_total']:,.0f} รายการ"
        message += f"\n   (อิงจากข้อมูล {forecast['days_elapsed']}/{forecast['days_in_month']} วันที่ผ่านมา)"

    # เพิ่มแหล่งที่มา
    source = data.get('source', 'unknown')
    source_display = "📦 Turso" if source == 'turso' else "🌐 Real-time"
    message += f"\n\n(Source: {source_display})"
    
    return message


# ==========================================
# รายงาน Pre Trade
# ------------------------------------------
# pre trade ถูกบันทึกเป็นแคมเปญ on-top (เช่น "4.Pre Trade iPhone Lock Price")
# ไม่ใช่ฟิลด์ IS_PRE_TRADE ของ Eve ซึ่งเป็น false เสมอ
# ==========================================

PRETRADE_HELP = """❌ คำสั่งไม่ถูกต้อง

รูปแบบคำสั่ง Pre Trade:

🗺️ ทั้ง Zone
• รายงาน pretrade zone Studio7
• รายงาน pretrade zone Studio7 กันยายน
• รายงาน pretrade zone Studio7 วันนี้

🏪 รายสาขา
• รายงาน pretrade 645
• รายงาน pretrade 645 กันยายน
• รายงาน pretrade 645 วันนี้

ไม่ระบุเดือน = เดือนปัจจุบัน"""

def _resolve_pretrade_period(tokens, parse_month_func, get_date_range_func):
    """แปลงคำท้ายคำสั่งเป็นช่วงวันที่

    Returns: (date_start, date_end, label, is_daily) หรือ (None, None, error, None)
    """
    text = ' '.join(tokens).strip()
    today = now_bkk()

    if not text:
        ds, de = get_date_range_func(today.month)
        return ds, de, f"{thai_month_name(today.month)} {today.year + 543}", False

    low = text.lower()
    if low in ('วันนี้', 'วันนี', 'today'):
        d = today.strftime('%d/%m/%Y')
        return d, d, f"วันนี้ ({d})", True
    if low in ('เมื่อวาน', 'เมื่อวานนี้', 'yesterday'):
        d = (today - timedelta(days=1)).strftime('%d/%m/%Y')
        return d, d, f"เมื่อวาน ({d})", True

    # วันที่ระบุเอง dd/mm/yyyy
    if '/' in text and len(text.split('/')) == 3:
        try:
            datetime.strptime(text, '%d/%m/%Y')
            return text, text, text, True
        except ValueError:
            pass

    month_number = parse_month_func(text)
    if month_number:
        ds, de = get_date_range_func(month_number)
        year = int(ds.split('/')[-1]) + 543
        return ds, de, f"{text} {year}", False

    return None, None, f"❌ ไม่รู้จักช่วงเวลา: {text}", None


def thai_month_name(m):
    names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
             'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    return names[m - 1] if 1 <= m <= 12 else str(m)


def _pretrade_stats(items):
    """นับ pre trade จากรายการดิบ"""
    pre = [it for it in items if is_pretrade(it)]
    total_amount = 0.0
    campaigns = defaultdict(int)
    confirmed = 0
    for it in pre:
        try:
            total_amount += float(it.get('amount') or it.get('AMOUNT') or 0)
        except (TypeError, ValueError):
            pass
        campaigns[pick_campaign_name(it) or '(ไม่ระบุแคมเปญ)'] += 1
        if str(it.get('BIDDING_STATUS_NAME', '')) in CONFIRMED_STATUSES:
            confirmed += 1
    return {
        'count': len(pre),
        'total': len(items),
        'amount': total_amount,
        'confirmed': confirmed,
        'campaigns': dict(campaigns),
    }


def handle_pretrade_command(tokens, find_zone_func, find_branch_func, fetch_data_func,
                            parse_month_func, get_date_range_func, fetch_batch_func=None):
    """รายงาน pre trade — รองรับ zone/สาขา x เดือน/วัน"""
    if not tokens:
        return PRETRADE_HELP

    if tokens[0].lower() == 'zone':
        if len(tokens) < 2:
            return PRETRADE_HELP
        # หา zone จากคำที่ยาวที่สุดที่ match ได้ ที่เหลือคือช่วงเวลา
        for split in range(len(tokens), 1, -1):
            zone_name = ' '.join(tokens[1:split])
            zone = find_zone_func(zone_name)
            if zone:
                return generate_pretrade_zone_report(
                    zone, tokens[split:], fetch_data_func, parse_month_func,
                    get_date_range_func, fetch_batch_func)
        return f"❌ ไม่พบ Zone: {' '.join(tokens[1:])}"

    return generate_pretrade_branch_report(
        tokens[0], tokens[1:], find_branch_func, fetch_data_func,
        parse_month_func, get_date_range_func)


def generate_pretrade_zone_report(zone, period_tokens, fetch_data_func,
                                  parse_month_func, get_date_range_func,
                                  fetch_batch_func=None):
    """รายงาน pre trade ทั้ง Zone แยกตามสาขา"""
    ds, de, label, is_daily = _resolve_pretrade_period(
        period_tokens, parse_month_func, get_date_range_func)
    if ds is None:
        return label

    branch_ids = zone['branch_ids']
    branches_map = load_branches_map()

    batch_data = None
    if fetch_batch_func:
        batch_data = fetch_batch_func(branch_ids, ds, de)

    per_branch = []
    grand = {'count': 0, 'total': 0, 'amount': 0.0, 'confirmed': 0}
    campaigns = defaultdict(int)
    last_source = 'unknown'

    for branch_id in branch_ids:
        data = None
        if batch_data and str(branch_id) in batch_data:
            data = batch_data[str(branch_id)]
        if not data:
            data = fetch_all_pages(fetch_data_func, {
                'date_start': ds, 'date_end': de, 'sale_code': '',
                'customer_sign': '', 'session_id': '', 'branch_id': str(branch_id),
            }, page_size=5000)
        if not data or 'error' in data:
            continue

        last_source = data.get('source', last_source)
        st = _pretrade_stats(data.get('data', []))
        grand['count'] += st['count']
        grand['total'] += st['total']
        grand['amount'] += st['amount']
        grand['confirmed'] += st['confirmed']
        for k, v in st['campaigns'].items():
            campaigns[k] += v

        if st['count'] > 0:
            name = branches_map.get(str(branch_id), f"สาขา {branch_id}")
            if ' : ' in name:
                name = name.split(' : ', 2)[-1]
            per_branch.append((name, st['count'], st['amount']))

    msg = "🎯 รายงาน Pre Trade\n"
    msg += f"📅 {label}\n"
    msg += f"🗺️ Zone: {zone['zone_name']}\n"
    msg += f"🏢 จำนวนสาขา: {len(branch_ids)} สาขา\n"
    msg += "━━━━━━━━━━━━\n\n"

    if grand['count'] == 0:
        msg += "ไม่มีรายการ Pre Trade ในช่วงนี้\n"
        msg += f"\n(ตรวจแล้ว {grand['total']:,} รายการทั้งหมด)"
        return msg

    per_branch.sort(key=lambda x: x[1], reverse=True)
    for name, cnt, amt in per_branch[:25]:
        msg += f"🏪 {name}\n"
        msg += f"  • {cnt} รายการ · {amt:,.0f} บาท\n\n"
    if len(per_branch) > 25:
        msg += f"... และอีก {len(per_branch) - 25} สาขา\n\n"

    pct = grand['count'] / grand['total'] * 100 if grand['total'] else 0
    cpct = grand['confirmed'] / grand['count'] * 100 if grand['count'] else 0
    msg += "━━━━━━━━━━━━\n"
    msg += "📈 สรุปรวมทั้ง Zone\n"
    msg += f"• Pre Trade: {grand['count']:,} รายการ ({pct:.0f}% ของทั้งหมด)\n"
    msg += f"• ยอดประเมิน: {grand['amount']:,.0f} บาท\n"
    msg += f"• ลูกค้าตกลง: {grand['confirmed']:,} ({cpct:.0f}%)\n"
    msg += f"• สาขาที่มี Pre Trade: {len(per_branch)}/{len(branch_ids)}"

    if len(campaigns) > 1:
        msg += "\n\n🏷️ แยกตามแคมเปญ"
        for cname, ccount in sorted(campaigns.items(), key=lambda x: -x[1])[:5]:
            msg += f"\n• {cname}: {ccount:,}"

    source_display = "📦 Turso" if last_source == 'turso' else "🌐 Real-time"
    msg += f"\n\n(Source: {source_display})"
    return msg


def generate_pretrade_branch_report(branch_id, period_tokens, find_branch_func,
                                    fetch_data_func, parse_month_func, get_date_range_func):
    """รายงาน pre trade รายสาขา แยกตามพนักงาน"""
    ds, de, label, is_daily = _resolve_pretrade_period(
        period_tokens, parse_month_func, get_date_range_func)
    if ds is None:
        return label

    branch = find_branch_func(branch_id)
    if not branch:
        return f"❌ ไม่พบสาขา: {branch_id}"

    branch_name = branch.get('branch_name', str(branch_id))
    display_name = branch_name.split(' : ', 2)[-1] if ' : ' in branch_name else branch_name
    api_branch_id = branch.get('branch_id', branch_id)

    data = fetch_all_pages(fetch_data_func, {
        'date_start': ds, 'date_end': de, 'sale_code': '',
        'customer_sign': '', 'session_id': '', 'branch_id': str(api_branch_id),
    }, page_size=5000)

    if not data or 'error' in data:
        return f"❌ ดึงข้อมูลไม่สำเร็จ: {(data or {}).get('error', 'ไม่ทราบสาเหตุ')}"

    items = data.get('data', [])
    st = _pretrade_stats(items)

    msg = "🎯 รายงาน Pre Trade\n"
    msg += f"📅 {label}\n"
    msg += f"🏪 {display_name}\n"
    msg += "━━━━━━━━━━━━\n\n"

    if st['count'] == 0:
        msg += "ไม่มีรายการ Pre Trade ในช่วงนี้\n"
        msg += f"\n(ตรวจแล้ว {st['total']:,} รายการทั้งหมด)"
        return msg

    pre_items = [it for it in items if is_pretrade(it)]

    by_sale = defaultdict(lambda: {'count': 0, 'amount': 0.0})
    for it in pre_items:
        key = str(it.get('SALE_NAME') or it.get('SALE_CODE') or 'ไม่ระบุ')
        by_sale[key]['count'] += 1
        try:
            by_sale[key]['amount'] += float(it.get('amount') or 0)
        except (TypeError, ValueError):
            pass

    for sale, v in sorted(by_sale.items(), key=lambda x: -x[1]['count'])[:20]:
        msg += f"👤 {sale}\n"
        msg += f"  • {v['count']} รายการ · {v['amount']:,.0f} บาท\n\n"

    pct = st['count'] / st['total'] * 100 if st['total'] else 0
    cpct = st['confirmed'] / st['count'] * 100 if st['count'] else 0
    msg += "━━━━━━━━━━━━\n"
    msg += "📈 สรุป\n"
    msg += f"• Pre Trade: {st['count']:,} รายการ ({pct:.0f}% ของ {st['total']:,})\n"
    msg += f"• ยอดประเมิน: {st['amount']:,.0f} บาท\n"
    msg += f"• ลูกค้าตกลง: {st['confirmed']:,} ({cpct:.0f}%)"

    if st['campaigns']:
        msg += "\n\n🏷️ แคมเปญ"
        for cname, ccount in sorted(st['campaigns'].items(), key=lambda x: -x[1])[:5]:
            msg += f"\n• {cname}: {ccount:,}"

    source_display = "📦 Turso" if data.get('source') == 'turso' else "🌐 Real-time"
    msg += f"\n\n(Source: {source_display})"
    return msg


def load_branches_map():
    """โหลด mapping ของ branch_id กับ branch_name (ดึงจาก DB ก่อน)"""
    branches_map = {}
    
    # 1. ลองดึงจาก DB (เหมือน load_supersale_config)
    try:
        import psycopg2
        import psycopg2.extras
        database_url = os.environ.get('POSTGRES_URL_NON_POOLING') or os.environ.get('DATABASE_URL')
        if database_url:
            conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
            cur = conn.cursor()
            cur.execute("SELECT branch_data FROM cached_branches ORDER BY updated_at DESC LIMIT 1")
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if row:
                data = row['branch_data']
                if isinstance(data, str):
                    import json
                    data = json.loads(data)
                if isinstance(data, list):
                    branches_map = {str(b.get('branch_id', '')): b.get('branch_name', '') for b in data if b.get('branch_id')}
                    return branches_map
    except Exception as e:
        print(f"⚠️ load_branches_map DB error: {e}")

    # 2. Fallback ไปที่ไฟล์เดิม
    branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
    try:
        if os.path.exists(branches_file):
            with open(branches_file, 'r', encoding='utf-8') as f:
                import json
                branches_data = json.load(f)
                branches_map = {str(b.get('branch_id', '')): b.get('branch_name', '') for b in branches_data if b.get('branch_id')}
    except Exception as e:
        print(f"Warning: Could not load branches data: {e}")
    
    return branches_map


def format_thai_date(date_obj):
    """แปลงวันที่เป็นรูปแบบภาษาไทย"""
    thai_months = [
        '', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
        'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
    ]
    
    day = date_obj.day
    month = thai_months[date_obj.month]
    year = date_obj.year + 543  # แปลงเป็น พ.ศ.
    
    return f"{day} {month} {year}"


def get_help_message():
    """แสดงวิธีใช้งาน LINE Bot"""
    message = "📖 วิธีใช้งาน LINE Bot\n"
    message += "━━━━━━━━━━━━━━━━━━\n\n"
    
    message += "🗺️ รายงาน Zone\n"
    message += "━━━━━━━━━━━━\n"
    message += "1️⃣ รายงานวันนี้:\n"
    message += "   รายงาน zone [ชื่อโซน]\n"
    message += "   ตัวอย่าง: รายงาน zone พี่โอ๊ค\n\n"
    
    message += "2️⃣ รายงานรายเดือน:\n"
    message += "   รายงาน [เดือน] zone [ชื่อโซน]\n"
    message += "   ตัวอย่าง: รายงาน พฤศจิกายน zone พี่โอ๊ค\n\n"
    
    message += "🏪 รายงานสาขา\n"
    message += "━━━━━━━━━━━━\n"
    message += "3️⃣ รายงานวันนี้ (แยกพนักงาน):\n"
    message += "   รายงาน [ID] รายวัน\n"
    message += "   ตัวอย่าง: รายงาน 9 รายวัน\n\n"
    
    message += "🎯 รายงาน Pre Trade:\n"
    message += "   รายงาน pretrade zone [ชื่อโซน]\n"
    message += "   รายงาน pretrade zone [ชื่อโซน] [เดือน]\n"
    message += "   รายงาน pretrade zone [ชื่อโซน] วันนี้\n"
    message += "   รายงาน pretrade [ID]\n"
    message += "   รายงาน pretrade [ID] [เดือน]\n"
    message += "   รายงาน pretrade [ID] วันนี้\n\n"
    message += "4️⃣ รายงานรายเดือน (แยกพนักงาน):\n"
    message += "   รายงาน [ID] [เดือน]\n"
    message += "   ตัวอย่าง: รายงาน 9 พฤศจิกายน\n\n"
    
    message += "📊 รายงาน Excel รายปี\n"
    message += "━━━━━━━━━━━━\n"
    message += "5️⃣ รายงานรายปี (ไฟล์ Excel):\n"
    message += "   รายงาน excel รายปี [ปี]\n"
    message += "   ตัวอย่าง: รายงาน excel รายปี 2024\n"
    message += "   ตัวอย่าง: รายงาน excel รายปี 2567\n\n"
    
    message += "6️⃣ รายงานรายปีของสาขา:\n"
    message += "   รายงาน excel รายปี [ปี] [ID]\n"
    message += "   ตัวอย่าง: รายงาน excel รายปี 2024 9\n\n"
    
    message += "📝 หมายเหตุ\n"
    message += "━━━━━━━━━━━━\n"
    message += "• ID = ตัวเลขจาก branch_name\n"
    message += "  (เช่น 9 จาก ID9, 13 จาก ID13)\n"
    message += "• เดือน: มกราคม, กุมภาพันธ์, มีนาคม,\n"
    message += "  เมษายน, พฤษภาคม, มิถุนายน,\n"
    message += "  กรกฎาคม, สิงหาคม, กันยายน,\n"
    message += "  ตุลาคม, พฤศจิกายน, ธันวาคม\n"
    message += "• ปี: รองรับทั้ง ค.ศ. (2024) และ พ.ศ. (2567)\n"
    message += "• รายงาน Excel จะส่งเป็นไฟล์พร้อมกราฟ\n\n"
    
    message += "💡 พิมพ์ 'วิธีใช้' เพื่อดูข้อความนี้อีกครั้ง"
    
    return message
