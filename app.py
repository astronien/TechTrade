from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
import requests
import json
from datetime import datetime, timedelta
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Supabase Database Connection
def get_db_connection():
    """สร้าง connection ไปยัง Supabase PostgreSQL"""
    try:
        db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
        if not db_url:
            print("❌ POSTGRES_URL_NON_POOLING not found in environment variables")
            return None
        
        print(f"🔌 Connecting to database...")
        conn = psycopg2.connect(
            db_url,
            cursor_factory=RealDictCursor
        )
        print("✅ Database connected successfully")
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        import traceback
        traceback.print_exc()
        return None

# สร้างตาราง zones และ admin_users ถ้ายังไม่มี
def init_database():
    """สร้างตาราง zones และ admin_users ใน database"""
    print("🔧 Initializing database...")
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database connection failed, skipping initialization")
        return False
    
    try:
        cur = conn.cursor()
        
        # สร้างตาราง custom_zones
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
        
        # สร้างตาราง admin_users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # สร้าง admin user เริ่มต้น (username: admin, password: admin123)
        default_password = hashlib.sha256('admin123'.encode()).hexdigest()
        cur.execute("""
            INSERT INTO admin_users (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
        """, ('admin', default_password))
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database tables ready")
        print("✅ Default admin user: admin / admin123")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()
        return False

# เรียก init เมื่อ start app
try:
    init_database()
except Exception as e:
    print(f"⚠️ Database initialization failed: {e}")
    print("⚠️ App will continue without database support")

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

# Decorator สำหรับตรวจสอบ login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    """หน้าแรกแสดงข้อมูล"""
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """หน้า Login"""
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'กรุณากรอก Username และ Password'})
        
        # ตรวจสอบ username และ password
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'ไม่สามารถเชื่อมต่อ database ได้'})
        
        try:
            cur = conn.cursor()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            cur.execute("""
                SELECT id, username FROM admin_users 
                WHERE username = %s AND password_hash = %s
            """, (username, password_hash))
            
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                return jsonify({'success': True, 'message': 'เข้าสู่ระบบสำเร็จ'})
            else:
                return jsonify({'success': False, 'error': 'Username หรือ Password ไม่ถูกต้อง'})
        except Exception as e:
            print(f"Login error: {e}")
            if conn:
                conn.close()
            return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาด'})
    
    # ถ้า login แล้ว redirect ไปหน้าหลัก
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('login'))

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
    try:
        conn = get_db_connection()
        if not conn:
            print("⚠️ No database connection, returning empty zones")
            return []
        
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
        import traceback
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.close()
        return []

# บันทึก custom zones ลง Supabase
def save_custom_zones_to_file(custom_zones):
    """บันทึก custom zones ลง Supabase PostgreSQL"""
    try:
        conn = get_db_connection()
        if not conn:
            print("❌ No database connection, cannot save zones")
            return False
        
        cur = conn.cursor()
        
        # ลบ zones เดิมทั้งหมด
        cur.execute("DELETE FROM custom_zones")
        print(f"🗑️ Deleted old zones")
        
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
            print(f"💾 Saved zone: {zone['zone_name']}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ บันทึก {len(custom_zones)} custom zones ลง database สำเร็จ")
        return True
    except Exception as e:
        print(f"❌ Error saving custom zones: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals() and conn:
            conn.rollback()
            conn.close()
        return False

# โหลด Zones data
def load_zones_data():
    """โหลดข้อมูล Zones (เฉพาะ custom zones ที่ผู้ใช้สร้าง)"""
    # โหลด custom zones จาก database
    custom_zones = load_custom_zones_from_file()
    
    return custom_zones

def find_zone_by_name(zone_name):
    """ค้นหา Zone จากชื่อ (รองรับการค้นหาแบบไม่ตรงทั้งหมด)"""
    zones = load_zones_data()
    zone_name_lower = zone_name.lower()
    
    for zone in zones:
        if zone_name_lower in zone['zone_name'].lower():
            return zone
    
    return None

def find_branch_by_id(branch_id_input):
    """ค้นหาสาขาจาก ID number (เช่น 9 จาก ID9, 13 จาก ID13)"""
    import os
    import re
    branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
    
    try:
        # แปลงเป็นตัวเลข
        search_id = int(branch_id_input)
        
        with open(branches_file, 'r', encoding='utf-8') as f:
            branches_data = json.load(f)
            
        for branch in branches_data:
            branch_name = branch.get('branch_name', '')
            # ดึงตัวเลขจาก ID (เช่น "00009 : ID9 : ..." -> 9)
            match = re.search(r'ID(\d+)', branch_name)
            if match:
                id_number = int(match.group(1))
                if id_number == search_id:
                    return branch
    except ValueError:
        print(f"Invalid branch_id: {branch_id_input}")
    except Exception as e:
        print(f"Error loading branches: {e}")
    
    return None

def parse_thai_month(month_name):
    """แปลงชื่อเดือนภาษาไทยเป็นเลขเดือน"""
    months = {
        'มกราคม': 1, 'ม.ค.': 1,
        'กุมภาพันธ์': 2, 'ก.พ.': 2,
        'มีนาคม': 3, 'มี.ค.': 3,
        'เมษายน': 4, 'เม.ย.': 4,
        'พฤษภาคม': 5, 'พ.ค.': 5,
        'มิถุนายน': 6, 'มิ.ย.': 6,
        'กรกฎาคม': 7, 'ก.ค.': 7,
        'สิงหาคม': 8, 'ส.ค.': 8,
        'กันยายน': 9, 'ก.ย.': 9,
        'ตุลาคม': 10, 'ต.ค.': 10,
        'พฤศจิกายน': 11, 'พ.ย.': 11,
        'ธันวาคม': 12, 'ธ.ค.': 12
    }
    return months.get(month_name.strip(), None)

def get_month_date_range(month_number, year=None):
    """คำนวณวันแรกและวันสุดท้ายของเดือน"""
    from datetime import datetime
    import calendar
    
    if year is None:
        year = datetime.now().year
    
    # วันแรกของเดือน
    first_day = datetime(year, month_number, 1)
    
    # วันสุดท้ายของเดือน
    last_day_num = calendar.monthrange(year, month_number)[1]
    last_day = datetime(year, month_number, last_day_num)
    
    return first_day.strftime('%d/%m/%Y'), last_day.strftime('%d/%m/%Y')

# Import LINE Bot Handler
from line_bot_handler import handle_line_message

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
                
                # ถ้าเป็นกลุ่ม ต้องขึ้นต้นด้วย "รายงาน"
                if source_type == 'group':
                    if not user_message.strip().startswith('รายงาน'):
                        continue  # ไม่ตอบข้อความอื่นๆ ในกลุ่ม
                
                # ใช้ handler จัดการข้อความ
                response_message = handle_line_message(
                    user_message,
                    fetch_data_from_api,
                    load_zones_data,
                    find_zone_by_name,
                    find_branch_by_id,
                    parse_thai_month,
                    get_month_date_range
                )
                
                # ถ้ามี response ให้ส่งกลับ
                if response_message:
                    reply_line_message(reply_token, response_message)
        
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
    try:
        data = request.get_json()
        zones = data.get('zones', [])
        
        # บันทึกทุก zones ที่ส่งมา (ไม่มี default zones อีกต่อไป)
        success = save_custom_zones_to_file(zones)
        
        if success:
            print(f"✅ บันทึก {len(zones)} zones")
            for zone in zones:
                print(f"   - {zone['zone_name']} ({len(zone['branch_ids'])} สาขา)")
            
            return jsonify({
                'success': True,
                'message': f'บันทึก {len(zones)} zones',
                'zones': zones
            })
        else:
            return jsonify({
                'success': False,
                'error': 'ไม่สามารถบันทึก zones ลง database ได้'
            }), 500
    except Exception as e:
        print(f"❌ Error in save_zones: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'เกิดข้อผิดพลาด: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
