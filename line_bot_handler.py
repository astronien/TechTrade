# LINE Bot Message Handler
from datetime import datetime
from collections import defaultdict
import json
import os

def handle_line_message(user_message, fetch_data_func, load_zones_func, find_zone_func, find_branch_func, parse_month_func, get_date_range_func):
    """
    จัดการข้อความจาก LINE และส่งกลับ response message
    
    คำสั่งที่รองรับ:
    1. รายงาน zone [ชื่อโซน] - รายงานวันนี้ของ Zone
    2. รายงาน [เดือน] zone [ชื่อโซน] - รายงานทั้งเดือนของ Zone
    3. รายงาน [branch_id] รายวัน - รายงานวันนี้ของสาขา แยกตามพนักงาน
    4. รายงาน [branch_id] [เดือน] - รายงานทั้งเดือนของสาขา แยกตามพนักงาน
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
        return "❌ กรุณาระบุคำสั่ง\n\nตัวอย่าง:\n• รายงาน zone พี่โอ๊ค\n• รายงาน 9 รายวัน (สาขา ID9)\n• รายงาน 13 พฤศจิกายน (สาขา ID13)\n• รายงาน พฤศจิกายน zone พี่โอ๊ค"
    
    # แยกคำสั่ง
    parts = command.split()
    
    # ตรวจสอบรูปแบบคำสั่ง
    if 'zone' in parts:
        # คำสั่งเกี่ยวกับ Zone
        zone_index = parts.index('zone')
        
        if zone_index == 0:
            # รายงาน zone [ชื่อโซน] - วันนี้
            zone_name = ' '.join(parts[1:])
            return generate_zone_daily_report(zone_name, find_zone_func, fetch_data_func)
        else:
            # รายงาน [เดือน] zone [ชื่อโซน] - ทั้งเดือน
            month_name = ' '.join(parts[:zone_index])
            zone_name = ' '.join(parts[zone_index+1:])
            return generate_zone_monthly_report(zone_name, month_name, find_zone_func, fetch_data_func, parse_month_func, get_date_range_func)
    
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
        return "❌ คำสั่งไม่ถูกต้อง\n\nตัวอย่าง:\n• รายงาน zone พี่โอ๊ค\n• รายงาน 9 รายวัน (สาขา ID9)\n• รายงาน 13 พฤศจิกายน (สาขา ID13)\n• รายงาน พฤศจิกายน zone พี่โอ๊ค"


def generate_zone_daily_report(zone_name, find_zone_func, fetch_data_func):
    """สร้างรายงานวันนี้ของ Zone (แยกตามสาขา)"""
    zone = find_zone_func(zone_name)
    
    if not zone:
        zones = []  # ต้องดึงจาก load_zones_func
        return f"❌ ไม่พบ Zone: {zone_name}"
    
    today = datetime.now().strftime('%d/%m/%Y')
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
    
    for branch_id in branch_ids:
        filters = {
            'date_start': today,
            'date_end': today,
            'sale_code': '',
            'customer_sign': '',
            'session_id': '',
            'branch_id': str(branch_id)
        }
        
        data = fetch_data_func(start=0, length=1000, **filters)
        
        branch_name = branches_map.get(branch_id, f"สาขา {branch_id}")
        if ' : ' in branch_name:
            branch_name = branch_name.split(' : ', 2)[-1]
        
        if 'error' not in data:
            items = data.get('data', [])
            total_count = len(items)
            confirmed_count = sum(1 for item in items 
                                 if item.get('BIDDING_STATUS_NAME', '') in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา'])
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
    
    return message


def generate_branch_daily_report(branch_id_input, find_branch_func, fetch_data_func):
    """สร้างรายงานวันนี้ของสาขา (แยกตามพนักงาน)"""
    branch = find_branch_func(branch_id_input)
    
    if not branch:
        return f"❌ ไม่พบสาขา ID: {branch_id_input}\n\nตัวอย่าง: รายงาน 9 รายวัน (สำหรับสาขา ID9)"
    
    today = datetime.now().strftime('%d/%m/%Y')
    thai_date = format_thai_date(datetime.now())
    
    filters = {
        'date_start': today,
        'date_end': today,
        'sale_code': '',
        'customer_sign': '',
        'session_id': '',
        'branch_id': str(branch['branch_id'])
    }
    
    data = fetch_data_func(start=0, length=1000, **filters)
    
    if 'error' in data:
        return f"❌ ไม่สามารถดึงข้อมูลได้: {data.get('error')}"
    
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
        sale_code = item.get('SALE_CODE', '')
        if not sale_code:
            continue
        
        sale_name = item.get('SALE_NAME', '')
        status = item.get('BIDDING_STATUS_NAME', '')
        is_confirmed = status in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
        
        amount_value = item.get('amount')
        try:
            amount = float(amount_value) if amount_value else 0.0
        except:
            amount = 0.0
        
        sales_summary[sale_code]['name'] = sale_name
        sales_summary[sale_code]['count'] += 1
        sales_summary[sale_code]['amount'] += amount
        
        if is_confirmed:
            sales_summary[sale_code]['confirmed'] += 1
        else:
            sales_summary[sale_code]['not_confirmed'] += 1
    
    # สร้างข้อความ
    import re
    branch_name = branch['branch_name'].split(' : ', 2)[-1] if ' : ' in branch['branch_name'] else branch['branch_name']
    
    # ดึง ID number จาก branch_name (เช่น ID9 -> 9)
    id_match = re.search(r'ID(\d+)', branch['branch_name'])
    id_display = f"ID{id_match.group(1)}" if id_match else branch_id_input
    
    message = f"📊 รายงานรายวัน\n"
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
    
    return message


def generate_zone_monthly_report(zone_name, month_name, find_zone_func, fetch_data_func, parse_month_func, get_date_range_func):
    """สร้างรายงานทั้งเดือนของ Zone (แยกตามสาขา)"""
    zone = find_zone_func(zone_name)
    
    if not zone:
        return f"❌ ไม่พบ Zone: {zone_name}"
    
    month_number = parse_month_func(month_name)
    if not month_number:
        return f"❌ ไม่รู้จักเดือน: {month_name}\n\nตัวอย่าง: มกราคม, กุมภาพันธ์, มีนาคม"
    
    date_start, date_end = get_date_range_func(month_number)
    branch_ids = zone['branch_ids']
    year = datetime.now().year + 543  # แปลงเป็น พ.ศ.
    
    # โหลดข้อมูลสาขา
    branches_map = load_branches_map()
    
    message = f"📊 รายงานยอดเทรด\n"
    message += f"📅 เดือน: {month_name} {year}\n"
    message += f"🗺️ Zone: {zone['zone_name']}\n"
    message += f"🏢 จำนวนสาขา: {len(branch_ids)} สาขา\n"
    message += f"━━━━━━━━━━━━\n\n"
    
    total_all = 0
    confirmed_all = 0
    
    for branch_id in branch_ids:
        filters = {
            'date_start': date_start,
            'date_end': date_end,
            'sale_code': '',
            'customer_sign': '',
            'session_id': '',
            'branch_id': str(branch_id)
        }
        
        data = fetch_data_func(start=0, length=5000, **filters)
        
        branch_name = branches_map.get(branch_id, f"สาขา {branch_id}")
        if ' : ' in branch_name:
            branch_name = branch_name.split(' : ', 2)[-1]
        
        if 'error' not in data:
            items = data.get('data', [])
            total_count = len(items)
            confirmed_count = sum(1 for item in items 
                                 if item.get('BIDDING_STATUS_NAME', '') in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา'])
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
    
    filters = {
        'date_start': date_start,
        'date_end': date_end,
        'sale_code': '',
        'customer_sign': '',
        'session_id': '',
        'branch_id': str(branch['branch_id'])
    }
    
    data = fetch_data_func(start=0, length=5000, **filters)
    
    if 'error' in data:
        return f"❌ ไม่สามารถดึงข้อมูลได้: {data.get('error')}"
    
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
        sale_code = item.get('SALE_CODE', '')
        if not sale_code:
            continue
        
        sale_name = item.get('SALE_NAME', '')
        status = item.get('BIDDING_STATUS_NAME', '')
        is_confirmed = status in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
        
        amount_value = item.get('amount')
        try:
            amount = float(amount_value) if amount_value else 0.0
        except:
            amount = 0.0
        
        sales_summary[sale_code]['name'] = sale_name
        sales_summary[sale_code]['count'] += 1
        sales_summary[sale_code]['amount'] += amount
        
        if is_confirmed:
            sales_summary[sale_code]['confirmed'] += 1
        else:
            sales_summary[sale_code]['not_confirmed'] += 1
    
    # สร้างข้อความ
    import re
    branch_name = branch['branch_name'].split(' : ', 2)[-1] if ' : ' in branch['branch_name'] else branch['branch_name']
    year = datetime.now().year + 543  # แปลงเป็น พ.ศ.
    
    # ดึง ID number จาก branch_name (เช่น ID9 -> 9)
    id_match = re.search(r'ID(\d+)', branch['branch_name'])
    id_display = f"ID{id_match.group(1)}" if id_match else branch_id
    
    message = f"📊 รายงานรายเดือน\n"
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
    
    return message


def load_branches_map():
    """โหลด mapping ของ branch_id กับ branch_name"""
    branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
    branches_map = {}
    
    try:
        with open(branches_file, 'r', encoding='utf-8') as f:
            branches_data = json.load(f)
            branches_map = {b['branch_id']: b['branch_name'] for b in branches_data}
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
    
    message += "4️⃣ รายงานรายเดือน (แยกพนักงาน):\n"
    message += "   รายงาน [ID] [เดือน]\n"
    message += "   ตัวอย่าง: รายงาน 9 พฤศจิกายน\n\n"
    
    message += "📝 หมายเหตุ\n"
    message += "━━━━━━━━━━━━\n"
    message += "• ID = ตัวเลขจาก branch_name\n"
    message += "  (เช่น 9 จาก ID9, 13 จาก ID13)\n"
    message += "• เดือน: มกราคม, กุมภาพันธ์, มีนาคม,\n"
    message += "  เมษายน, พฤษภาคม, มิถุนายน,\n"
    message += "  กรกฎาคม, สิงหาคม, กันยายน,\n"
    message += "  ตุลาคม, พฤศจิกายน, ธันวาคม\n\n"
    
    message += "💡 พิมพ์ 'วิธีใช้' เพื่อดูข้อความนี้อีกครั้ง"
    
    return message
