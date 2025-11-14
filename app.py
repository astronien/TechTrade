from flask import Flask, render_template, jsonify, request
import requests
import json
from datetime import datetime, timedelta
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Supabase Database Connection
def get_db_connection():
    """สร้าง connection ไปยัง Supabase PostgreSQL"""
    try:
        conn = psycopg2.connect(
            os.environ.get('POSTGRES_URL_NON_POOLING'),
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

# สร้างตาราง zones ถ้ายังไม่มี
def init_database():
    """สร้างตาราง zones ใน database"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_zones (
                id SERIAL PRIMARY KEY,
                zone_id VARCHAR(255) UNIQUE NOT NULL,
                zone_name VARCHAR(255) NOT NULL,
                branch_ids JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database initialized")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        if conn:
            conn.close()
        return False

# เรียก init เมื่อ start app
init_database()

# API Configuration
API_URL = "https://eve.techswop.com/ti/index.aspx/Getdata"
BRANCH_ID = "231"  # สาขาเดิมที่ใช้ได้

def get_datatables_payload(start=0, length=50, date_start=None, date_end=None, 
                          sale_code="", status="", brands=None, series="", 
                          doc_ref_number="", promo_code="", customer_sign="0", branch_id=None):
    """สร้าง DataTables payload"""
    
    # ถ้าไม่ระบุวันที่ ใช้วันนี้
    if not date_end:
        date_end = datetime.now().strftime("%d/%m/%Y")
    if not date_start:
        date_start = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    
    if brands is None:
        brands = []
    
    # ใช้ branch_id ที่ส่งมา หรือใช้ค่า default
    if branch_id is None:
        branch_id = BRANCH_ID
    
    columns = [
        {"data": "document_no", "name": "document_no", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "IS_SIGNED", "name": "IS_SIGNED", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "SIGN_DATE", "name": "SIGN_DATE", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "document_date", "name": "document_date", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "series", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "category_name", "name": "category_name", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "brand_name", "name": "brand_name", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "part_number", "name": "part_number", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "amount", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "COUPON_TRADE_IN_CODE", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "invoice_no", "name": "invoice_no", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "CAMPAIGN_ON_TOP_NAME", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "COUPON_ON_TOP_BRAND_CODE", "name": "COUPON_ON_TOP_BRAND_CODE", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "COUPON_ON_TOP_BRAND_PRICE", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "COUPON_ON_TOP_COMPANY_CODE", "name": "COUPON_ON_TOP_COMPANY_CODE", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "COUPON_ON_TOP_COMPANY_PRICE", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "customer_name", "name": "customer_name", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "customer_phone_number", "name": "customer_phone_number", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "customer_email", "name": "customer_email", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "buyer_name", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "SALE_CODE", "name": "SALE_CODE", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "SALE_NAME", "name": "SALE_NAME", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "DOCUMENT_REF_1", "name": "DOCUMENT_REF_1", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "BIDDING_STATUS_NAME", "name": "BIDDING_STATUS_NAME", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "CHANGE_REQUEST_COUNT", "name": "CHANGE_REQUEST_COUNT", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "trade_in_id", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}}
    ]
    
    return {
        "draw": 1,
        "columns": columns,
        "order": [],
        "start": start,
        "length": length,
        "search": {"value": "", "regex": False, "fixed": []},
        "textfield": "",
        "textSearch": "",
        "textdateStart": date_start,
        "textdateEnd": date_end,
        "status": status,
        "series": [series] if series else [],
        "brands": brands if brands else [],
        "saleCode": sale_code,
        "branchID": branch_id,
        "txtSearchRef1": doc_ref_number,
        "txtSearchCOTN": promo_code,
        "DocumentRef1": "",
        "customerSign": customer_sign
    }

def fetch_data_from_api(start=0, length=50, **filters):
    """ดึงข้อมูลจาก API"""
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
    }
    
    # เตรียม cookies ถ้ามี session_id
    cookies = {}
    session_id = filters.pop('session_id', '')  # ใช้ pop เพื่อเอาออกจาก filters
    if session_id:
        cookies['ASP.NET_SessionId'] = session_id
        print(f"🔐 Using Session ID: {session_id[:10]}...")
    
    # ดึง branch_id ออกจาก filters
    branch_id = filters.pop('branch_id', BRANCH_ID)
    
    payload = get_datatables_payload(start, length, branch_id=branch_id, **filters)
    
    # Debug: แสดง payload ที่ส่งไป
    print(f"📤 Sending to API:")
    print(f"   Date: {filters.get('date_start')} to {filters.get('date_end')}")
    print(f"   Branch ID: {branch_id}")
    print(f"   Sale Code: {filters.get('sale_code', 'N/A')}")
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, cookies=cookies)
        response.raise_for_status()
        result = response.json()
        
        # Debug: แสดง response
        print(f"📥 API Response:")
        if 'd' in result:
            data_obj = result['d']
            print(f"   Records Total: {data_obj.get('recordsTotal', 0)}")
            print(f"   Records Filtered: {data_obj.get('recordsFiltered', 0)}")
            print(f"   Data items: {len(data_obj.get('data', []))}")
            
            return {
                'data': data_obj.get('data', []),
                'recordsTotal': data_obj.get('recordsTotal', 0),
                'recordsFiltered': data_obj.get('recordsFiltered', 0)
            }
        else:
            print(f"   Unexpected format: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {str(e)}")
        return {"error": str(e)}

@app.route('/')
def index():
    """หน้าแรกแสดงข้อมูล"""
    return render_template('index.html')

@app.route('/install-extension')
def install_extension():
    """หน้าติดตั้ง Extension"""
    return render_template('install-extension.html')

@app.route('/download-extension')
def download_extension():
    """ดาวน์โหลดโฟลเดอร์ Extension เป็น ZIP"""
    import zipfile
    import io
    from flask import send_file
    
    # สร้าง ZIP file ในหน่วยความจำ
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        import os
        extension_dir = 'extension'
        for root, dirs, files in os.walk(extension_dir):
            for file in files:
                if not file.endswith('.py'):  # ไม่รวมไฟล์ Python
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extension_dir)
                    zf.write(file_path, arcname)
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='trade-in-extension.zip'
    )

@app.route('/api/data')
def get_data():
    """API endpoint สำหรับดึงข้อมูล"""
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 1000, type=int)  # เพิ่มเป็น 1000
    session_id = request.args.get('sessionId', '')  # รับ Session ID จาก client
    
    # รับพารามิเตอร์จากฟอร์ม
    filters = {
        'date_start': request.args.get('dateStart', ''),
        'date_end': request.args.get('dateEnd', ''),
        'sale_code': request.args.get('saleCode', ''),
        'status': request.args.get('status', ''),
        'brands': [request.args.get('brand')] if request.args.get('brand') else [],
        'series': request.args.get('series', ''),
        'doc_ref_number': request.args.get('docRefNumber', ''),
        'promo_code': request.args.get('promoCode', ''),
        'customer_sign': request.args.get('customerSign', '0'),
        'branch_id': request.args.get('branchId', BRANCH_ID),
        'session_id': session_id
    }
    
    # ดึงข้อมูลทั้งหมดถ้าจำนวนมากกว่า length
    data = fetch_data_from_api(start, length, **filters)
    
    print(f"🔍 Search - Date: {filters['date_start']} to {filters['date_end']}")
    
    # ตรวจสอบว่ามีข้อมูลเพิ่มหรือไม่
    if 'recordsTotal' in data and 'recordsFiltered' in data:
        total = data['recordsFiltered']
        current = len(data.get('data', []))
        
        print(f"📊 First batch: {current} items, Total available: {total}")
        
        # ถ้ายังไม่ครบ ดึงเพิ่ม
        if current < total and current == length:
            all_data = data.get('data', [])
            next_start = start + length
            
            print(f"⏳ Fetching more data...")
            
            while len(all_data) < total:
                next_batch = fetch_data_from_api(next_start, length, **filters)
                batch_data = next_batch.get('data', [])
                
                if not batch_data:
                    break
                    
                all_data.extend(batch_data)
                print(f"   + Fetched {len(batch_data)} more items (total: {len(all_data)})")
                next_start += length
                
                # ป้องกัน infinite loop
                if len(all_data) >= total or len(batch_data) < length:
                    break
            
            data['data'] = all_data
            print(f"✅ Final result: {len(all_data)} items")
        else:
            print(f"✅ Got all data in first batch: {current} items")
    
    return jsonify(data)

@app.route('/api/report')
def get_report():
    """API endpoint สำหรับสร้างรายงาน"""
    from collections import defaultdict
    
    # รับพารามิเตอร์
    session_id = request.args.get('sessionId', '')
    filters = {
        'date_start': request.args.get('dateStart', ''),
        'date_end': request.args.get('dateEnd', ''),
        'sale_code': request.args.get('saleCode', ''),
        'customer_sign': request.args.get('customerSign', ''),  # เพิ่ม customerSign
        'branch_id': request.args.get('branchId', BRANCH_ID),
        'session_id': session_id
    }
    
    # ดึงข้อมูลทั้งหมดแบบ pagination (จำกัดเวลาสำหรับ Vercel)
    import time
    start_time = time.time()
    max_time = 8  # จำกัด 8 วินาที (เหลือเวลา 2 วินาทีสำหรับ process)
    
    length = 1000
    start = 0
    all_items = []
    
    while True:
        # ตรวจสอบเวลา
        if time.time() - start_time > max_time:
            print(f"⚠️ Timeout protection: stopped at {len(all_items)} items")
            break
            
        data = fetch_data_from_api(start=start, length=length, **filters)
        
        if 'error' in data:
            return jsonify(data)
        
        batch_data = data.get('data', [])
        if not batch_data:
            break
        
        all_items.extend(batch_data)
        
        # ตรวจสอบว่าดึงครบหรือยัง
        total = data.get('recordsFiltered', 0)
        if len(all_items) >= total or len(batch_data) < length:
            break
        
        start += length
        
        # ป้องกัน infinite loop (สูงสุด 10,000 รายการ)
        if len(all_items) >= 10000:
            break
    
    print(f"Debug - Total items fetched: {len(all_items)}")
    
    if not all_items:
        return jsonify({'error': 'ไม่พบข้อมูล'})
    
    # วิเคราะห์ข้อมูล
    items = all_items
    
    # สรุปข้อมูล
    total_count = len(items)
    confirmed_count = 0
    cancelled_count = 0
    not_confirmed_count = 0
    total_amount = 0.0
    confirmed_amount = 0.0
    
    status_summary = {}
    brand_summary = {}
    daily_summary = defaultdict(lambda: {'count': 0, 'confirmedCount': 0, 'totalAmount': 0.0, 'confirmedAmount': 0.0})
    sales_summary = defaultdict(lambda: {'name': '', 'count': 0, 'confirmedCount': 0, 'totalAmount': 0.0, 'confirmedAmount': 0.0})
    
    for item in items:
        # นับตามสถานะ
        status = item.get('BIDDING_STATUS_NAME', 'ไม่ระบุ')
        if status not in status_summary:
            status_summary[status] = {'count': 0, 'amount': 0.0}
        status_summary[status]['count'] += 1
        
        # คำนวณมูลค่า - รองรับทั้ง null, empty string, และ 0
        amount_value = item.get('amount')
        if amount_value is None or amount_value == '' or amount_value == 'null':
            amount = 0.0
        else:
            try:
                amount = float(amount_value)
            except (ValueError, TypeError):
                amount = 0.0
        
        status_summary[status]['amount'] += amount
        total_amount += amount
        
        # นับตามแบรนด์
        brand = item.get('brand_name', 'ไม่ระบุ')
        if brand not in brand_summary:
            brand_summary[brand] = {'count': 0, 'amount': 0.0}
        brand_summary[brand]['count'] += 1
        brand_summary[brand]['amount'] += amount
        
        # ตรวจสอบว่าเป็นสถานะที่ลูกค้าตกลงหรือไม่
        is_confirmed = status in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
        
        # สรุปตามวัน
        doc_date = item.get('document_date', '')
        if doc_date:
            daily_summary[doc_date]['count'] += 1
            daily_summary[doc_date]['totalAmount'] += amount
            if is_confirmed:
                daily_summary[doc_date]['confirmedCount'] += 1
                daily_summary[doc_date]['confirmedAmount'] += amount
        
        # สรุปตามพนักงานขาย
        sale_code = item.get('SALE_CODE', '')
        sale_name = item.get('SALE_NAME', '')
        if sale_code:
            sales_summary[sale_code]['name'] = sale_name
            sales_summary[sale_code]['count'] += 1
            sales_summary[sale_code]['totalAmount'] += amount
            if is_confirmed:
                sales_summary[sale_code]['confirmedCount'] += 1
                sales_summary[sale_code]['confirmedAmount'] += amount
        
        # นับสถานะพิเศษ
        if is_confirmed:
            confirmed_count += 1
            confirmed_amount += amount
        else:
            not_confirmed_count += 1
        
        if status == 'ยกเลิกรายการ':
            cancelled_count += 1
    
    # Debug: แสดงสถานะที่พบ
    print(f"Debug - Total items: {total_count}")
    print(f"Debug - Confirmed count: {confirmed_count}")
    print(f"Debug - Not confirmed count: {not_confirmed_count}")
    print(f"Debug - Status summary: {status_summary}")
    
    # เรียงลำดับ
    status_summary = dict(sorted(status_summary.items(), key=lambda x: x[1]['count'], reverse=True))
    brand_summary = dict(sorted(brand_summary.items(), key=lambda x: x[1]['count'], reverse=True))
    daily_summary = dict(sorted(daily_summary.items(), reverse=True))  # เรียงวันที่ล่าสุดก่อน
    sales_summary = dict(sorted(sales_summary.items(), key=lambda x: x[1]['totalAmount'], reverse=True))  # เรียงตามยอดเทรด
    
    report = {
        'totalCount': total_count,
        'confirmedCount': confirmed_count,
        'notConfirmedCount': not_confirmed_count,
        'cancelledCount': cancelled_count,
        'totalAmount': total_amount,
        'confirmedAmount': confirmed_amount,
        'statusSummary': status_summary,
        'brandSummary': brand_summary,
        'dailySummary': daily_summary,
        'salesSummary': sales_summary
    }
    
    return jsonify({
        'report': report,
        'details': items
    })



@app.route('/api/check-cancel', methods=['POST'])
def check_cancel():
    """API endpoint สำหรับตรวจสอบว่ายกเลิกได้หรือไม่"""
    data = request.get_json()
    trade_in_id = data.get('tradeInId', '')
    cookies = data.get('cookies', {})
    
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
    }
    
    try:
        response = requests.post(
            'https://eve.techswop.com/ti/index.aspx/CheckAllowCancel',
            headers=headers,
            json={"trade_in_id": int(trade_in_id)},
            cookies=cookies
        )
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'d': {'is_success': False, 'message': [f'HTTP {response.status_code}']}})
    except Exception as e:
        return jsonify({'d': {'is_success': False, 'message': [str(e)]}})

@app.route('/api/cancel-data', methods=['POST'])
def cancel_data():
    """API endpoint สำหรับยกเลิกรายการ"""
    data = request.get_json()
    payload = data.get('payload', {})
    cookies = data.get('cookies', {})
    
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
    }
    
    try:
        response = requests.post(
            'https://eve.techswop.com/ti/index.aspx/CancelData',
            headers=headers,
            json=payload,
            cookies=cookies
        )
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'d': {'is_success': False, 'message': [f'HTTP {response.status_code}']}})
    except Exception as e:
        return jsonify({'d': {'is_success': False, 'message': [str(e)]}})

@app.route('/api/get-cookies', methods=['GET'])
def get_cookies():
    """API endpoint สำหรับดึง cookies จาก browser"""
    # รับ cookies จาก request header
    cookie_header = request.headers.get('Cookie', '')
    cookies = {}
    
    if cookie_header:
        for item in cookie_header.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                cookies[key] = value
    
    return jsonify({'cookies': cookies})

@app.route('/api/auto-get-session', methods=['POST'])
def auto_get_session():
    """API endpoint สำหรับดึง Session ID จาก eve.techswop.com อัตโนมัติ"""
    try:
        # ใช้ requests session เพื่อจำลองการเข้าถึง
        session = requests.Session()
        
        # ส่ง request ไปที่หน้า login
        response = session.get('https://eve.techswop.com/TI/login.aspx')
        
        # ดึง Session ID จาก cookies
        session_id = session.cookies.get('ASP.NET_SessionId')
        
        if session_id:
            return jsonify({
                'success': True,
                'sessionId': session_id,
                'message': 'ดึง Session ID สำเร็จ'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'ไม่พบ Session ID - กรุณา login ที่ eve.techswop.com ก่อน'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'เกิดข้อผิดพลาด: {str(e)}'
        })

@app.route('/api/send-telegram', methods=['POST'])
def send_telegram():
    """API endpoint สำหรับส่งรายงานไป Telegram"""
    data = request.get_json()
    bot_token = data.get('botToken', '')
    chat_id = data.get('chatId', '')
    message = data.get('message', '')
    
    if not bot_token or not chat_id or not message:
        return jsonify({
            'success': False,
            'error': 'กรุณาระบุ Bot Token, Chat ID และข้อความ'
        })
    
    try:
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload)
        result = response.json()
        
        if result.get('ok'):
            return jsonify({
                'success': True,
                'message': 'ส่งรายงานไป Telegram สำเร็จ!'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('description', 'ส่งไม่สำเร็จ')
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'เกิดข้อผิดพลาด: {str(e)}'
        })

# โหลด custom zones จาก Supabase
def load_custom_zones_from_file():
    """โหลด custom zones จาก Supabase PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT zone_id, zone_name, branch_ids FROM custom_zones ORDER BY created_at")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        zones = []
        for row in rows:
            zones.append({
                'zone_id': row['zone_id'],
                'zone_name': row['zone_name'],
                'branch_ids': row['branch_ids']
            })
        
        print(f"✅ โหลด {len(zones)} custom zones จาก database")
        return zones
    except Exception as e:
        print(f"❌ Error loading custom zones: {e}")
        if conn:
            conn.close()
        return []

# บันทึก custom zones ลง Supabase
def save_custom_zones_to_file(custom_zones):
    """บันทึก custom zones ลง Supabase PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # ลบ zones เดิมทั้งหมด
        cur.execute("DELETE FROM custom_zones")
        
        # เพิ่ม zones ใหม่
        for zone in custom_zones:
            cur.execute("""
                INSERT INTO custom_zones (zone_id, zone_name, branch_ids)
                VALUES (%s, %s, %s)
                ON CONFLICT (zone_id) 
                DO UPDATE SET 
                    zone_name = EXCLUDED.zone_name,
                    branch_ids = EXCLUDED.branch_ids,
                    updated_at = CURRENT_TIMESTAMP
            """, (zone['zone_id'], zone['zone_name'], json.dumps(zone['branch_ids'])))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ บันทึก {len(custom_zones)} custom zones ลง database")
        return True
    except Exception as e:
        print(f"❌ Error saving custom zones: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

# โหลด Zones data
def load_zones_data():
    """โหลดข้อมูล Zones (รวม custom zones ที่ผู้ใช้สร้าง)"""
    # ค่า default zones
    default_zones = [
        {
            "zone_id": "ZONE_BKK_CENTRAL",
            "zone_name": "กรุงเทพ - ใจกลางเมือง",
            "branch_ids": [1, 2, 3, 8, 9, 12, 19, 22]
        },
        {
            "zone_id": "ZONE_BKK_EAST",
            "zone_name": "กรุงเทพ - ฝั่งตะวันออก",
            "branch_ids": [9, 18]
        },
        {
            "zone_id": "ZONE_BKK_WEST",
            "zone_name": "กรุงเทพ - ฝั่งตะวันตก",
            "branch_ids": [16, 17, 23]
        },
        {
            "zone_id": "ZONE_BKK_NORTH",
            "zone_name": "กรุงเทพ - ฝั่งเหนือ/ปริมณฑล",
            "branch_ids": [1, 3, 6, 12, 20, 22]
        },
        {
            "zone_id": "ZONE_EAST",
            "zone_name": "ภาคตะวันออก",
            "branch_ids": [4, 5, 11, 25]
        },
        {
            "zone_id": "ZONE_CENTRAL",
            "zone_name": "ภาคกลาง",
            "branch_ids": [7]
        },
        {
            "zone_id": "ZONE_SOUTH",
            "zone_name": "ภาคใต้",
            "branch_ids": [10]
        },
        {
            "zone_id": "ZONE_NORTHEAST",
            "zone_name": "ภาคตะวันออกเฉียงเหนือ",
            "branch_ids": [14, 15]
        }
    ]
    
    # รวมกับ custom zones จากไฟล์
    custom_zones = load_custom_zones_from_file()
    all_zones = default_zones + custom_zones
    
    return all_zones

def find_zone_by_name(zone_name):
    """ค้นหา Zone จากชื่อ (รองรับการค้นหาแบบไม่ตรงทั้งหมด)"""
    zones = load_zones_data()
    zone_name_lower = zone_name.lower()
    
    for zone in zones:
        if zone_name_lower in zone['zone_name'].lower():
            return zone
    
    return None

@app.route('/webhook/line', methods=['POST'])
def line_webhook():
    """Webhook สำหรับรับข้อความจาก LINE"""
    try:
        body = request.get_json()
        events = body.get('events', [])
        
        for event in events:
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                user_message = event['message']['text']
                
                # ตรวจสอบว่าเป็นกลุ่มหรือไม่
                source_type = event['source']['type']
                
                # ทำให้ข้อความเป็นตัวพิมพ์เล็กและตัดช่องว่าง
                clean_message = user_message.strip()
                
                # ถ้าเป็นกลุ่ม ต้องขึ้นต้นด้วย "รายงาน"
                if source_type == 'group':
                    if not clean_message.startswith('รายงาน'):
                        continue  # ไม่ตอบข้อความอื่นๆ ในกลุ่ม
                
                # ตรวจสอบคำสั่ง
                if clean_message.startswith('รายงาน'):
                    from datetime import datetime
                    from collections import defaultdict
                    
                    today = datetime.now().strftime('%d/%m/%Y')
                    
                    # แยกคำสั่ง
                    parts = clean_message.split(maxsplit=1)
                    zone_name = parts[1] if len(parts) > 1 else None
                    
                    # ถ้าระบุ Zone
                    if zone_name:
                        zone = find_zone_by_name(zone_name)
                        
                        if not zone:
                            reply_line_message(reply_token, f"❌ ไม่พบ Zone: {zone_name}\n\nZone ที่มี:\n" + 
                                             "\n".join([f"• {z['zone_name']}" for z in load_zones_data()]))
                            continue
                        
                        # โหลดข้อมูลสาขาทั้งหมด
                        import os
                        branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
                        branches_map = {}
                        
                        try:
                            with open(branches_file, 'r', encoding='utf-8') as f:
                                branches_data = json.load(f)
                                branches_map = {b['branch_id']: b['branch_name'] for b in branches_data}
                        except Exception as e:
                            print(f"Warning: Could not load branches data: {e}")
                        
                        # สร้างรายงานแยกตามสาขาใน Zone
                        branch_ids = zone['branch_ids']
                        
                        message = f"📊 รายงานยอดเทรด\n"
                        message += f"📅 วันที่: {today}\n"
                        message += f"🗺️ Zone: {zone['zone_name']}\n"
                        message += f"🏢 จำนวนสาขา: {len(branch_ids)} สาขา\n"
                        message += f"━━━━━━━━━━━━\n\n"
                        
                        total_all = 0
                        confirmed_all = 0
                        not_confirmed_all = 0
                        
                        # ดึงข้อมูลแต่ละสาขา
                        for branch_id in branch_ids:
                            filters = {
                                'date_start': today,
                                'date_end': today,
                                'sale_code': '',
                                'customer_sign': '',
                                'session_id': '',
                                'branch_id': str(branch_id)
                            }
                            
                            data = fetch_data_from_api(start=0, length=1000, **filters)
                            
                            # ดึงชื่อสาขา
                            branch_name = branches_map.get(branch_id, f"สาขา {branch_id}")
                            # ตัดเอาเฉพาะส่วนแรก (รหัสสาขา : ID : ชื่อ)
                            if ' : ' in branch_name:
                                branch_name = branch_name.split(' : ', 2)[-1]  # เอาส่วนชื่อสาขา
                            
                            if 'error' not in data:
                                items = data.get('data', [])
                                total_count = len(items)
                                confirmed_count = sum(1 for item in items 
                                                     if item.get('BIDDING_STATUS_NAME', '') in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา'])
                                not_confirmed_count = total_count - confirmed_count
                                
                                total_all += total_count
                                confirmed_all += confirmed_count
                                not_confirmed_all += not_confirmed_count
                            else:
                                # ถ้า error ให้ตั้งค่าเป็น 0
                                total_count = 0
                                confirmed_count = 0
                                not_confirmed_count = 0
                            
                            # แสดงทุกสาขา (รวมสาขาที่ยอด 0)
                            message += f"🏪 {branch_name}\n"
                            message += f"  • ทั้งหมด: {total_count} รายการ\n"
                            message += f"  • ตกลง: ✅{confirmed_count} ❌{not_confirmed_count}\n\n"
                        
                        # สรุปรวม
                        message += f"━━━━━━━━━━━━\n"
                        message += f"📈 สรุปรวมทั้ง Zone\n"
                        message += f"• รายการทั้งหมด: {total_all} รายการ\n"
                        message += f"• ลูกค้าตกลง: {confirmed_all} รายการ\n"
                        message += f"• ลูกค้าไม่ตกลง: {not_confirmed_all} รายการ\n"
                        
                        reply_line_message(reply_token, message)
                    
                    else:
                        # รายงานสาขาเดียว (แบบเดิม)
                        global BRANCH_ID
                        branch_id = BRANCH_ID
                        
                        filters = {
                            'date_start': today,
                            'date_end': today,
                            'sale_code': '',
                            'customer_sign': '',
                            'session_id': '',
                            'branch_id': branch_id
                        }
                        
                        data = fetch_data_from_api(start=0, length=1000, **filters)
                        
                        if 'error' not in data:
                            all_items = data.get('data', [])
                        else:
                            all_items = []
                        
                        # วิเคราะห์ข้อมูล
                        total_count = len(all_items)
                        confirmed_count = 0
                        not_confirmed_count = 0
                        sales_summary = defaultdict(lambda: {'count': 0, 'confirmedCount': 0})
                        
                        for item in all_items:
                            status = item.get('BIDDING_STATUS_NAME', '')
                            is_confirmed = status in ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
                            
                            if is_confirmed:
                                confirmed_count += 1
                            else:
                                not_confirmed_count += 1
                            
                            # สรุปตามพนักงาน
                            sale_code = item.get('SALE_CODE', '')
                            if sale_code:
                                sales_summary[sale_code]['count'] += 1
                                if is_confirmed:
                                    sales_summary[sale_code]['confirmedCount'] += 1
                        
                        # สร้างข้อความรายงาน
                        message = f"📊 รายงานยอดเทรด\n"
                        message += f"📅 วันที่: {today}\n"
                        message += f"🏢 สาขา: {branch_id}\n"
                        message += f"━━━━━━━━━━━━\n\n"
                        message += f"📈 สรุปภาพรวม\n"
                        message += f"• รายการทั้งหมด: {total_count} รายการ\n"
                        message += f"• ลูกค้าตกลง: {confirmed_count} รายการ\n"
                        message += f"• ลูกค้าไม่ตกลง: {not_confirmed_count} รายการ\n\n"
                        
                        if sales_summary:
                            message += f"👤 สรุปตามพนักงาน\n"
                            sorted_sales = sorted(sales_summary.items(), key=lambda x: x[1]['count'], reverse=True)
                            for sale_code, info in sorted_sales[:10]:
                                confirmed = info['confirmedCount']
                                total = info['count']
                                not_confirmed = total - confirmed
                                message += f"{sale_code}: {total} รายการ (✅{confirmed} ❌{not_confirmed})\n"
                        
                        message += f"━━━━━━━━━━━━"
                        
                        reply_line_message(reply_token, message)
                
                else:
                    # ไม่ตอบข้อความอื่นๆ
                    pass
        
        return jsonify({'status': 'ok'})
    
    except Exception as e:
        print(f"LINE Webhook Error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def reply_line_message(reply_token, message):
    """ส่ง Reply Message ไปยัง LINE"""
    import os
    channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
    
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {channel_access_token}'
    }
    payload = {
        'replyToken': reply_token,
        'messages': [
            {
                'type': 'text',
                'text': message
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending LINE message: {str(e)}")
        return None

@app.route('/api/send-line', methods=['POST'])
def send_line():
    """API endpoint สำหรับส่งรายงานไป LINE (Push Message)"""
    data = request.get_json()
    channel_access_token = data.get('channelAccessToken', '')
    user_id = data.get('userId', '')
    message = data.get('message', '')
    
    if not channel_access_token or not user_id or not message:
        return jsonify({
            'success': False,
            'error': 'กรุณาระบุ Channel Access Token, User ID และข้อความ'
        })
    
    try:
        url = 'https://api.line.me/v2/bot/message/push'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {channel_access_token}'
        }
        payload = {
            'to': user_id,
            'messages': [
                {
                    'type': 'text',
                    'text': message
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'ส่งรายงานไป LINE สำเร็จ!'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'HTTP {response.status_code}: {response.text}'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'เกิดข้อผิดพลาด: {str(e)}'
        })

# API endpoint /api/branches ถูกลบออกแล้ว
# เนื่องจากใช้ข้อมูล hardcode ใน static/branches.js แทน

@app.route('/api/cancel', methods=['POST'])
def cancel_orders():
    """API endpoint สำหรับยกเลิกรายการ"""
    data = request.get_json()
    trade_in_ids = data.get('tradeInIds', [])
    cancel_info = data.get('cancelInfo', {})
    
    if not trade_in_ids:
        return jsonify({'success': False, 'error': 'ไม่มีรายการที่ต้องการยกเลิก'})
    
    # ข้อมูลพนักงานและเหตุผลการยกเลิก
    emp_code = cancel_info.get('empCode', '')
    emp_name = cancel_info.get('empName', '')
    emp_phone = cancel_info.get('empPhone', '')
    reason = cancel_info.get('reason', 'ยกเลิกจากระบบ')
    reason_cancel = cancel_info.get('reasonCancel', '3')  # 1=ลูกค้าเปลี่ยนใจ, 2=ราคาไม่ตรง, 3=อื่นๆ
    cancel_type = cancel_info.get('cancelType', '1')  # 1=โดนยกเลิกจากผู้ขาย, 2=อื่นๆ
    description = cancel_info.get('description', '-')
    
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
    }
    
    success_count = 0
    failed_count = 0
    errors = []
    
    for trade_in_id in trade_in_ids:
        try:
            # เรียก API CheckAllowCancel ก่อน
            check_payload = {"trade_in_id": int(trade_in_id)}
            check_response = requests.post(
                'https://eve.techswop.com/ti/index.aspx/CheckAllowCancel',
                headers=headers,
                json=check_payload
            )
            
            if check_response.status_code == 200:
                check_result = check_response.json()
                
                # ตรวจสอบว่าสามารถยกเลิกได้หรือไม่
                can_cancel = False
                print(f"Check result for {trade_in_id}: {check_result}")
                
                if 'd' in check_result:
                    result_data = check_result['d']
                    print(f"Result data: {result_data}")
                    
                    # ตรวจสอบ is_success หรือ allow_cancel หรือ success
                    can_cancel = (result_data.get('is_success', False) or 
                                 result_data.get('allow_cancel', False) or 
                                 result_data.get('success', False))
                    
                    if not can_cancel:
                        failed_count += 1
                        error_msg = result_data.get('message', 'ไม่สามารถยกเลิกได้')
                        if isinstance(error_msg, list):
                            error_msg = ', '.join(error_msg) if error_msg else 'ไม่สามารถยกเลิกได้'
                        errors.append(f"ID {trade_in_id}: {error_msg}")
                        print(f"Cannot cancel: {error_msg}")
                        continue
                else:
                    can_cancel = True
                    print(f"No 'd' key, assuming can cancel")
                
                # ถ้าตรวจสอบผ่าน ให้ยกเลิกจริง
                if can_cancel:
                    cancel_payload = {
                        "param": {
                            "TRADE_IN_ID": str(trade_in_id),
                            "EMP_CODE": emp_code,
                            "EMP_FULL_NAME": emp_name,
                            "EMP_PHONE_NUMBER": emp_phone,
                            "REASON": reason,
                            "CANCEL_STATUS": cancel_type,
                            "REASON_CANCEL": reason_cancel,
                            "DESCRIPTION": description
                        }
                    }
                    
                    print(f"Cancel payload: {cancel_payload}")
                    
                    cancel_response = requests.post(
                        'https://eve.techswop.com/ti/index.aspx/CancelData',
                        headers=headers,
                        json=cancel_payload
                    )
                    
                    print(f"Cancel response status: {cancel_response.status_code}")
                    print(f"Cancel response: {cancel_response.text[:500]}")
                    
                    if cancel_response.status_code == 200:
                        cancel_result = cancel_response.json()
                        print(f"Cancel result: {cancel_result}")
                        
                        if 'd' in cancel_result:
                            result_data = cancel_result['d']
                            # ตรวจสอบ is_success หรือ success
                            is_success = (result_data.get('is_success', False) or 
                                        result_data.get('success', False))
                            
                            if is_success:
                                success_count += 1
                                print(f"Successfully cancelled {trade_in_id}")
                            else:
                                failed_count += 1
                                error_msg = result_data.get('message', 'ยกเลิกไม่สำเร็จ')
                                if isinstance(error_msg, list):
                                    error_msg = ', '.join(error_msg) if error_msg else 'ยกเลิกไม่สำเร็จ'
                                errors.append(f"ID {trade_in_id}: {error_msg}")
                                print(f"Cancel failed: {error_msg}")
                        else:
                            success_count += 1
                            print(f"No 'd' key, assuming success")
                    else:
                        failed_count += 1
                        errors.append(f"ID {trade_in_id}: HTTP {cancel_response.status_code}")
                        print(f"HTTP error: {cancel_response.status_code}")
            else:
                failed_count += 1
                errors.append(f"ID {trade_in_id}: ตรวจสอบไม่สำเร็จ HTTP {check_response.status_code}")
        except Exception as e:
            print(f"Error canceling {trade_in_id}: {str(e)}")
            failed_count += 1
            errors.append(f"ID {trade_in_id}: {str(e)}")
    
    if failed_count > 0 and success_count == 0:
        return jsonify({
            'success': False,
            'successCount': success_count,
            'failedCount': failed_count,
            'error': f'ยกเลิกล้มเหลวทั้งหมด {failed_count} รายการ',
            'errors': errors
        })
    
    return jsonify({
        'success': True,
        'successCount': success_count,
        'failedCount': failed_count,
        'message': f'ยกเลิกสำเร็จ {success_count} รายการ' + (f', ล้มเหลว {failed_count} รายการ' if failed_count > 0 else ''),
        'errors': errors if failed_count > 0 else []
    })

@app.route('/api/zones', methods=['GET'])
def get_zones():
    """API endpoint สำหรับดึงรายการ Zones ทั้งหมด"""
    zones = load_zones_data()
    return jsonify({
        'success': True,
        'zones': zones
    })

@app.route('/api/zones', methods=['POST'])
def save_zones():
    """API endpoint สำหรับบันทึก custom zones"""
    data = request.get_json()
    all_zones = data.get('zones', [])
    
    # กรองเฉพาะ custom zones (ที่ไม่ใช่ default)
    default_zone_ids = [
        'ZONE_BKK_CENTRAL', 'ZONE_BKK_EAST', 'ZONE_BKK_WEST', 
        'ZONE_BKK_NORTH', 'ZONE_EAST', 'ZONE_CENTRAL', 
        'ZONE_SOUTH', 'ZONE_NORTHEAST'
    ]
    
    custom_zones = [z for z in all_zones if z.get('zone_id') not in default_zone_ids]
    
    # บันทึกลงไฟล์
    success = save_custom_zones_to_file(custom_zones)
    
    if success:
        print(f"✅ บันทึก {len(custom_zones)} custom zones ลงไฟล์")
        for zone in custom_zones:
            print(f"   - {zone['zone_name']} ({len(zone['branch_ids'])} สาขา)")
        
        return jsonify({
            'success': True,
            'message': f'บันทึก {len(custom_zones)} custom zones',
            'custom_zones': custom_zones
        })
    else:
        return jsonify({
            'success': False,
            'error': 'ไม่สามารถบันทึก zones ลงไฟล์ได้'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
