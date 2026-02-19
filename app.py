from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_file
from functools import wraps
import requests
import json
from datetime import datetime, timedelta
import os
import secrets
import hashlib
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)
# Use a fixed secret key for development to avoid session invalidation on restart
app.secret_key = os.environ.get('SECRET_KEY', 'techtrade_dev_secret_key_fixed_12345')
app.permanent_session_lifetime = timedelta(days=7) # Remember login for 7 days

# Global Cache for Dynamic Params
DYNAMIC_PARAMS_CACHE = {
    'data': None,
    'timestamp': 0
}
CACHE_DURATION = 300 # 5 minutes

# Global Cache for Eve Session (auto-login)
EVE_SESSION_CACHE = {
    'session_id': None,
    'timestamp': 0
}
EVE_SESSION_DURATION = 600  # 10 นาที

# Supabase Database Connection
def get_db_connection():
    """สร้าง connection ไปยัง Supabase PostgreSQL"""
    try:
        db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
        if not db_url:
            print("❌ POSTGRES_URL_NON_POOLING not found in environment variables")
            return None
        
        print(f"🔌 Connecting to database...")
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(
            db_url,
            cursor_factory=RealDictCursor,
            connect_timeout=10
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
        
        # สร้างตาราง cached_branches (เก็บรายชื่อสาขา)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cached_branches (
                id SERIAL PRIMARY KEY,
                branch_data JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # สร้างตาราง system_settings (เก็บ Session ID และ User/Pass ของ Eve)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key VARCHAR(255) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # สร้างตาราง api_dynamic_params (เก็บ dynamic parameters ที่ค้นพบจาการ auto-healing)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_dynamic_params (
                param_key VARCHAR(255) PRIMARY KEY,
                param_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # สร้างตาราง auto_cancel_config
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_cancel_config (
                id SERIAL PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                schedule_time VARCHAR(5) DEFAULT '23:00',
                branch_ids TEXT DEFAULT '',
                emp_code VARCHAR(50) DEFAULT '',
                emp_name VARCHAR(100) DEFAULT '',
                emp_phone VARCHAR(20) DEFAULT '',
                cancel_type VARCHAR(5) DEFAULT '1',
                reason_cancel VARCHAR(5) DEFAULT '1',
                description TEXT DEFAULT '-',
                telegram_bot_token TEXT DEFAULT '',
                telegram_chat_id TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # สร้างตาราง auto_cancel_log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_cancel_log (
                id SERIAL PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                branch_ids TEXT DEFAULT '',
                total_found INTEGER DEFAULT 0,
                total_cancelled INTEGER DEFAULT 0,
                total_skipped INTEGER DEFAULT 0,
                total_failed INTEGER DEFAULT 0,
                details TEXT DEFAULT '',
                telegram_sent BOOLEAN DEFAULT FALSE
            )
        """)
        
        # สร้างตาราง admin_users
        
        # สร้าง admin user เริ่มต้น
        default_password = hashlib.sha256('teehid1234'.encode()).hexdigest()
        cur.execute("""
            INSERT INTO admin_users (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
        """, ('tanadech', default_password))
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database tables ready")
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

# ==========================================
# Database Helper Functions for Branch & Settings
# ==========================================

from flask import g

def save_branches_to_db(branches_list):
    """บันทึกรายชื่อสาขาลง Database (cached_branches)"""
    conn = get_db_connection()
    if not conn:
        print("⚠️ No database connection, falling back to memory/file")
        return False
        
    try:
        cur = conn.cursor()
        # ลบข้อมูลเก่าทิ้ง (เราเก็บแค่ version ล่าสุดก็พอ)
        cur.execute("TRUNCATE TABLE cached_branches")
        
        # บันทึกข้อมูลใหม่
        cur.execute("""
            INSERT INTO cached_branches (branch_data)
            VALUES (%s)
        """, (json.dumps(branches_list, ensure_ascii=False),))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Saved {len(branches_list)} branches to database")
        return True
    except Exception as e:
        print(f"❌ Error saving branches to DB: {e}")
        if conn: conn.close()
        return False

def get_branches_from_db():
    """ดึงรายชื่อสาขาจาก Database"""
    conn = get_db_connection()
    if not conn:
        return []
        
    try:
        cur = conn.cursor()
        cur.execute("SELECT branch_data FROM cached_branches ORDER BY updated_at DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return row['branch_data']
        return []
    except Exception as e:
        print(f"❌ Error fetching branches from DB: {e}")
        if conn: conn.close()
        return []

def save_system_setting(key, value):
    """บันทึกการตั้งค่าระบบลง DB"""
    conn = get_db_connection()
    if not conn: return False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) 
            DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error saving setting {key}: {e}")
        if conn: conn.close()
        return False

def get_system_setting(key):
    """ดึงการตั้งค่าระบบจาก DB"""
    conn = get_db_connection()
    if not conn: return None
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return row['value']
        return None
    except Exception as e:
        print(f"❌ Error fetching setting {key}: {e}")
        if conn: conn.close()
        return None

def get_dynamic_params():
    """ดึง parameters เพิ่มเติมจาก DB (Cached)"""
    global DYNAMIC_PARAMS_CACHE
    import time
    
    current_time = time.time()
    
    # Check cache validity
    if DYNAMIC_PARAMS_CACHE['data'] is not None and \
       (current_time - DYNAMIC_PARAMS_CACHE['timestamp'] < CACHE_DURATION):
        return DYNAMIC_PARAMS_CACHE['data']
        
    conn = get_db_connection()
    if not conn: 
        # Return cached data if DB fails (fallback)
        return DYNAMIC_PARAMS_CACHE['data'] or {}
    
    params = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT param_key, param_value FROM api_dynamic_params")
        rows = cur.fetchall()
        
        for row in rows:
            params[row['param_key']] = row['param_value']
            
        cur.close()
        conn.close()
        
        # Update Cache
        DYNAMIC_PARAMS_CACHE['data'] = params
        DYNAMIC_PARAMS_CACHE['timestamp'] = current_time
        
        if params:
            print(f"🧩 Loaded dynamic params (Updated Cache): {list(params.keys())}")
        return params
    except Exception as e:
        print(f"❌ Error fetching dynamic params: {e}")
        if conn: conn.close()
        return DYNAMIC_PARAMS_CACHE['data'] or {}

def save_dynamic_param(key, value=""):
    """บันทึก parameter ใหม่ลง DB"""
    conn = get_db_connection()
    if not conn: return False
    
    try:
        print(f"💊 Auto-Healing: Saving new parameter '{key}'='{value}'")
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO api_dynamic_params (param_key, param_value)
            VALUES (%s, %s)
            ON CONFLICT (param_key) 
            DO UPDATE SET param_value = EXCLUDED.param_value
        """, (key, value))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error saving dynamic param {key}: {e}")
        if conn: conn.close()
        return False

def trigger_branch_update(session_id):
    """ฟังก์ชันกลางสำหรับสั่งอัปเดตสาขา"""
    try:
        print(f"🔄 Triggering branch update with Session ID: {session_id[:10]}...")
        url = 'https://eve.techswop.com/TI/inventory/stock-view-list.aspx/GetDropDownBranch'
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Cookie': f'ASP.NET_SessionId={session_id}'
        }
        
        response = requests.post(url, headers=headers, json={})
        
        if response.status_code == 200:
            result = response.json()
            branches_list = []
            
            # Extract Data
            if 'd' in result:
                raw_data = result['d']
                if isinstance(raw_data, str):
                    branches_list = json.loads(raw_data)
                elif isinstance(raw_data, list):
                    branches_list = raw_data
                elif isinstance(raw_data, dict) and 'data' in raw_data:
                    branches_list = raw_data['data']
            elif isinstance(result, list):
                branches_list = result
                
            if branches_list:
                # Format Data
                formatted_branches = []
                for b in branches_list:
                    bid = b.get('BRANCH_ID') or b.get('branch_id') or b.get('Value') or b.get('Id')
                    bname = b.get('BRANCH_NAME') or b.get('branch_name') or b.get('Text') or b.get('Name')
                    if bid and bname:
                        formatted_branches.append({"branch_id": bid, "branch_name": bname})
                
                # Save to DB
                if formatted_branches:
                    save_branches_to_db(formatted_branches)
                    return True, len(formatted_branches)
                    
        return False, 0
    except Exception as e:
        print(f"❌ Trigger update failed: {e}")
        return False, 0

# ==========================================
# Bot / Auto-Login Logic
# ==========================================
import re


def extract_aspnet_fields(html_content):
    """Extract ASP.NET hidden fields needed for POST requests"""
    fields = {}
    try:
        if isinstance(html_content, bytes):
            html_content = html_content.decode('utf-8', errors='ignore')
            
        # Regex ที่ยืดหยุ่นขึ้น (รองรับทั้ง id และ name, และสลับตำแหน่ง attribute)
        patterns = {
            '__VIEWSTATE': [
                 r'id="__VIEWSTATE" value="([^"]+)"', 
                 r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]+)"',
                 r'value="([^"]+)" id="__VIEWSTATE"',
                 r'value="([^"]+)" name="__VIEWSTATE"'
            ],
            '__VIEWSTATEGENERATOR': [
                r'id="__VIEWSTATEGENERATOR" value="([^"]+)"',
                r'value="([^"]+)" id="__VIEWSTATEGENERATOR"'
            ],
            '__EVENTVALIDATION': [
                r'id="__EVENTVALIDATION" value="([^"]+)"',
                r'value="([^"]+)" id="__EVENTVALIDATION"'
            ]
        }
        
        for field, regex_list in patterns.items():
            for regex in regex_list:
                match = re.search(regex, html_content)
                if match:
                    fields[field] = match.group(1)
                    break 
            
    except Exception as e:
        print(f"⚠️ Error extracting ASP.NET fields: {e}")
        
    return fields

def perform_eve_login():
    """Log in to Eve System using stored credentials (Bot)"""
    try:
        # 1. Get Credentials
        username = get_system_setting('eve_username')
        password = get_system_setting('eve_password')
        
        if not username or not password:
            return None, "No credentials stored in settings."
            
        # Trim whitespaces
        username = username.strip()
        password = password.strip()
            
        print(f"🤖 Bot attempting login as: {username}...")
        
        session = requests.Session()
        login_url = 'https://eve.techswop.com/TI/login.aspx'
        
        # 2. GET Login Page (to parse ViewState)
        try:
            response_get = session.get(login_url, timeout=30)
        except requests.exceptions.RequestException as e:
            return None, f"Connection Failed (GET): {str(e)}"

        if response_get.status_code != 200:
            return None, f"Login Page Unreachable: HTTP {response_get.status_code}"
            
        hidden_fields = extract_aspnet_fields(response_get.content)
        if '__VIEWSTATE' not in hidden_fields:
            return None, "Could not find __VIEWSTATE in login page."
            
        # 3. POST Credentials
        payload = {
            'txtUsername': username,
            'txtPassword': password,
            'btnSignin': 'เข้าสู่ระบบ', 
            **hidden_fields
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': login_url,
            'Origin': 'https://eve.techswop.com',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            response_post = session.post(login_url, data=payload, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
             return None, f"Connection Failed (POST): {str(e)}"
        
        # 4. Check Success
        cookies = session.cookies.get_dict()
        session_id = cookies.get('ASP.NET_SessionId')
        
        # Debug: Check response URL
        print(f"👉 Post Login URL: {response_post.url}")
        
        if session_id:
            # ตรวจสอบเพิ่มเติมว่า Login จริงหรือเปล่า (ถ้าเด้งกลับมาหน้า Login แปลว่าผิด)
            if '/login.aspx' in response_post.url.lower() and 'เข้าสู่ระบบ' in response_post.text:
                 # Check for specific error message in HTML if possible
                 if 'รหัสผ่านไม่ถูกต้อง' in response_post.text or 'User หรือ Password ไม่ถูกต้อง' in response_post.text:
                     return None, "Username or Password Incorrect."
                 return None, "Login failed (Redirected to login page). Credentials might be wrong."

            print(f"✅ Bot Login Successful! Session ID: {session_id[:10]}...")
            return session_id, None
            
        return None, "No Session ID returned from server."

    except Exception as e:
        print(f"❌ Bot Login Error: {e}")
        return None, f"System Error: {str(e)}"


def get_eve_session(force_refresh=False):
    """ดึง Eve Session ID อัตโนมัติ (cached + auto-login)"""
    global EVE_SESSION_CACHE
    import time
    
    current_time = time.time()
    
    # ใช้ cache ถ้ายังไม่หมดอายุ
    if not force_refresh and EVE_SESSION_CACHE['session_id'] and \
       (current_time - EVE_SESSION_CACHE['timestamp'] < EVE_SESSION_DURATION):
        return EVE_SESSION_CACHE['session_id']
    
    # Login ใหม่
    print("🔐 Auto-Login: กำลัง login Eve อัตโนมัติ...")
    session_id, error = perform_eve_login()
    if session_id:
        EVE_SESSION_CACHE['session_id'] = session_id
        EVE_SESSION_CACHE['timestamp'] = current_time
        print(f"✅ Auto-Login สำเร็จ! Session cached for {EVE_SESSION_DURATION}s")
        return session_id
    
    print(f"❌ Auto-Login ล้มเหลว: {error}")
    return None


@app.route('/api/admin/run-bot', methods=['POST', 'GET'])
def run_bot_update():
    """API to manually trigger the Bot"""
    try:
        session_id, error_msg = perform_eve_login()
        if not session_id:
            return jsonify({'success': False, 'error': error_msg}), 400
            
        # Trigger update with new session
        success, count = trigger_branch_update(session_id)
        
        return jsonify({
            'success': success,
            'message': f'Bot Login Successful! Updated {count} branches.',
            'count': count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
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
    
    payload = {
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
        "customerSign": customer_sign,
    }
    
    # ผสาน dynamic parameters จาก DB
    dynamic_params = get_dynamic_params()
    # ถ้ายังไม่มีใน DB ให้ใส่ default ufund="" ไปก่อน (เพื่อความเข้ากันได้ย้อนหลังกับ hardcode เดิม)
    if 'ufund' not in dynamic_params:
        dynamic_params['ufund'] = ""
        
    # อัปเดต payload ด้วย dynamic parameters
    # (ถ้ามี key ซ้ำ จะใช้ค่าจาก dynamic_params ทับ)
    payload.update(dynamic_params)
    
    return payload

def fetch_data_from_api(start=0, length=50, **filters):
    """ดึงข้อมูลจาก API พร้อมระบบ Auto-Healing"""
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }
    
    # เตรียม cookies ด้วย auto-login session
    cookies = {}
    
    # ดึง session_id อัตโนมัติจาก Eve (cached)
    session_id = get_eve_session()
    if session_id:
        cookies['ASP.NET_SessionId'] = session_id
        print(f"🔐 Using Auto Session ID: {session_id[:10]}...")
    
    # ดึง branch_id ออกจาก filters
    branch_id = filters.pop('branch_id', BRANCH_ID)
    
    payload = get_datatables_payload(start, length, branch_id=branch_id, **filters)
    
    # Debug: แสดง payload ที่ส่งไป
    print(f"📤 Sending to API:")
    print(f"   Date: {filters.get('date_start')} to {filters.get('date_end')}")
    print(f"   Branch ID (in payload): {branch_id}")
    print(f"   Sale Code: {filters.get('sale_code', 'N/A')}")
    print(f"   Session ID: {session_id[:10] if session_id else 'N/A'}...")
    print(f"🔍 DEBUG: Full payload branchID field: {payload.get('branchID')}")
    
    # ใช้ Session เพื่อ reuse connection
    with requests.Session() as session:
        # Retry loop สำหรับ Auto-Healing
        max_healing_retries = 2
        for attempt in range(max_healing_retries + 1):
            try:
                # Re-generate payload ในทุกรอบ เพราะ dynamic params อาจเปลี่ยนไปหลัง healing
                # (รอบแรกใช้อันที่สร้างมาแล้ว ถ้ารอบ 2 สร้างใหม่)
                if attempt > 0:
                    print(f"🩹 Healing Attempt {attempt}...")
                    payload = get_datatables_payload(start, length, branch_id=branch_id, **filters)
                
                response = session.post(API_URL, headers=headers, json=payload, cookies=cookies, timeout=45)
                
                # ตรวจสอบ Error 500 เพื่อทำ Auto-Healing
                if response.status_code == 500:
                    print(f"🔥 Got 500 Error. Checking for missing parameters...")
                    try:
                        error_json = response.json()
                        error_msg = error_json.get('Message', '')
                        
                        # Regex หา Missing Parameter
                        # ตัวอย่าง: "Invalid web service call, missing value for parameter: 'ufund'."
                        import re
                        match = re.search(r"missing value for parameter: '(\w+)'", error_msg)
                        if match:
                            missing_param = match.group(1)
                            print(f"💡 Found missing parameter: {missing_param}")
                            
                            # บันทึกลง DB
                            save_dynamic_param(missing_param, "")
                            print(f"✅ Auto-Healed! Added '{missing_param}' to dynamic params.")
                            
                            # Continue เพื่อเริ่มลูปใหม่ (ซึ่งจะไปดึง param ใหม่มาใช้)
                            continue
                    except:
                        pass # ถ้า parse ไม่ได้ก็ปล่อยไปตามยถากรรม
                
                response.raise_for_status()
                result = response.json()
            
                # ถ้าสำเร็จ (หรือไม่ใช่ 500) ให้ break loop ออกไป return ผลลัพธ์
                # แต่ถ้ายังเป็น 500 และไม่เจอ params ขาด ก็จะหลุดมา raise_for_status ข้างล่างอยู่ดี
                break 
                
            except requests.exceptions.RequestException as e:
                # ถ้าเป็น error ทั่วไป (timeout, connection)
                print(f"⚠️ API Error (Attempt {attempt}): {e}")
                
                if attempt < max_healing_retries:
                    import time
                    time.sleep(1) # รอสักครู่ก่อนลองใหม่
                    continue
                    
                # ถ้าเป็นรอบสุดท้าย ให้ return error
                print(f"❌ API Failed after {max_healing_retries} retries: {e}")
                return {"error": str(e)} 
            
    # Move logging and return logic outside/inside try based on original structure
    # Original structure handled exceptions for the whole block.
    # We need to adapt it. 
    
    # Actually, easiest way is to wrap the whole loop and if success, process.
    # But we need result variable.
    
    # Let's restructure to match the original flow better
    try:
        # Debug: แสดง response
        print(f"📥 API Response:")
        if 'd' in result:
            data_obj = result['d']
            records_total = data_obj.get('recordsTotal', 0)
            records_filtered = data_obj.get('recordsFiltered', 0)
            data_items = len(data_obj.get('data', []))
            
            print(f"   Records Total: {records_total}")
            print(f"   Records Filtered: {records_filtered}")
            print(f"   Data items: {data_items}")
            
            # Debug: ถ้าไม่มีข้อมูล แสดงรายละเอียดเพิ่มเติม
            if records_filtered == 0:
                print(f"⚠️ DEBUG: No records found!")
                print(f"   - Branch ID used: {branch_id}")
                print(f"   - Date range: {filters.get('date_start')} to {filters.get('date_end')}")
            
            return {
                'data': data_obj.get('data', []),
                'recordsTotal': records_total,
                'recordsFiltered': records_filtered
            }
        else:
            print(f"   Unexpected format: {result}")
        return result
        
    except UnboundLocalError:
        # Case where loop finished without assignment (should raise in loop)
        return {"error": "API Call Failed"}
        
    except Exception as e:
        # Fallback
        return {"error": str(e)}



def fetch_data_with_retry(start=0, length=50, max_retries=3, **filters):
    """ดึงข้อมูลจาก API พร้อม retry mechanism"""
    import time
    
    for retry_count in range(max_retries):
        data = fetch_data_from_api(start=start, length=length, **filters)
        
        if 'error' not in data:
            # เพิ่ม delay เล็กน้อยระหว่าง request เพื่อไม่ให้ API ล้น
            time.sleep(0.5)
            return data
        
        if retry_count < max_retries - 1:
            wait_time = 3 * (retry_count + 1)  # เพิ่มเวลารอเป็น 3, 6, 9 วินาที
            print(f"⚠️ Retry {retry_count + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)
    
    return data  # ส่ง error กลับถ้า retry หมดแล้ว

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
        
        print(f"🔐 Login attempt - Username: {username}")
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'กรุณากรอก Username และ Password'})
        
        # ตรวจสอบ username และ password
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'ไม่สามารถเชื่อมต่อ database ได้'})
        
        try:
            cur = conn.cursor()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            print(f"🔑 Password hash: {password_hash}")
            
            cur.execute("""
                SELECT id, username, password_hash FROM admin_users 
                WHERE username = %s
            """, (username,))
            
            user = cur.fetchone()
            
            if user:
                print(f"✅ User found: {user['username']}")
                print(f"📝 Stored hash: {user['password_hash']}")
                print(f"🔍 Match: {user['password_hash'] == password_hash}")
                
                if user['password_hash'] == password_hash:
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session.permanent = True
                    print(f"✅ Login successful for {username}")
                    cur.close()
                    conn.close()
                    return jsonify({'success': True, 'message': 'เข้าสู่ระบบสำเร็จ'})
                else:
                    print(f"❌ Password mismatch for {username}")
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Username หรือ Password ไม่ถูกต้อง'})
            else:
                print(f"❌ User not found: {username}")
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Username หรือ Password ไม่ถูกต้อง'})
        except Exception as e:
            print(f"❌ Login error: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.close()
            return jsonify({'success': False, 'error': f'เกิดข้อผิดพลาด: {str(e)}'})
    
    # ถ้า login แล้ว redirect ไปหน้าหลัก
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('login'))

# Routes /install-extension และ /download-extension ถูกลบออกแล้ว
# เนื่องจากระบบใช้ Auto-Login แทน Chrome Extension

@app.route('/api/data')
def get_data():
    """API endpoint สำหรับดึงข้อมูล"""
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 50, type=int)  # ลดเหลือ 50 เพื่อป้องกัน Timeout
    
    # รับพารามิเตอร์จากฟอร์ม (session จัดการอัตโนมัติโดย backend)
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
        'branch_id': request.args.get('branchId', BRANCH_ID)
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

def fetch_all_for_branch(filters):
    """ดึงข้อมูลทั้งหมดของสาขาเดียว (พร้อม pagination)"""
    import time
    
    # ปรับ timeout ตามสภาพแวดล้อม
    is_vercel = os.environ.get('VERCEL', False)
    max_time = 160 if is_vercel else 120
    max_items = 10000 if is_vercel else 50000
    
    length = 100
    start = 0
    all_items = []
    batch_count = 0
    start_time = time.time()
    
    print(f"📊 Fetching for branch {filters.get('branch_id')}...")
    
    while True:
        # ตรวจสอบเวลา
        elapsed = time.time() - start_time
        if elapsed > max_time:
            print(f"⚠️ Timeout protection: stopped at {len(all_items)} items after {elapsed:.1f}s")
            break
            
        batch_count += 1
        
        data = fetch_data_with_retry(start=start, length=length, **filters)
        
        if 'error' in data:
            print(f"❌ API Error: {data['error']}")
            return [] # Return empty list on error to allow other branches to continue
        
        batch_data = data.get('data', [])
        if not batch_data:
            break
        
        all_items.extend(batch_data)
        
        # ตรวจสอบว่าดึงครบหรือยัง
        total = data.get('recordsFiltered', 0)
        if len(all_items) >= total or len(batch_data) < length:
            break
        
        start += length
        
        # ป้องกัน infinite loop
        if len(all_items) >= max_items:
            break
            
    return all_items

def fetch_and_process_report(filters):
    """ดึงและประมวลผลข้อมูลรายงาน"""
    from collections import defaultdict
    import time
    
    start_time = time.time()
    all_items = []
    
    zone_id = filters.get('zone_id')
    
    if zone_id:
        print(f"🗺️ Fetching data for Zone: {zone_id}")
        zones = load_custom_zones_from_file()
        target_zone = next((z for z in zones if str(z['zone_id']) == str(zone_id)), None)
        
        if target_zone:
            branch_ids = target_zone['branch_ids']
            print(f"   Found {len(branch_ids)} branches: {branch_ids}")
            
            for i, branch_id in enumerate(branch_ids):
                print(f"   [{i+1}/{len(branch_ids)}] Processing branch {branch_id}...")
                branch_filters = filters.copy()
                branch_filters['branch_id'] = branch_id
                # ลบ zone_id ออกเพื่อไม่ให้ recursive (แม้จริงๆ function นี้ไม่ได้เรียกตัวเอง)
                if 'zone_id' in branch_filters:
                    del branch_filters['zone_id']
                
                items = fetch_all_for_branch(branch_filters)
                all_items.extend(items)
        else:
            print(f"❌ Zone not found: {zone_id}")
            return {'error': 'ไม่พบข้อมูล Zone'}, []
    else:
        # สาขาเดียว
        all_items = fetch_all_for_branch(filters)
    
    elapsed_time = time.time() - start_time
    print(f"✅ Total items fetched: {len(all_items)} in {elapsed_time:.1f}s")
    
    elapsed_time = time.time() - start_time
    print(f"✅ Total items fetched: {len(all_items)} in {elapsed_time:.1f}s")
    
    if not all_items:
        return None, []
    
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
    
    return report, items

@app.route('/api/report')
def get_report():
    """API endpoint สำหรับสร้างรายงาน"""
    # รับพารามิเตอร์ (session จัดการอัตโนมัติโดย backend)
    filters = {
        'date_start': request.args.get('dateStart', ''),
        'date_end': request.args.get('dateEnd', ''),
        'sale_code': request.args.get('saleCode', ''),
        'customer_sign': request.args.get('customerSign', ''),
        'branch_id': request.args.get('branchId', BRANCH_ID)
    }
    
    report, items = fetch_and_process_report(filters)
    
    if report is None:
        return jsonify({
            'error': 'ไม่พบข้อมูล',
            'message': 'ไม่พบข้อมูลในช่วงเวลาที่เลือก กรุณาตรวจสอบช่วงวันที่'
        }), 404
        
    if 'error' in report:
        return jsonify(report), 500
    
    return jsonify({
        'report': report,
        'details': items
    })

@app.route('/api/export-report')
def export_report():
    """API endpoint สำหรับ Export รายงานเป็น Excel"""
    # รับพารามิเตอร์ (session จัดการอัตโนมัติโดย backend)
    filters = {
        'date_start': request.args.get('dateStart', ''),
        'date_end': request.args.get('dateEnd', ''),
        'sale_code': request.args.get('saleCode', ''),
        'customer_sign': request.args.get('customerSign', ''),
        'branch_id': request.args.get('branchId', BRANCH_ID),
        'zone_id': request.args.get('zoneId', '')
    }
    
    report, items = fetch_and_process_report(filters)
    
    if report is None or (not items and 'error' not in report):
        return jsonify({
            'error': 'ไม่พบข้อมูล',
            'message': 'ไม่พบข้อมูลในช่วงเวลาที่เลือก'
        }), 404
        
    if 'error' in report:
        return jsonify(report), 500
        
    # สร้างไฟล์ Excel
    filepath = generate_excel_report(items, report, filters['date_start'], filters['date_end'])
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=os.path.basename(filepath)
    )



@app.route('/api/check-cancel', methods=['POST'])
def check_cancel():
    """API endpoint สำหรับตรวจสอบว่ายกเลิกได้หรือไม่"""
    data = request.get_json()
    trade_in_id = data.get('tradeInId', '')
    
    # ใช้ auto-login session แทน cookies จาก client
    session_id = get_eve_session()
    cookies = {'ASP.NET_SessionId': session_id} if session_id else {}
    
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
    
    # ใช้ auto-login session แทน cookies จาก client
    session_id = get_eve_session()
    cookies = {'ASP.NET_SessionId': session_id} if session_id else {}
    
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

# Routes /api/get-cookies และ /api/auto-get-session ถูกลบออกแล้ว
# เนื่องจากระบบใช้ Auto-Login ผ่าน get_eve_session() แทน

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
    """ค้นหาสาขาจาก ID number (เช่น 9 จาก ID9, 13 จาก ID13) หรือ branch_id"""
    import os
    import re
    branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
    
    try:
        with open(branches_file, 'r', encoding='utf-8') as f:
            branches_data = json.load(f)
        
        # ลองค้นหาจาก ID number ในชื่อสาขาก่อน (เพื่อให้ตรงกับที่ผู้ใช้ต้องการ)
        try:
            search_id = int(branch_id_input)
            for branch in branches_data:
                branch_name = branch.get('branch_name', '')
                # ดึงตัวเลขจาก ID (เช่น "00009 : ID9 : ..." -> 9)
                match = re.search(r'ID(\d+)', branch_name)
                if match:
                    id_number = int(match.group(1))
                    if id_number == search_id:
                        return branch
        except ValueError:
            pass
        
        # ถ้าไม่เจอ ลองค้นหาจาก branch_id ตรงๆ
        branch_id_str = str(branch_id_input)
        for branch in branches_data:
            if str(branch.get('branch_id', '')) == branch_id_str:
                return branch
            
    except Exception as e:
        print(f"Error loading branches: {e}")
    
    return None

def find_branch_by_sequential_id(seq_id):
    """ค้นหาสาขาจาก branch_id (sequential index)"""
    import os
    import json
    branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
    
    print(f"🔍 DEBUG find_branch_by_sequential_id: Looking for seq_id={seq_id} (type: {type(seq_id)})")
    
    try:
        with open(branches_file, 'r', encoding='utf-8') as f:
            branches_data = json.load(f)
        
        print(f"🔍 DEBUG find_branch_by_sequential_id: Loaded {len(branches_data)} branches from file")
        
        try:
            seq_id_int = int(seq_id)
            print(f"🔍 DEBUG find_branch_by_sequential_id: Converted to int: {seq_id_int}")
            
            for branch in branches_data:
                if branch.get('branch_id') == seq_id_int:
                    print(f"✅ DEBUG find_branch_by_sequential_id: Found branch: {branch.get('branch_name')}")
                    return branch
            
            print(f"⚠️ DEBUG find_branch_by_sequential_id: No branch found with branch_id={seq_id_int}")
        except ValueError:
            print(f"❌ DEBUG find_branch_by_sequential_id: Cannot convert '{seq_id}' to int")
            pass
            
    except Exception as e:
        print(f"❌ DEBUG find_branch_by_sequential_id: Error loading branches: {e}")
    
    return None

def get_real_branch_id(branch):
    """ดึง Real ID จากข้อมูลสาขา (เช่น 249 จาก ID249)"""
    if not branch:
        print(f"🔍 DEBUG get_real_branch_id: branch is None/empty")
        return None
        
    branch_name = branch.get('branch_name', '')
    print(f"🔍 DEBUG get_real_branch_id: Processing branch_name: {branch_name}")
    
    import re
    
    # Pattern 1: IDxxx (e.g. "00249 : ID249 : ...")
    match = re.search(r'ID(\d+)', branch_name)
    if match:
        real_id = match.group(1)
        print(f"✅ DEBUG get_real_branch_id: Pattern 1 (IDxxx) matched -> {real_id}")
        return real_id
        
    # Pattern 2: FCBxxx/FCPxxx (e.g. "00517 : FCB517 : ...")
    match = re.search(r'FC[BP](\d+)', branch_name)
    if match:
        real_id = match.group(1)
        print(f"✅ DEBUG get_real_branch_id: Pattern 2 (FCBxxx) matched -> {real_id}")
        return real_id
        
    # Pattern 3: Just numbers in the middle (e.g. "01331 : 1331 : ...")
    parts = branch_name.split(':')
    if len(parts) >= 2:
        middle = parts[1].strip()
        match = re.search(r'(\d+)', middle)
        if match:
            real_id = match.group(1)
            print(f"✅ DEBUG get_real_branch_id: Pattern 3 (middle number) matched -> {real_id}")
            return real_id
    
    # Fallback: ใช้ branch_id
    fallback_id = str(branch.get('branch_id'))
    print(f"⚠️ DEBUG get_real_branch_id: No pattern matched, using branch_id -> {fallback_id}")
    return fallback_id

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
from excel_report_generator import generate_annual_excel_report, parse_year_from_command, get_year_date_range

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
                
                # ตรวจสอบว่าเป็นคำสั่ง Excel Annual Report หรือไม่
                if isinstance(response_message, dict) and response_message.get('type') == 'excel_annual':
                    # จัดการคำสั่ง Excel รายปี
                    handle_excel_annual_request(reply_token, response_message['parts'], event)
                elif response_message:
                    # ส่ง text message ปกติ
                    reply_line_message(reply_token, response_message)
        
        return jsonify({'status': 'ok'})
    
    except Exception as e:
        print(f"LINE Webhook Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


def handle_excel_annual_request(reply_token, parts, event):
    """จัดการคำสั่งสร้างรายงาน Excel รายปี"""
    try:
        # ส่งข้อความแจ้งว่ากำลังประมวลผล
        reply_line_message(reply_token, "⏳ กำลังสร้างรายงาน Excel รายปี...\nโปรดรอสักครู่ (ประมาณ 30-60 วินาที)")
        
        # แยก parameter จาก parts
        # รูปแบบ: ['excel', 'รายปี', '2024', '9'] หรือ ['excel', 'รายปี', '2024']
        year = None
        branch_id = None
        branch_name = None
        
        # หาตำแหน่ง 'รายปี'
        if 'รายปี' in parts:
            year_index = parts.index('รายปี') + 1
            
            # ถ้ามีปีระบุ
            if len(parts) > year_index:
                year_str = parts[year_index]
                year = parse_year_from_command(year_str)
                
                if not year:
                    push_line_message(event, f"❌ ปีไม่ถูกต้อง: {year_str}\n\nกรุณาระบุปี ค.ศ. 2020-{datetime.now().year+1} หรือ พ.ศ. 2563-{datetime.now().year+544}")
                    return
                
                # ถ้ามี branch_id ระบุ
                if len(parts) > year_index + 1:
                    branch_id_str = parts[year_index + 1]
                    branch = find_branch_by_id(branch_id_str)
                    
                    if branch:
                        branch_id = branch['branch_id']
                        branch_name = branch['branch_name']
                    else:
                        push_line_message(event, f"❌ ไม่พบสาขา ID: {branch_id_str}")
                        return
            else:
                # ไม่ระบุปี ใช้ปีปัจจุบัน
                year = datetime.now().year
        else:
            # ไม่มีคำว่า 'รายปี' ใช้ปีปัจจุบัน
            year = datetime.now().year
        
        # ดึงข้อมูลจาก API
        date_start, date_end = get_year_date_range(year)
        
        filters = {
            'date_start': date_start,
            'date_end': date_end,
            'sale_code': '',
            'customer_sign': '',
            'session_id': '',
            'branch_id': str(branch_id) if branch_id else None
        }
        
        print(f"📊 Fetching annual data for year {year}, branch {branch_id}...")
        
        # ดึงข้อมูลทั้งปี
        all_data = []
        start = 0
        length = 1000
        
        while True:
            data = fetch_data_with_retry(start=start, length=length, **filters)
            
            if 'error' in data:
                push_line_message(event, f"❌ ไม่สามารถดึงข้อมูลได้: {data.get('error')}")
                return
            
            batch_data = data.get('data', [])
            if not batch_data:
                break
            
            all_data.extend(batch_data)
            
            # ตรวจสอบว่าดึงครบหรือยัง
            total = data.get('recordsFiltered', 0)
            if len(all_data) >= total or len(batch_data) < length:
                break
            
            start += length
            
            # ป้องกัน infinite loop
            if len(all_data) >= 50000:
                break
        
        print(f"✅ Fetched {len(all_data)} records")
        
        if not all_data:
            push_line_message(event, f"❌ ไม่พบข้อมูลในปี {year}{f' เดือน {month}' if month else ''}")
            # If no data, still generate an empty report for consistency
            # The original code would return here, but the instruction implies generating a report even if empty.
            # Let's keep the original behavior of returning if no data, as generating an empty report might not be desired.
            return
        
        # สร้าง Excel Report
        excel_path = generate_annual_excel_report(all_data, year, branch_id, branch_name, month=month)
        
        # ส่งไฟล์ Excel ผ่าน LINE
        send_excel_file_to_line(event, excel_path, year, branch_id, branch_name, month=month)
        
        # ลบไฟล์ชั่วคราว
        import os
        try:
            os.remove(excel_path)
            print(f"🗑️ Removed temp file: {excel_path}")
        except:
            pass
        
    except Exception as e:
        print(f"❌ Error generating Excel report: {str(e)}")
        import traceback
        traceback.print_exc()
        push_line_message(event, f"❌ เกิดข้อผิดพลาด: {str(e)}")


def send_excel_file_to_line(event, excel_path, year, branch_id=None, branch_name=None):
    """ส่งไฟล์ Excel ไปยัง LINE"""
    import os
    import requests
    
    channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    
    if not channel_access_token:
        print("❌ LINE_CHANNEL_ACCESS_TOKEN not found")
        push_line_message(event, "❌ ไม่สามารถส่งไฟล์ได้: ไม่พบ Channel Access Token")
        return
    
    # อ่านไฟล์
    with open(excel_path, 'rb') as f:
        file_content = f.read()
    
    # สร้างข้อความอธิบาย
    if branch_id and branch_name:
        description = f"รายงานเทรดรายปี {year}\nสาขา: {branch_name}"
    else:
        description = f"รายงานเทรดรายปี {year}\nทุกสาขา"
    
    # ส่งข้อความก่อน
    push_line_message(event, f"✅ สร้างรายงานเสร็จแล้ว!\n\n{description}\n\nกำลังส่งไฟล์...")
    
    # ส่งไฟล์ผ่าน LINE (ใช้ Push Message API)
    # หมายเหตุ: LINE Bot API ไม่รองรับการส่งไฟล์ Excel โดยตรง
    # ต้องใช้วิธีอื่น เช่น upload ไปที่ cloud storage แล้วส่ง link
    # หรือแปลงเป็น image แล้วส่ง
    
    # วิธีชั่วคราว: แจ้งให้ user ทราบว่าไฟล์พร้อมแล้ว
    push_line_message(event, f"📊 รายงานพร้อมแล้ว!\n\n{description}\n\n⚠️ ขออภัย: LINE Bot ยังไม่รองรับการส่งไฟล์ Excel โดยตรง\nกรุณาติดต่อผู้ดูแลระบบเพื่อรับไฟล์")


def push_line_message(event, message):
    """ส่ง Push Message ไปยัง LINE"""
    import os
    import requests
    
    channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    
    if not channel_access_token:
        print("❌ LINE_CHANNEL_ACCESS_TOKEN not found")
        return
    
    # ดึง user_id หรือ group_id
    source = event.get('source', {})
    source_type = source.get('type')
    
    if source_type == 'user':
        to = source.get('userId')
    elif source_type == 'group':
        to = source.get('groupId')
    elif source_type == 'room':
        to = source.get('roomId')
    else:
        print(f"❌ Unknown source type: {source_type}")
        return
    
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {channel_access_token}'
    }
    payload = {
        'to': to,
        'messages': [
            {
                'type': 'text',
                'text': message
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"✅ Pushed message to LINE")
        else:
            print(f"❌ Failed to push message: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error pushing message: {str(e)}")

def reply_line_message(reply_token, message):
    """ส่ง Reply Message ไปยัง LINE"""
    import os
    channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
    
    if channel_access_token == 'YOUR_CHANNEL_ACCESS_TOKEN':
        print("❌ Error: LINE_CHANNEL_ACCESS_TOKEN is set to default placeholder!")
        return None

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
        if response.status_code != 200:
            print(f"❌ Failed to reply Line message: {response.status_code}")
            print(f"   Response: {response.text}")
        else:
            print(f"✅ Reply Line message success")
        return response.json()
    except Exception as e:
        print(f"Error sending LINE message: {str(e)}")
        import traceback
        traceback.print_exc()
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
    
    # ใช้ auto-login session
    session_id = get_eve_session()
    eve_cookies = {'ASP.NET_SessionId': session_id} if session_id else {}
    
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
                json=check_payload,
                cookies=eve_cookies
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
                        json=cancel_payload,
                        cookies=eve_cookies
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

@app.route('/api/annual-report-data')
def get_annual_report_data():
    """API endpoint สำหรับดึงข้อมูลรายงานรายปี (JSON) - เวอร์ชันเร็ว"""
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)  # เพิ่มพารามิเตอร์เดือน
        branch_id = request.args.get('branchId', '')
        session_id = request.args.get('sessionId', '')
        
        if not year:
            return jsonify({'error': 'กรุณาระบุปี'}), 400
        
        # ตรวจสอบปี
        current_year = datetime.now().year
        if year < 2020 or year > current_year + 1:
            return jsonify({'error': f'ปีต้องอยู่ระหว่าง 2020-{current_year + 1}'}), 400
        
        # ใช้ Sequential ID ตรงๆ ไม่ต้องแปลงเป็น Real ID
        # เพราะ API ต้องการ branch_id ที่เป็น sequential index
        api_branch_id = branch_id
        branch_info = None
        
        print(f"🔍 DEBUG: Received branch_id from frontend: {branch_id} (type: {type(branch_id)})")
        
        if branch_id:
            # ค้นหาข้อมูลสาขาเพื่อแสดงชื่อ
            branch_info = find_branch_by_sequential_id(branch_id)
            print(f"🔍 DEBUG: find_branch_by_sequential_id({branch_id}) returned: {branch_info}")
            
            if branch_info:
                print(f"✅ Using Sequential ID {branch_id} for API call ({branch_info.get('branch_name')})")
            else:
                print(f"⚠️ DEBUG: Branch not found for Sequential ID: {branch_id}")
        
        print(f"📊 Fetching {'monthly' if month else 'annual'} report data for year {year}{f', month {month}' if month else ''}, branch Sequential ID: {api_branch_id or 'all'}")
        
        # นับจำนวนเทรดแต่ละเดือน/วันโดยเรียก API
        from collections import defaultdict
        import re
        import calendar
        
        if month:
            # รายงานรายเดือน - นับรายวัน
            num_days = calendar.monthrange(year, month)[1]
            daily_counts = defaultdict(lambda: {'assessed': 0, 'agreed': 0})
            total_assessed = 0
            total_agreed = 0
            
            # ดึงข้อมูลทั้งเดือน
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"01/{month:02d}/{year}"
            date_end = f"{last_day}/{month:02d}/{year}"
            
            filters = {
                'date_start': date_start,
                'date_end': date_end,
                'sale_code': '',
                'customer_sign': '',
                'session_id': session_id,
                'branch_id': api_branch_id if api_branch_id else None
            }
            
            print(f"🔍 DEBUG: Fetching daily data for month {month}")
            
            # ดึงข้อมูลทั้งหมดของเดือนนั้น
            all_items = fetch_all_for_branch(filters)
            total_assessed = len(all_items)
            
            # นับตามวัน
            for item in all_items:
                # Count Agreed (Status 3)
                is_agreed = (item.get('status') == 3)
                if is_agreed:
                    total_agreed += 1

                doc_date = item.get('document_date', '')
                if doc_date and doc_date.startswith('/Date('):
                    timestamp_match = re.search(r'/Date\((\d+)\)/', doc_date)
                    if timestamp_match:
                        timestamp = int(timestamp_match.group(1)) / 1000
                        date_obj = datetime.fromtimestamp(timestamp)
                        if date_obj.year == year and date_obj.month == month:
                            daily_counts[date_obj.day]['assessed'] += 1
                            if is_agreed:
                                daily_counts[date_obj.day]['agreed'] += 1
            
            # สร้าง array ข้อมูลรายวัน
            daily_data = []
            for day in range(1, num_days + 1):
                daily_data.append({
                    'day': day,
                    'count': daily_counts[day]['assessed'], # Backwards compatibility
                    'assessed': daily_counts[day]['assessed'],
                    'agreed': daily_counts[day]['agreed']
                })
            
            print(f"✅ Total Assessed: {total_assessed}, Agreed: {total_agreed}")
            
            # หาชื่อสาขา
            branch_name = None
            if branch_info:
                branch_name = branch_info['branch_name']
            elif branch_id:
                branch = find_branch_by_id(branch_id)
                if branch:
                    branch_name = branch['branch_name']
            
            return jsonify({
                'success': True,
                'year': year,
                'month': month,
                'branch_id': branch_id,
                'branch_name': branch_name,
                'total_records': total_assessed,
                'total_agreed': total_agreed,
                'daily_data': daily_data
            })
        else:
            # รายงานรายเดือน - นับรายวัน (Logic เดิม)
            pass # (This block is not being edited, just context)

        if not month:
            # รายงานรายปี - นับรายเดือน (พร้อม agreed/not_agreed)
            monthly_counts_all = defaultdict(int)
            monthly_counts_agreed = defaultdict(int)
            total_records = 0
            total_agreed = 0
            
            month_names = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
                           'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
            
            # สถานะที่ถือว่า "ตกลงเทรด"
            AGREED_STATUSES = ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
            
            # ดึงข้อมูลทีละเดือน
            for month_num in range(1, 13):
                last_day = calendar.monthrange(year, month_num)[1]
                date_start = f"01/{month_num:02d}/{year}"
                date_end = f"{last_day}/{month_num:02d}/{year}"
                
                filters = {
                    'date_start': date_start,
                    'date_end': date_end,
                    'sale_code': '',
                    'customer_sign': '',
                    'session_id': session_id,
                    'branch_id': api_branch_id if api_branch_id else None
                }
                
                # ดึงข้อมูลจริงมานับ agreed/not_agreed
                all_items = fetch_all_for_branch(filters)
                month_total = len(all_items)
                month_agreed = 0
                
                for item in all_items:
                    # ตรวจสอบว่าตกลงเทรดหรือไม่
                    status = item.get('status')
                    status_name = item.get('BIDDING_STATUS_NAME', '')
                    is_agreed = (status == 3 or status_name in AGREED_STATUSES)
                    if is_agreed:
                        month_agreed += 1
                
                monthly_counts_all[month_num] = month_total
                monthly_counts_agreed[month_num] = month_agreed
                total_records += month_total
                total_agreed += month_agreed
                
                print(f"   🗓️ Month {month_num}: {month_total} total, {month_agreed} agreed")
            
            print(f"✅ Total records: {total_records}, Total agreed: {total_agreed}")
            
            # สร้าง array ข้อมูล 12 เดือน
            monthly_data = []
            for month_num in range(1, 13):
                count_all = monthly_counts_all.get(month_num, 0)
                count_agreed = monthly_counts_agreed.get(month_num, 0)
                monthly_data.append({
                    'month': month_names[month_num - 1],
                    'month_number': month_num,
                    'count': count_all,  # backwards compatibility
                    'agreed': count_agreed,
                    'not_agreed': count_all - count_agreed
                })
            
            # หาชื่อสาขา
            branch_name = None
            if branch_info:
                branch_name = branch_info['branch_name']
            elif branch_id:
                branch = find_branch_by_id(branch_id)
                if branch:
                    branch_name = branch['branch_name']
            
            return jsonify({
                'success': True,
                'year': year,
                'branch_id': branch_id,
                'branch_name': branch_name,
                'total_records': total_records,
                'total_agreed': total_agreed,
                'total_not_agreed': total_records - total_agreed,
                'monthly_data': monthly_data
            })
        
    except Exception as e:
        print(f"❌ Error fetching annual report data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


@app.route('/api/annual-report-excel-from-data', methods=['POST'])
def get_annual_report_excel_from_data():
    """API endpoint สำหรับ Export Excel จากข้อมูลที่มีอยู่แล้ว (เร็ว!)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'ไม่พบข้อมูล'}), 400
        
        year = data.get('year')
        if year:
            year = int(year)  # แปลง year เป็น int
        month = data.get('month')  # เพิ่ม month parameter
        if month:
            month = int(month)  # แปลงเป็น int
        zone_name = data.get('zone_name')
        branch_name = data.get('branch_name')
        branches_data = data.get('branches_data')
        
        print(f"📊 Generating Excel from existing data for year {year} (type: {type(year)})")
        print(f"🔍 DEBUG: branches_data exists? {branches_data is not None}")
        print(f"🔍 DEBUG: Number of branches? {len(branches_data) if branches_data else 0}")
        if branches_data and len(branches_data) > 0:
            first_branch = branches_data[0]
            print(f"🔍 DEBUG: First branch has monthly_data? {first_branch.get('monthly_data') is not None}")
            if first_branch.get('monthly_data'):
                sample_data = first_branch['monthly_data']
                print(f"🔍 DEBUG: Sample data count: {len(sample_data)}")
                if len(sample_data) > 0:
                    print(f"🔍 DEBUG: First item keys: {sample_data[0].keys()}")
                    print(f"🔍 DEBUG: First item: {sample_data[0]}")
        
        # สร้าง Excel จากข้อมูลที่ส่งมา
        if branches_data:
            # Zone report
            from excel_report_generator import generate_annual_excel_report_for_zone
            from collections import defaultdict
            
            # แปลง monthly_data เป็น monthly_counts_all และ monthly_counts_agreed
            formatted_branches = []
            for branch in branches_data:
                monthly_counts_all = {}
                monthly_counts_agreed = {}
                
                for item in branch.get('monthly_data', []):
                    # ตรวจสอบว่าเป็น daily_data (มี key 'day') หรือ monthly_data (มี key 'month_number')
                    if 'day' in item:
                        period_key = item['day']
                    elif 'month_number' in item:
                        period_key = item['month_number']
                    else:
                        continue
                    
                    monthly_counts_all[period_key] = item.get('count', 0)
                    monthly_counts_agreed[period_key] = item.get('agreed', 0)
                
                formatted_branches.append({
                    'branch_id': branch.get('branch_id'),
                    'branch_name': branch.get('branch_name'),
                    'monthly_counts_all': monthly_counts_all,
                    'monthly_counts_agreed': monthly_counts_agreed
                })
            
            excel_path = generate_annual_excel_report_for_zone(formatted_branches, year, zone_name, month=month)
        else:
            # Single branch report
            from excel_report_generator import generate_annual_excel_report
            
            # สร้าง dummy trade_data พร้อม agreed flag
            report_data = data.get('monthly_data') or data.get('daily_data', [])
            trade_data = []
            
            if month and data.get('daily_data'):
                # รายเดือน - ใช้ daily_data
                for day_info in report_data:
                    count_all = day_info.get('count', 0)
                    count_agreed = day_info.get('agreed', 0)
                    day_num = day_info.get('day')
                    
                    # สร้าง dummy records สำหรับ agreed
                    for _ in range(count_agreed):
                        timestamp = datetime(year, month, day_num, 12, 0, 0).timestamp() * 1000
                        trade_data.append({
                            'document_date': f'/Date({int(timestamp)})/',
                            'agreed': True
                        })
                    # สร้าง dummy records สำหรับ not agreed
                    for _ in range(count_all - count_agreed):
                        timestamp = datetime(year, month, day_num, 12, 0, 0).timestamp() * 1000
                        trade_data.append({
                            'document_date': f'/Date({int(timestamp)})/',
                            'agreed': False
                        })
            else:
                # รายปี - ใช้ monthly_data
                for month_info in report_data:
                    count_all = int(month_info.get('count', 0) or 0)
                    count_agreed = int(month_info.get('agreed', 0) or 0)
                    month_num = month_info.get('month_number')
                    
                    if not month_num:
                        continue
                    month_num = int(month_num)
                    
                    # สร้าง dummy records สำหรับ agreed
                    for _ in range(count_agreed):
                        timestamp = datetime(year, month_num, 15).timestamp() * 1000
                        trade_data.append({
                            'document_date': f'/Date({int(timestamp)})/',
                            'agreed': True
                        })
                    # สร้าง dummy records สำหรับ not agreed
                    not_agreed_count = count_all - count_agreed
                    for _ in range(max(0, not_agreed_count)):
                        timestamp = datetime(year, month_num, 15).timestamp() * 1000
                        trade_data.append({
                            'document_date': f'/Date({int(timestamp)})/',
                            'agreed': False
                        })
            
            excel_path = generate_annual_excel_report(trade_data, year, data.get('branch_id'), branch_name, month=month)
        
        # ส่งไฟล์กลับ
        from flask import send_file
        response = send_file(
            excel_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=os.path.basename(excel_path)
        )
        
        # ลบไฟล์ชั่วคราวหลังส่ง
        @response.call_on_close
        def cleanup():
            try:
                os.remove(excel_path)
                print(f"🗑️ Removed temp file: {excel_path}")
            except:
                pass
        
        return response
        
    except Exception as e:
        print(f"❌ Error generating Excel from data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


@app.route('/api/health')
def health_check():
    token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
    is_token_set = token and token != 'YOUR_CHANNEL_ACCESS_TOKEN'
    return jsonify({
        'status': 'ok', 
        'version': 'v2-fix-hashlib-and-webhook',
        'line_token_configured': is_token_set, 
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/annual-report-excel-v2')
def get_annual_report_excel_v2():
    """API endpoint สำหรับ Export รายงานรายปี/รายเดือนเป็น Excel"""
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int) # รับค่าเดือน (ถ้ามี)
        branch_id = request.args.get('branchId', '')
        zone_id = request.args.get('zoneId', '')
        session_id = request.args.get('sessionId', '')
        
        if not year:
            return jsonify({'error': 'กรุณาระบุปี'}), 400
        
        # ตรวจสอบปี
        current_year = datetime.now().year
        if year < 2020 or year > current_year + 1:
            return jsonify({'error': f'ปีต้องอยู่ระหว่าง 2020-{current_year + 1}'}), 400
        
        # ถ้าเลือก Zone ให้ดึงข้อมูลทุกสาขาใน Zone
        if zone_id:
            zone = find_zone_by_name(zone_id)  # ใช้ zone_id เป็น zone_name
            if not zone:
                # ลองหาจาก zones list
                zones = load_zones_data()
                zone = next((z for z in zones if z['zone_id'] == zone_id), None)
            
            if not zone:
                return jsonify({'error': f'ไม่พบ Zone: {zone_id}'}), 404
            
            branch_ids = zone['branch_ids']
            print(f"📊 Generating Excel for year {year}, zone {zone['zone_name']} ({len(branch_ids)} branches)")
        else:
            branch_ids = [branch_id] if branch_id else []
            print(f"📊 Generating Excel for year {year}, branch {branch_id or 'all'}")
        
        # คำนวณวันที่เริ่มต้นและสิ้นสุด
        if month:
            # กรณีเลือกเดือน: วันที่ 1 ถึงวันสุดท้ายของเดือนนั้น
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"01/{month:02d}/{year}"
            date_end = f"{last_day}/{month:02d}/{year}"
            print(f"📊 Generating Monthly Excel for {month:02d}/{year}")
        else:
            # กรณีทั้งปี: 1 ม.ค. ถึง 31 ธ.ค.
            date_start = f"01/01/{year}"
            date_end = f"31/12/{year}"
            print(f"📊 Generating Annual Excel for year {year}")
        
        # ดึงข้อมูลทั้งปี
        all_data = []
        
        # ถ้าเป็น Zone ให้ดึงข้อมูลทุกสาขา
        if zone_id and 'branch_ids' in locals():
            for bid in branch_ids:
                # แปลง Sequential ID เป็น Real ID
                real_bid = str(bid)
                branch_info = find_branch_by_sequential_id(bid)
                if branch_info:
                    real_id = get_real_branch_id(branch_info)
                    if real_id:
                        real_bid = real_id
                
                filters = {
                    'date_start': date_start,
                    'date_end': date_end,
                    'sale_code': '',
                    'customer_sign': '',
                    'session_id': session_id,
                    'branch_id': real_bid
                }
                
                start = 0
                length = 1000
                max_items = 50000
                
                while len(all_data) < max_items:
                    data = fetch_data_with_retry(start=start, length=length, **filters)
                    
                    if 'error' in data:
                        print(f"⚠️ Error fetching branch {bid}: {data['error']}")
                        break
                    
                    batch_data = data.get('data', [])
                    if not batch_data:
                        break
                    
                    all_data.extend(batch_data)
                    
                    total = data.get('recordsFiltered', 0)
                    if len(all_data) >= total or len(batch_data) < length:
                        break
                    
                    start += length
                
                print(f"   Branch {bid}: {len(all_data)} records so far")
        else:
            # ดึงข้อมูลสาขาเดียวหรือทุกสาขา
            
            # แปลง Sequential ID เป็น Real ID
            real_branch_id = branch_id
            branch_info = None
            
            if branch_id:
                branch_info = find_branch_by_sequential_id(branch_id)
                if branch_info:
                    real_id = get_real_branch_id(branch_info)
                    if real_id:
                        real_branch_id = real_id
            
            filters = {
                'date_start': date_start,
                'date_end': date_end,
                'sale_code': '',
                'customer_sign': '',
                'session_id': session_id,
                'branch_id': real_branch_id if real_branch_id else None
            }
            
            start = 0
            length = 1000
            max_items = 50000
            
            while len(all_data) < max_items:
                data = fetch_data_with_retry(start=start, length=length, **filters)
                
                if 'error' in data:
                    return jsonify({'error': f'ไม่สามารถดึงข้อมูลได้: {data["error"]}'}), 500
                
                batch_data = data.get('data', [])
                if not batch_data:
                    break
                
                all_data.extend(batch_data)
                print(f"   Fetched {len(all_data)} records...")
                
                total = data.get('recordsFiltered', 0)
                if len(all_data) >= total or len(batch_data) < length:
                    break
                
                start += length
        
        if not all_data:
            debug_info = {
                'year': year,
                'branch_id': branch_id,
                'zone_id': zone_id,
                'real_branch_id': real_branch_id if 'real_branch_id' in locals() else 'N/A',
                'filters': filters,
                'session_provided': bool(session_id)
            }
            return jsonify({
                'success': False, 
                'error': f'ไม่พบข้อมูลการขายในปี {year} (No Data Found)',
                'debug': debug_info
            }), 200
        
        # สร้าง Excel Report
        if zone_id and 'zone' in locals() and 'branch_ids' in locals():
            # สร้างรายงาน Zone แยกตามสาขา
            from excel_report_generator import generate_annual_excel_report_for_zone
            import re
            from collections import defaultdict
            
            # จัดกลุ่มข้อมูลตามสาขา
            branches_data = []
            for bid in branch_ids:
                branch = find_branch_by_sequential_id(str(bid))
                branch_name = branch['branch_name'] if branch else f"สาขา {bid}"
                
                # นับเทรดแต่ละเดือนของสาขานี้
                monthly_counts = defaultdict(int)
                for item in all_data:
                    # ตรวจสอบว่า item นี้เป็นของสาขาไหน (ถ้ามี branch_id ใน item)
                    item_branch = item.get('branch_id') or item.get('BRANCH_ID')
                    if str(item_branch) == str(bid):
                        doc_date = item.get('document_date', '')
                        if doc_date and doc_date.startswith('/Date('):
                            timestamp_match = re.search(r'/Date\((\d+)\)/', doc_date)
                            if timestamp_match:
                                timestamp = int(timestamp_match.group(1)) / 1000
                                date_obj = datetime.fromtimestamp(timestamp)
                                if date_obj.year == year:
                                    if month:
                                        if date_obj.month == month:
                                            monthly_counts[date_obj.day] += 1
                                    else:
                                        monthly_counts[date_obj.month] += 1
                
                branches_data.append({
                    'branch_id': str(bid),
                    'branch_name': branch_name,
                    'monthly_counts': dict(monthly_counts)
                })
            
            excel_path = generate_annual_excel_report_for_zone(branches_data, year, zone['zone_name'], month=month)
        else:
            # สร้างรายงานสาขาเดียว
            branch_name = None
            if branch_id:
                branch = find_branch_by_sequential_id(branch_id)
                if branch:
                    branch_name = branch['branch_name']
            
            excel_path = generate_annual_excel_report(all_data, year, branch_id, branch_name)
        
        if not os.path.exists(excel_path):
            return jsonify({'error': 'File generation failed'}), 500
            
        file_size = os.path.getsize(excel_path)
        print(f"📦 Generated Excel size: {file_size} bytes")

        # อ่านไฟล์ลงหน่วยความจำเพื่อส่งกลับและลบไฟล์ทันที (เลี่ยงปัญหา File Lock/Delete Race Condition)
        import io
        return_data = io.BytesIO()
        with open(excel_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        print(f"📦 Buffered size: {return_data.getbuffer().nbytes} bytes")
        
        # ลบไฟล์ต้นฉบับ
        os.remove(excel_path)
        
        from flask import send_file
        return send_file(
            return_data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=os.path.basename(excel_path)
        )

    except Exception as e:
        print(f"❌ Error generating Excel from data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/annual-report-excel-from-data', methods=['POST'])
def generate_annual_excel_from_data():
    """สร้าง Excel จากข้อมูลที่ส่งมาจาก Frontend (ไม่ต้องดึงใหม่)"""
    try:
        data = request.get_json()
        
        # ตรวจสอบว่าเป็นรายงานแบบไหน
        # ถ้ามี branches_data แสดงว่าเป็น Zone Report (หรือ All Branches)
        if 'branches_data' in data and data['branches_data']:
            from excel_report_generator import generate_annual_excel_report_for_zone
            
            # ปรับปรุง data ให้ตรง format ที่ generator ต้องการ
            formatted_branches = []
            for b in data['branches_data']:
                counts = {}
                monthly_data = b.get('monthly_data', [])
                
                for item in monthly_data:
                    # ถ้าเป็นรายปี
                    if 'month_number' in item:
                        counts[int(item['month_number'])] = int(item['count'])
                    elif 'day' in item:
                        # ถ้าเป็นรายเดือน
                        counts[int(item['day'])] = int(item['count'])
                
                formatted_branches.append({
                    'branch_id': b['branch_id'],
                    'branch_name': b['branch_name'],
                    'monthly_counts': counts
                })
            
            excel_path = generate_annual_excel_report_for_zone(
                formatted_branches, 
                data['year'], 
                data.get('zone_name', 'Report'),
                month=data.get('month')
            )
            
        else:
            # รายงานสาขาเดียว (หรือแบบที่ส่ง raw processed data มา)
            # data ในที่นี้คือ { year, branch_id, monthly_data: [...], ... }
            
            costs = {}
            monthly_data = data.get('daily_data', data.get('monthly_data', []))
            
            for item in monthly_data:
                if 'month_number' in item:
                    costs[int(item['month_number'])] = int(item['count'])
                elif 'day' in item:
                    costs[int(item['day'])] = int(item['count'])
            
            branch_name = data.get('branch_name') or str(data.get('branch_id', 'Unknown'))

            formatted_branches = [{
                'branch_id': data.get('branch_id', 'Unknown'),
                'branch_name': branch_name,
                'monthly_counts': costs
            }]
            
            from excel_report_generator import generate_annual_excel_report_for_zone
            excel_path = generate_annual_excel_report_for_zone(
                formatted_branches, 
                data['year'], 
                branch_name, 
                month=data.get('month')
            )

        if not os.path.exists(excel_path):
            return jsonify({'error': 'File generation failed'}), 500
            
        file_size = os.path.getsize(excel_path)
        print(f"📦 Generated Excel size: {file_size} bytes")

        # อ่านไฟล์ลงหน่วยความจำเพื่อส่งกลับและลบไฟล์ทันที
        import io
        return_data = io.BytesIO()
        with open(excel_path, 'rb') as f:
            return_data.write(f.read())
        return_data.seek(0)
        
        os.remove(excel_path)
        
        from flask import send_file
        return send_file(
            return_data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=os.path.basename(excel_path)
        )

    except Exception as e:
        print(f"❌ Error generating Excel from data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# @app.route('/api/admin/update-branches', methods=['POST']) # DEPRECATED
def update_branches_data_deprecated():
    """API endpoint สำหรับอัปเดตข้อมูลสาขา (Hybrid)"""
    try:
        data = request.get_json()
        session_id = data.get('sessionId')
        
        if not session_id:
            return jsonify({'success': False, 'error': 'กรุณาระบุ Session ID'}), 400
            
        print(f"🔄 Updating branches with Session ID: {session_id[:10]}...")
        
        # 1. เรียก API ดึงข้อมูลสาขา
        url = 'https://eve.techswop.com/TI/inventory/stock-view-list.aspx/GetDropDownBranch'
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json; charset=utf-8',
            'Origin': 'https://eve.techswop.com',
            'Referer': 'https://eve.techswop.com/ti/index.aspx',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': f'ASP.NET_SessionId={session_id}'
        }
        
        payload = {} # Empty payload often works for simple Get calls in ASP.NET page methods
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
             return jsonify({'success': False, 'error': f'API Error: {response.status_code}'}), 500
             
        result = response.json()
        
        # ตรวจสอบโครงสร้างข้อมูลที่ได้
        branches_list = []
        if 'd' in result:
             # กรณี ASP.NET response ปติที่จะอยู่ใน 'd'
             raw_data = result['d']
             # อาจจะเป็น string JSON หรือ array เลย
             if isinstance(raw_data, str):
                 try:
                     branches_list = json.loads(raw_data)
                 except:
                     return jsonify({'success': False, 'error': 'Cannot parse "d" string'}), 500
             elif isinstance(raw_data, list):
                 branches_list = raw_data
             elif isinstance(raw_data, dict) and 'data' in raw_data:
                 branches_list = raw_data['data']
        elif isinstance(result, list):
            branches_list = result
        else:
             return jsonify({'success': False, 'error': 'Unknown API response format', 'debug': str(result)[:200]}), 500
             
        if not branches_list:
            print(f"❌ Raw API Response: {json.dumps(result, ensure_ascii=False)[:1000]}")
            return jsonify({
                'success': False, 
                'error': 'No branches found in response',
                'raw_response': str(result)[:500]
            }), 500
            
        print(f"✅ Fetched {len(branches_list)} branches")
        
        # 2. แปลงข้อมูลให้เป็น Format ที่เราใช้
        formatted_branches = []
        for b in branches_list:
            # พยายามหา field ที่ถูกต้อง
            bid = b.get('BRANCH_ID') or b.get('branch_id') or b.get('Value') or b.get('Id')
            bname = b.get('BRANCH_NAME') or b.get('branch_name') or b.get('Text') or b.get('Name')
            
            if bid and bname:
                formatted_branches.append({
                    "branch_id": bid,
                    "branch_name": bname
                })
        
        if not formatted_branches:
             return jsonify({'success': False, 'error': 'Could not extract valid branch data'}), 500

        # 3. พยายามอัปเดตไฟล์ (อาจจะพังบน Vercel เพราะ Read-only)
        try:
            # 3.1 อัปเดตไฟล์ extracted_branches.json
            json_path = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(formatted_branches, f, ensure_ascii=False, indent=2)
                
            # 3.2 อัปเดตไฟล์ static/branches-data.js
            js_path = os.path.join(os.path.dirname(__file__), 'static', 'branches-data.js')
            js_content = f"""// ข้อมูลสาขาทั้งหมด {len(formatted_branches)} สาขา (Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
const BRANCHES_DATA = {json.dumps(formatted_branches, ensure_ascii=False, indent=None)};
"""
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write(js_content)
                
            return jsonify({
                'success': True,
                'count': len(formatted_branches),
                'message': f'อัปเดตข้อมูลสำเร็จ! ({len(formatted_branches)} สาขา)'
            })
            
        except OSError as e:
            # กรณี Vercel Read-Only
            print(f"⚠️ Read-only filesystem detected: {e}")
            return jsonify({
                'success': True,
                'count': len(formatted_branches),
                'message': f'ดึงข้อมูลสำเร็จ! ({len(formatted_branches)} สาขา) <br>⚠️ บน Server เขียนไฟล์ไม่ได้ กรุณา Copy JSON ด้านล่างไปส่งให้ Developer:',
                'manual_copy_needed': True,
                'branches_json': json.dumps(formatted_branches, ensure_ascii=False)
            })

    except Exception as e:
        print(f"❌ Error updating branches: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


# ==========================================
# New Branch API Endpoints (DB-backed)
# ==========================================

@app.route('/api/branches', methods=['GET'])
def get_all_branches():
    """API endpoint สำหรับดึงรายชื่อสาขา (จาก Database)"""
    try:
        # 1. พยายามดึงจาก DB
        branches = get_branches_from_db()
        
        # 2. ถ้าไม่มีใน DB ให้ลองดึงจากไฟล์เดิม (Fallback)
        if not branches:
            print("⚠️ No branches in DB, checking static file...")
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        branches = json.load(f)
            except Exception as e:
                print(f"⚠️ File fallback failed: {e}")
        
        return jsonify({
            'success': True,
            'branches': branches,
            'source': 'database' if branches else 'static_file'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/system-settings', methods=['GET', 'POST'])
def manage_admin_settings():
    """API สำหรับจัดการการตั้งค่า (Eve Credentials) - GET/POST"""
    if request.method == 'GET':
        try:
            username = get_system_setting('eve_username')
            password = get_system_setting('eve_password')
            
            return jsonify({
                'success': True,
                'eve_username': username if username else '',
                'eve_password_set': bool(password) # Don't send actual password back for security, just flag
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # POST Method (Save)
    try:
        data = request.get_json()
        eve_username = data.get('eve_username')
        eve_password = data.get('eve_password')
        
        # Check DB connection first
        conn = get_db_connection()
        if not conn:
             return jsonify({'success': False, 'error': 'Database Connection Failed: Check POSTGRES_URL_NON_POOLING'}), 500
        conn.close()
        
        if eve_username is not None: # Allow saving empty string to clear
            if not save_system_setting('eve_username', eve_username):
                return jsonify({'success': False, 'error': 'Failed to save username to DB'}), 500
                
        if eve_password: # Only update password if provided (non-empty)
            if not save_system_setting('eve_password', eve_password):
                return jsonify({'success': False, 'error': 'Failed to save password to DB'}), 500
            
        return jsonify({'success': True, 'message': 'Settings saved to Database'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/update-branches', methods=['POST'])
def update_branches_data():
    """API endpoint สำหรับอัปเดตข้อมูลสาขา (Hybrid)"""
    try:
        # ใช้ auto-login session แทนการรับจาก client
        session_id = get_eve_session()
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Auto-Login ล้มเหลว กรุณาตรวจสอบ Eve Credentials'}), 400
            
        # ใช้ Helper Function ใหม่ที่เขียนข้อมูลลง DB
        print(f"🔄 Updating branches via DB Helper...")
        success, count = trigger_branch_update(session_id)
        
        if success:
             return jsonify({
                'success': True, 
                'message': f'อัปเดตสาขาเรียบร้อย ({count} สาขา)',
                'count': count
            })
        else:
             return jsonify({'success': False, 'error': 'Failed to update branches from external API'}), 500

    except Exception as e:
        print(f"❌ Error in update_branches_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# Auto-Cancel Scheduler System
# ============================================================

scheduler = BackgroundScheduler(timezone='Asia/Bangkok')

def get_auto_cancel_config():
    """ดึง config auto-cancel จาก DB"""
    try:
        conn = get_db_connection()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT * FROM auto_cancel_config ORDER BY id LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            columns = ['id', 'enabled', 'schedule_time', 'branch_ids', 'emp_code', 'emp_name',
                       'emp_phone', 'cancel_type', 'reason_cancel', 'description',
                       'telegram_bot_token', 'telegram_chat_id', 'updated_at']
            return dict(zip(columns, row))
        return None
    except Exception as e:
        print(f"❌ Error getting auto-cancel config: {e}")
        return None

def save_auto_cancel_config(config):
    """บันทึก config auto-cancel ลง DB"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        
        # ลบ config เก่า แล้ว insert ใหม่ (single row)
        cur.execute("DELETE FROM auto_cancel_config")
        cur.execute("""
            INSERT INTO auto_cancel_config 
            (enabled, schedule_time, branch_ids, emp_code, emp_name, emp_phone,
             cancel_type, reason_cancel, description, telegram_bot_token, telegram_chat_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            config.get('enabled', False),
            config.get('schedule_time', '23:00'),
            config.get('branch_ids', ''),
            config.get('emp_code', ''),
            config.get('emp_name', ''),
            config.get('emp_phone', ''),
            config.get('cancel_type', '1'),
            config.get('reason_cancel', '1'),
            config.get('description', '-'),
            config.get('telegram_bot_token', ''),
            config.get('telegram_chat_id', '')
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error saving auto-cancel config: {e}")
        return False

def save_auto_cancel_log(log_data):
    """บันทึก log การรัน auto-cancel"""
    try:
        conn = get_db_connection()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO auto_cancel_log 
            (branch_ids, total_found, total_cancelled, total_skipped, total_failed, details, telegram_sent)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            log_data.get('branch_ids', ''),
            log_data.get('total_found', 0),
            log_data.get('total_cancelled', 0),
            log_data.get('total_skipped', 0),
            log_data.get('total_failed', 0),
            log_data.get('details', ''),
            log_data.get('telegram_sent', False)
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error saving auto-cancel log: {e}")

def send_telegram_notification(bot_token, chat_id, message):
    """ส่งแจ้งเตือน Telegram"""
    try:
        if not bot_token or not chat_id:
            print("⚠️ Telegram not configured, skipping notification")
            return False
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        response = requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        })
        result = response.json()
        if result.get('ok'):
            print("✅ Telegram notification sent")
            return True
        else:
            print(f"❌ Telegram error: {result.get('description')}")
            return False
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def run_auto_cancel():
    """ฟังก์ชันหลัก: ยกเลิกรายการเทรดอัตโนมัติ"""
    print("\n" + "="*60)
    print(f"⏰ Auto-Cancel Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    config = get_auto_cancel_config()
    if not config or not config.get('enabled'):
        print("⚠️ Auto-cancel is disabled, skipping")
        return
    
    branch_ids_str = config.get('branch_ids', '')
    if not branch_ids_str:
        print("⚠️ No branches configured, skipping")
        return
    
    branch_ids = [b.strip() for b in branch_ids_str.split(',') if b.strip()]
    emp_code = config.get('emp_code', '')
    emp_name = config.get('emp_name', '')
    emp_phone = config.get('emp_phone', '')
    cancel_type = config.get('cancel_type', '1')
    reason_cancel = config.get('reason_cancel', '1')
    description = config.get('description', '-')
    
    # Eve session
    session_id = get_eve_session()
    if not session_id:
        print("❌ Cannot get Eve session, aborting")
        return
    
    eve_cookies = {'ASP.NET_SessionId': session_id}
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15'
    }
    
    today = datetime.now().strftime('%d/%m/%Y')
    total_found = 0
    total_cancelled = 0
    total_skipped = 0
    total_failed = 0
    details_list = []
    
    for branch_id in branch_ids:
        print(f"\n🔍 Processing branch: {branch_id}")
        try:
            # ดึงข้อมูลเทรดวันนี้
            result = fetch_data_from_api(
                start=0, length=200,
                branch_id=branch_id,
                date_start=today,
                date_end=today
            )
            
            if not result or 'data' not in result:
                print(f"  ⚠️ No data for branch {branch_id}")
                details_list.append(f"⚠️ Branch {branch_id}: ไม่มีข้อมูล")
                continue
            
            items = result['data']
            
            # Debug: แสดง field names ของ item แรก
            if items:
                first_item = items[0]
                print(f"  🔑 First item keys: {list(first_item.keys())[:10]}")
                # แสดงสถานะทั้งหมดที่เจอ
                all_statuses = set(item.get('BIDDING_STATUS_NAME', 'N/A') for item in items)
                print(f"  📋 All statuses found: {all_statuses}")
            
            # กรองเฉพาะ "รอผู้ขายยืนยันราคา"
            pending_items = [item for item in items 
                           if item.get('BIDDING_STATUS_NAME') == 'รอผู้ขายยืนยันราคา']
            
            print(f"  📊 Found {len(pending_items)}/{len(items)} items with status 'รอผู้ขายยืนยันราคา'")
            total_found += len(pending_items)
            
            for item in pending_items:
                # ลอง field names หลายแบบ
                trade_in_id = item.get('trade_in_id') or item.get('TRADE_IN_ID') or item.get('tradeInId', '')
                doc_no = item.get('document_no') or item.get('DOCUMENT_NO') or item.get('documentNo', str(trade_in_id))
                
                print(f"  🔄 Processing: trade_in_id={trade_in_id}, doc_no={doc_no}")
                
                try:
                    # Pre-check
                    check_resp = requests.post(
                        'https://eve.techswop.com/ti/index.aspx/CheckAllowCancel',
                        headers=headers,
                        json={"trade_in_id": int(trade_in_id)},
                        cookies=eve_cookies
                    )
                    
                    if check_resp.status_code == 200:
                        check_result = check_resp.json()
                        d = check_result.get('d', {})
                        can_cancel = d.get('is_success', False) or d.get('allow_cancel', False) or d.get('success', False)
                        
                        if not can_cancel:
                            total_skipped += 1
                            msg = d.get('message', 'ไม่อนุญาต')
                            if isinstance(msg, list):
                                msg = ', '.join(msg)
                            details_list.append(f"⏭️ {doc_no}: {msg}")
                            print(f"  ⏭️ Skip {doc_no}: {msg}")
                            continue
                    else:
                        total_skipped += 1
                        details_list.append(f"⏭️ {doc_no}: check failed HTTP {check_resp.status_code}")
                        continue
                    
                    # ยกเลิกจริง
                    cancel_payload = {
                        "param": {
                            "TRADE_IN_ID": str(trade_in_id),
                            "EMP_CODE": emp_code,
                            "EMP_FULL_NAME": emp_name,
                            "EMP_PHONE_NUMBER": emp_phone,
                            "REASON": description,
                            "CANCEL_STATUS": cancel_type,
                            "REASON_CANCEL": reason_cancel,
                            "DESCRIPTION": description
                        }
                    }
                    
                    cancel_resp = requests.post(
                        'https://eve.techswop.com/ti/index.aspx/CancelData',
                        headers=headers,
                        json=cancel_payload,
                        cookies=eve_cookies
                    )
                    
                    if cancel_resp.status_code == 200:
                        cancel_result = cancel_resp.json()
                        d = cancel_result.get('d', {})
                        is_success = d.get('is_success', False) or d.get('success', False)
                        
                        if is_success:
                            total_cancelled += 1
                            details_list.append(f"✅ {doc_no}: ยกเลิกสำเร็จ")
                            print(f"  ✅ Cancelled {doc_no}")
                        else:
                            total_failed += 1
                            msg = d.get('message', 'ไม่ทราบสาเหตุ')
                            if isinstance(msg, list):
                                msg = ', '.join(msg)
                            details_list.append(f"❌ {doc_no}: {msg}")
                            print(f"  ❌ Failed {doc_no}: {msg}")
                    else:
                        total_failed += 1
                        details_list.append(f"❌ {doc_no}: HTTP {cancel_resp.status_code}")
                
                except Exception as e:
                    total_failed += 1
                    details_list.append(f"❌ {doc_no}: {str(e)}")
                    print(f"  ❌ Error {doc_no}: {e}")
                
                # Delay ระหว่างรายการ
                import time
                time.sleep(0.5)
        
        except Exception as e:
            print(f"  ❌ Error processing branch {branch_id}: {e}")
            details_list.append(f"❌ Branch {branch_id}: {str(e)}")
    
    # สรุปผล
    summary = f"""⏰ <b>Auto-Cancel Report</b>
📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}
🏪 สาขา: {', '.join(branch_ids)}
👤 พนักงาน: {emp_name} ({emp_code})

📊 <b>สรุป:</b>
🔍 พบทั้งหมด: {total_found} รายการ
✅ ยกเลิกสำเร็จ: {total_cancelled}
⏭️ ข้าม (ยกเลิกไปแล้ว): {total_skipped}
❌ ล้มเหลว: {total_failed}"""
    
    if details_list:
        summary += "\n\n📋 <b>รายละเอียด:</b>\n" + "\n".join(details_list[:20])
        if len(details_list) > 20:
            summary += f"\n... และอีก {len(details_list) - 20} รายการ"
    
    print(f"\n📊 Summary: Found={total_found}, Cancelled={total_cancelled}, Skipped={total_skipped}, Failed={total_failed}")
    
    # ส่ง Telegram
    telegram_sent = send_telegram_notification(
        config.get('telegram_bot_token', ''),
        config.get('telegram_chat_id', ''),
        summary
    )
    
    # บันทึก log
    save_auto_cancel_log({
        'branch_ids': branch_ids_str,
        'total_found': total_found,
        'total_cancelled': total_cancelled,
        'total_skipped': total_skipped,
        'total_failed': total_failed,
        'details': '\n'.join(details_list[:50]),
        'telegram_sent': telegram_sent
    })
    
    print(f"⏰ Auto-Cancel Completed\n")

def start_auto_cancel_scheduler():
    """เริ่ม scheduler จาก config ใน DB"""
    try:
        config = get_auto_cancel_config()
        if not config or not config.get('enabled'):
            print("⏰ Auto-cancel scheduler: disabled")
            return
        
        schedule_time = config.get('schedule_time', '23:00')
        hour, minute = schedule_time.split(':')
        
        # ลบ job เก่า (ถ้ามี)
        if scheduler.get_job('auto_cancel'):
            scheduler.remove_job('auto_cancel')
        
        scheduler.add_job(
            run_auto_cancel,
            'cron',
            hour=int(hour),
            minute=int(minute),
            id='auto_cancel',
            replace_existing=True
        )
        
        if not scheduler.running:
            scheduler.start()
            atexit.register(lambda: scheduler.shutdown())
        
        print(f"⏰ Auto-cancel scheduler: enabled at {schedule_time}")
    except Exception as e:
        print(f"❌ Error starting auto-cancel scheduler: {e}")

def reschedule_auto_cancel():
    """Reschedule job เมื่อ config เปลี่ยน"""
    try:
        # ลบ job เก่า
        if scheduler.get_job('auto_cancel'):
            scheduler.remove_job('auto_cancel')
        
        config = get_auto_cancel_config()
        if not config or not config.get('enabled'):
            print("⏰ Auto-cancel scheduler: disabled (removed job)")
            return
        
        schedule_time = config.get('schedule_time', '23:00')
        hour, minute = schedule_time.split(':')
        
        scheduler.add_job(
            run_auto_cancel,
            'cron',
            hour=int(hour),
            minute=int(minute),
            id='auto_cancel',
            replace_existing=True
        )
        
        if not scheduler.running:
            scheduler.start()
            atexit.register(lambda: scheduler.shutdown())
        
        print(f"⏰ Auto-cancel rescheduled to {schedule_time}")
    except Exception as e:
        print(f"❌ Error rescheduling auto-cancel: {e}")

# API Routes for Auto-Cancel Config
@app.route('/api/admin/auto-cancel-config', methods=['GET', 'POST'])
def manage_auto_cancel_config():
    """API สำหรับจัดการ config auto-cancel"""
    if request.method == 'GET':
        config = get_auto_cancel_config()
        if config:
            config['updated_at'] = str(config.get('updated_at', ''))
            return jsonify({'success': True, 'config': config})
        return jsonify({'success': True, 'config': None})
    
    # POST - save config
    try:
        data = request.get_json()
        success = save_auto_cancel_config(data)
        if success:
            reschedule_auto_cancel()
            return jsonify({'success': True, 'message': 'บันทึกสำเร็จ'})
        return jsonify({'success': False, 'error': 'บันทึกไม่สำเร็จ'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/auto-cancel-test', methods=['POST'])
def test_auto_cancel():
    """ทดสอบรัน auto-cancel ทันที"""
    try:
        import threading
        thread = threading.Thread(target=run_auto_cancel)
        thread.start()
        return jsonify({'success': True, 'message': 'เริ่มรัน auto-cancel แล้ว ดูผลลัพธ์ใน Telegram และ log'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/auto-cancel-logs', methods=['GET'])
def get_auto_cancel_logs():
    """ดึง log การรัน auto-cancel"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'DB connection failed'}), 500
        cur = conn.cursor()
        cur.execute("SELECT * FROM auto_cancel_log ORDER BY run_at DESC LIMIT 10")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        logs = []
        columns = ['id', 'run_at', 'branch_ids', 'total_found', 'total_cancelled',
                   'total_skipped', 'total_failed', 'details', 'telegram_sent']
        for row in rows:
            log = dict(zip(columns, row))
            log['run_at'] = str(log['run_at'])
            logs.append(log)
        
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# เริ่ม scheduler เมื่อ app start (เฉพาะ non-debug reloader)
import os as _os
if _os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    start_auto_cancel_scheduler()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
