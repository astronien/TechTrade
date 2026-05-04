from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_file
from functools import wraps
import requests
import json
from datetime import datetime, timedelta
import pytz
import os
import secrets
import hashlib
import atexit
import os as _os  # Moved to top for safety
from line_bot_handler import handle_line_message, verify_line_signature, send_line_reply
from turso_handler import TursoHandler

# Debug Log to Database (Persistent)
def log_debug(msg):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        final_msg = f"[{timestamp}] {msg}"
        print(final_msg) # Still print to console just in case
        
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debug_logs (
                    id SERIAL PRIMARY KEY,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("INSERT INTO debug_logs (message) VALUES (%s)", (final_msg,))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"❌ Error logging to DB: {e}")



app = Flask(__name__)
from flask_cors import CORS
CORS(app) # อนุญาตให้ทุก Domain เข้าถึงได้ (สามารถกำหนดเฉพาะ Domain ได้ภายหลัง)

# Register Turso API Blueprint
from api_turso import turso_api
app.register_blueprint(turso_api)

@app.route('/turso-stats')
def turso_dashboard():
    return render_template('turso_dashboard.html')

@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')

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
        
        # สร้างตาราง auto_export_config
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_export_config (
                id SERIAL PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                schedule_time VARCHAR(5) DEFAULT '00:05',
                zone_ids JSONB DEFAULT '[]',
                gdrive_folder_id VARCHAR(255) DEFAULT '',
                gdrive_credentials TEXT DEFAULT '',
                max_files_per_zone INTEGER DEFAULT 365,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # สร้างตาราง auto_export_log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_export_log (
                id SERIAL PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                zone_id VARCHAR(255) DEFAULT '',
                zone_name VARCHAR(255) DEFAULT '',
                date_exported VARCHAR(10) DEFAULT '',
                total_records INTEGER DEFAULT 0,
                file_name VARCHAR(500) DEFAULT '',
                gdrive_file_id VARCHAR(255) DEFAULT '',
                status VARCHAR(20) DEFAULT 'success',
                error_message TEXT DEFAULT '',
                duration_seconds FLOAT DEFAULT 0
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
            data = row['branch_data']
            # JSONB ควรจะ auto-parse แต่ถ้าเป็น string ให้ parse เอง
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    print(f"⚠️ branch_data is a string but not valid JSON")
                    return []
            print(f"📦 Loaded {len(data) if isinstance(data, list) else 0} branches from DB")
            return data if isinstance(data, list) else []
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

def get_supersale_branch_ids():
    """ดึงรายชื่อ branch_id ที่มี supersale จาก DB"""
    try:
        value = get_system_setting('supersale_branch_ids')
        if value:
            return json.loads(value)
        return []
    except Exception as e:
        print(f"⚠️ Error loading supersale config: {e}")
        return []

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
            'Cookie': f'ASP.NET_SessionId={session_id}',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        response = requests.post(url, headers=headers, json={}, timeout=30, allow_redirects=False)
        
        print(f"📥 Branch API Response Status: {response.status_code}")
        print(f"📥 Branch API Response Headers: {dict(response.headers)}")
        
        # ตรวจสอบว่าถูก redirect ไปหน้า login หรือไม่
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_url = response.headers.get('Location', '')
            print(f"⚠️ Branch API redirected to: {redirect_url}")
            print(f"❌ Session expired or invalid! Need to re-login.")
            return False, 0
        
        if response.status_code != 200:
            print(f"❌ Branch API returned HTTP {response.status_code}")
            print(f"❌ Response body (first 500 chars): {response.text[:500]}")
            return False, 0
        
        # ตรวจสอบว่า response เป็น JSON หรือไม่
        content_type = response.headers.get('Content-Type', '')
        if 'json' not in content_type and 'javascript' not in content_type:
            print(f"⚠️ Response Content-Type is not JSON: {content_type}")
            print(f"⚠️ Response body (first 500 chars): {response.text[:500]}")
            # อาจจะเป็น HTML login page
            if 'login' in response.text.lower() or 'เข้าสู่ระบบ' in response.text:
                print(f"❌ Session expired! Got login page instead of branch data.")
                return False, 0
        
        try:
            result = response.json()
        except Exception as json_err:
            print(f"❌ Failed to parse JSON response: {json_err}")
            print(f"❌ Response body (first 500 chars): {response.text[:500]}")
            return False, 0
            
        print(f"📦 Branch API Result keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        
        branches_list = []
        
        # Extract Data
        if isinstance(result, dict) and 'd' in result:
            raw_data = result['d']
            print(f"📦 'd' field type: {type(raw_data).__name__}, length: {len(raw_data) if hasattr(raw_data, '__len__') else 'N/A'}")
            if isinstance(raw_data, str):
                try:
                    branches_list = json.loads(raw_data)
                    print(f"📦 Parsed 'd' string -> {len(branches_list)} items")
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse 'd' as JSON string: {e}")
                    print(f"❌ 'd' content (first 300 chars): {raw_data[:300]}")
            elif isinstance(raw_data, list):
                branches_list = raw_data
                print(f"📦 'd' is already a list with {len(branches_list)} items")
            elif isinstance(raw_data, dict) and 'data' in raw_data:
                branches_list = raw_data['data']
                print(f"📦 'd' is a dict, extracted 'data' with {len(branches_list)} items")
            else:
                print(f"⚠️ Unexpected 'd' format: {type(raw_data).__name__}")
                if isinstance(raw_data, dict):
                    print(f"   Keys: {list(raw_data.keys())}")
        elif isinstance(result, list):
            branches_list = result
            print(f"📦 Result is directly a list with {len(branches_list)} items")
        else:
            print(f"⚠️ Unexpected result format. Keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            # ลองดึงข้อมูลจาก key อื่นๆ ที่อาจมี
            if isinstance(result, dict):
                for key in result.keys():
                    if isinstance(result[key], list) and len(result[key]) > 0:
                        branches_list = result[key]
                        print(f"📦 Found branch data in key '{key}' with {len(branches_list)} items")
                        break
            
        if branches_list:
            # แสดงตัวอย่างข้อมูลแรก
            if len(branches_list) > 0:
                print(f"📦 Sample first branch item: {branches_list[0]}")
                print(f"📦 Sample first branch keys: {list(branches_list[0].keys()) if isinstance(branches_list[0], dict) else type(branches_list[0]).__name__}")
            
            # Format Data
            formatted_branches = []
            for b in branches_list:
                if not isinstance(b, dict):
                    print(f"⚠️ Skipping non-dict item: {b}")
                    continue
                bid = b.get('BRANCH_ID') or b.get('branch_id') or b.get('Value') or b.get('Id') or b.get('value') or b.get('id')
                bname = b.get('BRANCH_NAME') or b.get('branch_name') or b.get('Text') or b.get('Name') or b.get('text') or b.get('name')
                if bid and bname:
                    formatted_branches.append({"branch_id": str(bid), "branch_name": str(bname)})
            
            print(f"📦 Formatted {len(formatted_branches)} branches out of {len(branches_list)} raw items")
            
            # Save to DB
            if formatted_branches:
                saved = save_branches_to_db(formatted_branches)
                if saved:
                    print(f"✅ Branch update complete! {len(formatted_branches)} branches saved to DB")
                    return True, len(formatted_branches)
                else:
                    print(f"❌ Failed to save branches to DB!")
                    return False, 0
            else:
                print(f"⚠️ No branches matched the expected format (need both branch_id and branch_name)")
                if len(branches_list) > 0:
                    print(f"   Available keys in first item: {list(branches_list[0].keys()) if isinstance(branches_list[0], dict) else 'N/A'}")
        else:
            print(f"⚠️ branches_list is empty after extraction")
                    
        return False, 0
    except Exception as e:
        print(f"❌ Trigger update failed: {e}")
        import traceback
        traceback.print_exc()
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
                          doc_ref_number="", promo_code="", customer_sign="0", branch_id=None, **kwargs):
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
    
    # 🛡️ Smart Cache: ตรวจสอบข้อมูลใน Turso ก่อน
    try:
        date_start = filters.get('date_start')
        date_end = filters.get('date_end')
        branch_id = filters.get('branch_id', BRANCH_ID)
        today_str = datetime.now().strftime('%d/%m/%Y')
        
        print(f"🔍 [Fetch] Request for Branch {branch_id} | Range: {date_start} to {date_end}")
        
        if date_start and date_end:
            # 💡 กรณีข้อมูลวันนี้ -> บังคับดึงใหม่
            if date_end == today_str:
                print(f"⏩ [Skip Cache] Date is 'Today' ({today_str}). Bypassing Turso to get Real-time data from Eve.")
            
            # 💡 กรณีข้อมูลย้อนหลัง -> เช็ค Turso
            else:
                print(f"📦 [Check Turso] Searching for historical data in database...")
                turso = TursoHandler()
                # 💡 อนุญาตให้ใช้ Turso ได้แม้จะไม่มี client (ใช้ HTTP Fallback แทน)
                if turso.url and turso.token:
                    # 🔍 แปลง branch_id (Eve ID) เป็น real_branch_id (เช่น 645) สำหรับ Turso
                    turso_branch_id = branch_id
                    try:
                        branch_info = find_branch_by_sequential_id(branch_id)
                        if branch_info and 'branch_name' in branch_info:
                            import re
                            match = re.search(r'ID(\d+)', branch_info['branch_name'])
                            if match:
                                turso_branch_id = match.group(1)
                                if str(turso_branch_id) != str(branch_id):
                                    print(f"🔄 [Turso Map] Mapping Eve ID {branch_id} -> Real ID {turso_branch_id}")
                    except Exception as map_err:
                        print(f"⚠️ [Turso Map Error] {map_err}")

                    sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
                    if turso.is_synced(turso_branch_id, sync_key):
                        cached_data = turso.get_trades(date_start, date_end, branch_id=turso_branch_id)
                        turso.close()
                        
                        if cached_data:
                            print(f"✨ [Success] Found {len(cached_data)} records in Turso for Branch {branch_id}. Returning cached data.")
                            return {
                                'data': cached_data,
                                'recordsTotal': len(cached_data),
                                'recordsFiltered': len(cached_data),
                                'source': 'turso'
                            }
                        else:
                            print(f"📭 [Info] Turso has 'Synced' record but 0 trades found. Returning empty results.")
                            return {'data': [], 'recordsTotal': 0, 'recordsFiltered': 0, 'source': 'turso'}
                    else:
                        print(f"❓ [Cache Miss] No synced records found in Turso for this range. Proceeding to Eve API...")
                    turso.close()
        else:
            print(f"⚠️ [Warning] Date filters missing. Defaulting to Eve API.")
            
    except Exception as cache_err:
        print(f"⚠️ [Error] Smart Cache Exception: {cache_err}. Falling back to Eve API.")

    # 🌐 เรียก Eve API (กรณีไม่มีใน Cache หรือเป็นข้อมูลวันนี้)
    print(f"🌐 [API Call] Requesting fresh data from Eve Techswop API...")
    
    # ... (ส่วนเดิมของ headers และการเรียก API) ...
    
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
    
    # 🛡️ Smart Cache: ลองดึงจาก Turso ก่อนถ้าเป็นข้อมูลย้อนหลัง
    try:
        date_start = filters.get('date_start')
        date_end = filters.get('date_end')
        today_str = datetime.now().strftime('%d/%m/%Y')
        
        # 🛡️ Smart Cache: ลองดึงจาก Turso ก่อนถ้าเป็นข้อมูลย้อนหลัง
        if date_start and date_end:
            today_str = datetime.now().strftime('%d/%m/%Y')
            
            # 💡 ถ้าไม่ใช่ข้อมูลของ "วันนี้" และเคยดึงสำเร็จแล้ว -> ใช้ Turso เลย
            if date_end != today_str:
                turso = TursoHandler()
                if turso.client:
                    sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
                    if turso.is_synced(branch_id, sync_key):
                        cached_data = turso.get_trades(date_start, date_end, branch_id=branch_id)
                        turso.close()
                        print(f"🚀 [Smart Cache] Using verified historical data from Turso for Branch {branch_id}")
                        return {
                            'data': cached_data,
                            'recordsTotal': len(cached_data),
                            'recordsFiltered': len(cached_data)
                        }
                    turso.close()
            else:
                print(f"🔄 [Real-time] Fetching today's data from Eve API for Branch {branch_id}...")
    except Exception as cache_err:
        print(f"⚠️ Smart Cache Error: {cache_err}")

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
            
            # 🚀 Near Real-time Sync to Turso
            try:
                trade_data = data_obj.get('data', [])
                zone_name = filters.get('zone_name', 'Auto-Sync')
                turso = TursoHandler()
                
                # บันทึกรายการเทรด (ถ้ามี) - TursoHandler จะจัดการ Fallback เองภายใน
                if trade_data:
                    turso.insert_trades_batch(trade_data, zone_name)
                
                # 💡 บันทึกประวัติการ Sync (เพื่อให้คราวหน้าจะได้ไม่ต้องดึง API อีก)
                sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
                turso.mark_synced(branch_id, sync_key, len(trade_data))
                
                print(f"   🗄️ Near Real-time Sync: Processed Branch {branch_id} ({len(trade_data)} records)")
                turso.close()
            except Exception as sync_err:
                print(f"   ⚠️ Turso Sync Error (Non-blocking): {sync_err}")

            # Debug: ถ้าไม่มีข้อมูล แสดงรายละเอียดเพิ่มเติม
            if records_filtered == 0:
                print(f"⚠️ DEBUG: No records found!")
                print(f"   - Branch ID used: {branch_id}")
                print(f"   - Date range: {filters.get('date_start')} to {filters.get('date_end')}")
            
            return {
                'data': data_obj.get('data', []),
                'recordsTotal': records_total,
                'recordsFiltered': records_filtered,
                'source': 'eve_api'
            }
        return result
    except Exception as e:
        print(f"❌ API Global Error: {e}")
        return {"error": str(e)}

def fetch_zone_data_batch(branch_ids, date_start, date_end):
    """
    ดึงข้อมูลแบบ Batch สำหรับหลายสาขา (ใช้สำหรับ LINE Bot Zone Reports)
    """
    try:
        if not branch_ids:
            return {}
            
        print(f"🔍 [Batch] Request for {len(branch_ids)} branches | Range: {date_start} to {date_end}")
        
        # 💡 กรณีข้อมูลวันนี้ -> บังคับดึงใหม่ทีละสาขา (เพราะ Eve API ไม่รองรับ Batch Branch IDs)
        today_str = datetime.now().strftime('%d/%m/%Y')
        if date_end == today_str:
            print(f"⏩ [Batch Skip] Date is 'Today'. Using individual fetches for real-time accuracy.")
            return None
            
        turso = TursoHandler()
        if not (turso.url and turso.token):
            return None
            
        # 1. แปลง branch_ids (Eve IDs) เป็น Real IDs สำหรับ Turso
        real_ids_map = {} # {real_id: eve_id}
        real_ids_to_fetch = []
        
        for eve_id in branch_ids:
            real_id = eve_id
            try:
                branch_info = find_branch_by_sequential_id(eve_id)
                if branch_info and 'branch_name' in branch_info:
                    import re
                    match = re.search(r'ID(\d+)', branch_info['branch_name'])
                    if match:
                        real_id = match.group(1)
            except:
                pass
            real_ids_map[str(real_id)] = str(eve_id)
            real_ids_to_fetch.append(str(real_id))
            
        # 2. ตรวจสอบสถานะการ Sync
        sync_status = turso.check_sync_status_batch(real_ids_to_fetch, date_start, date_end)
        
        # 3. Hybrid Fetch: ดึงเฉพาะสาขาที่ Sync แล้วออกมาแบบ Batch
        synced_real_ids = [rid for rid, status in sync_status.items() if status]
        unsynced_real_ids = [rid for rid, status in sync_status.items() if not status]
        
        results = {}
        
        if synced_real_ids:
            print(f"✨ [Hybrid Batch] Fetching {len(synced_real_ids)} synced branches from Turso...")
            # ✅ FIX: เรียก get_trades_batch ด้วย argument ที่ถูกต้อง (date_start, date_end, branch_ids=)
            trades = turso.get_trades_batch(date_start, date_end, branch_ids=synced_real_ids)
            
            print(f"   Total trades returned from Turso: {len(trades)}")
            
            # Debug: แสดง sample ของ real_branch_id ที่เจอใน trades
            sample_ids = list(set(str(t.get('real_branch_id') or t.get('BRANCH_ID', '')) for t in trades[:20]))
            print(f"   Sample real_branch_id/BRANCH_ID in trades: {sample_ids[:5]}")
            print(f"   Expected real_ids: {synced_real_ids[:5]}")
            
            # จัดกลุ่มข้อมูลตาม Eve ID
            for real_id in synced_real_ids:
                eve_id = real_ids_map.get(str(real_id))
                # ✅ เช็คทั้ง real_branch_id และ BRANCH_ID เพื่อรองรับทั้ง 2 รูปแบบ
                b_trades = [t for t in trades if 
                            str(t.get('real_branch_id', '')) == str(real_id) or 
                            str(t.get('BRANCH_ID', '')) == str(real_id)]
                results[str(eve_id)] = {
                    'data': b_trades,
                    'recordsTotal': len(b_trades),
                    'recordsFiltered': len(b_trades),
                    'source': 'turso'
                }
        
        if unsynced_real_ids:
            print(f"❓ [Hybrid Batch] {len(unsynced_real_ids)} branches not synced. Fetching from Eve API individually...")
            for real_id in unsynced_real_ids:
                eve_id = real_ids_map.get(str(real_id))
                if not eve_id:
                    continue
                try:
                    filters = {
                        'date_start': date_start,
                        'date_end': date_end,
                        'sale_code': '',
                        'customer_sign': '',
                        'session_id': '',
                        'branch_id': str(eve_id)
                    }
                    api_result = fetch_data_from_api(start=0, length=5000, **filters)
                    results[str(eve_id)] = api_result
                    print(f"   ✅ [Hybrid Batch] Fetched Branch {eve_id} (real: {real_id}) from Eve API: {len(api_result.get('data', []))} records")
                except Exception as fetch_err:
                    print(f"   ⚠️ [Hybrid Batch] Failed to fetch Branch {eve_id}: {fetch_err}")
                    results[str(eve_id)] = {'data': [], 'recordsTotal': 0, 'recordsFiltered': 0, 'source': 'error'}

        turso.close()
        return results
            
    except Exception as e:
        print(f"⚠️ [Batch Error] {e}")
        import traceback
        traceback.print_exc()
        return None
        



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

    def extract_real_branch_id(item, fallback_id):
        """หาค่า branch id จริงจาก API payload ก่อน แล้ว fallback จากชื่อสาขา"""
        bid = item.get('BRANCH_ID') or item.get('branch_id')
        raw_name = str(item.get('BRANCH_NAME', '') or item.get('branch_name', ''))
        import re
        m = re.search(r'ID(\d+)', raw_name)
        if m:
            return m.group(1)
        return str(bid) if bid not in (None, '') else str(fallback_id)

    # Inject branch info
    branches_dict = {str(b.get('branch_id', '')): b.get('branch_name', '').split(':')[-1].strip() for b in get_branches_from_db() if b.get('branch_id')}
    req_b_id = str(filters['branch_id'])
    b_name = branches_dict.get(req_b_id, f"Branch {req_b_id}")
    for item in data.get('data', []):
        real_id = extract_real_branch_id(item, req_b_id)
        item['selected_branch_id'] = req_b_id
        item['branch_id'] = real_id
        raw_name = str(item.get('BRANCH_NAME', '') or item.get('branch_name', ''))
        if raw_name:
            item['branch_name'] = raw_name.split(':')[-1].strip() if ':' in raw_name else raw_name
        else:
            item['branch_name'] = branches_dict.get(real_id, b_name)
    
    return jsonify(data)

@app.route('/api/data-batch', methods=['POST'])
def get_data_batch():
    """API endpoint สำหรับดึงข้อมูลหลายสาขาพร้อมกัน (Batch + Concurrent)"""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        branch_ids = data.get('branchIds', [])
        if not branch_ids:
            return jsonify({'error': 'No branchIds provided'}), 400
        
        print(f"📦 Batch request: {len(branch_ids)} branches: {branch_ids}")
        
        # สร้าง filters จาก request data
        base_filters = {
            'date_start': data.get('dateStart', ''),
            'date_end': data.get('dateEnd', ''),
            'sale_code': data.get('saleCode', ''),
            'status': data.get('status', ''),
            'brands': [data.get('brand')] if data.get('brand') else [],
            'series': data.get('series', ''),
            'doc_ref_number': data.get('docRefNumber', ''),
            'promo_code': data.get('promoCode', ''),
            'customer_sign': data.get('customerSign', '0')
        }
        
        all_data = []
        total_records = 0
        errors = []
        sources_summary = {}
        
        # Vercel Hobby timeout = 60s, ให้ใช้สูงสุด 50s
        is_vercel = os.environ.get('VERCEL', False)
        max_time = 50 if is_vercel else 180
        
        branches_dict = {str(b.get('branch_id', '')): b.get('branch_name', '').split(':')[-1].strip() for b in get_branches_from_db() if b.get('branch_id')}
        
        def extract_real_branch_id(item, requested_branch_id):
            bid = item.get('BRANCH_ID') or item.get('branch_id')
            raw_name = str(item.get('BRANCH_NAME', '') or item.get('branch_name', ''))
            import re
            m = re.search(r'ID(\d+)', raw_name)
            if m:
                return m.group(1)
            return str(bid) if bid not in (None, '') else str(requested_branch_id)

        def fetch_branch(branch_id):
            """ดึงข้อมูลสาขาเดียว (ใช้ใน thread)"""
            branch_start = time.time()
            try:
                branch_filters = base_filters.copy()
                branch_filters['branch_id'] = branch_id
                
                result = fetch_data_from_api(start=0, length=200, **branch_filters)
                source = result.get('source', 'unknown')
                
                if 'error' in result:
                    print(f"  ❌ Branch {branch_id}: {result['error']} ({source})")
                    return {'branch_id': branch_id, 'error': result['error'], 'data': [], 'total': 0, 'source': source}
                
                items = result.get('data', [])
                record_total = result.get('recordsFiltered', len(items))
                
                # ดึง pagination ถ้ามีมากกว่า 200 รายการ
                if record_total > len(items) and len(items) == 200:
                    next_start = 200
                    while len(items) < record_total:
                        elapsed = time.time() - start_time
                        if elapsed > max_time:
                            break
                        more = fetch_data_from_api(start=next_start, length=200, **branch_filters)
                        more_data = more.get('data', [])
                        if not more_data:
                            break
                        items.extend(more_data)
                        next_start += 200
                        if len(more_data) < 200:
                            break
                
                elapsed_branch = time.time() - branch_start
                print(f"  ✅ Branch {branch_id}: {len(items)} items in {elapsed_branch:.1f}s ({source})")
                
                b_name = branches_dict.get(str(branch_id), f"Branch {branch_id}")
                for item in items:
                    real_id = extract_real_branch_id(item, branch_id)
                    item['selected_branch_id'] = str(branch_id)
                    item['branch_id'] = real_id
                    raw_name = str(item.get('BRANCH_NAME', '') or item.get('branch_name', ''))
                    if raw_name:
                        item['branch_name'] = raw_name.split(':')[-1].strip() if ':' in raw_name else raw_name
                    else:
                        item['branch_name'] = branches_dict.get(real_id, b_name)
                    
                return {'branch_id': branch_id, 'data': items, 'total': record_total, 'source': source}
                
            except Exception as e:
                print(f"  ❌ Branch {branch_id} exception: {e}")
                return {'branch_id': branch_id, 'error': str(e), 'data': [], 'total': 0}
        
        # ใช้ ThreadPoolExecutor ดึง concurrent (max 5 threads)
        max_workers = min(5, len(branch_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_branch, bid): bid for bid in branch_ids}
            
            for future in as_completed(futures):
                elapsed = time.time() - start_time
                if elapsed > max_time:
                    print(f"⚠️ Batch timeout after {elapsed:.1f}s, collected {len(all_data)} items so far")
                    break
                    
                result = future.result()
                bid = str(result.get('branch_id', ''))
                if bid:
                    sources_summary[bid] = result.get('source', 'unknown')
                
                if result.get('error'):
                    errors.append({'branch_id': bid, 'error': result['error']})
                all_data.extend(result.get('data', []))
                total_records += result.get('total', 0)
        
        elapsed_total = time.time() - start_time
        print(f"📦 Batch done: {len(branch_ids)} branches, {len(all_data)} items, {len(errors)} errors in {elapsed_total:.1f}s")
        
        return jsonify({
            'data': all_data,
            'recordsTotal': total_records,
            'recordsFiltered': len(all_data),
            'branchCount': len(branch_ids),
            'errors': errors if errors else None,
            'sources': sources_summary
        })
        
    except Exception as e:
        print(f"❌ Batch API error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def fetch_all_for_branch(filters):
    """ดึงข้อมูลทั้งหมดของสาขาเดียว (พร้อม pagination)"""
    import time
    
    # ปรับ timeout ตามสภาพแวดล้อม
    is_vercel = os.environ.get('VERCEL', False)
    max_time = 300 if is_vercel else 900  # เพิ่มเวลาเป็น 15 นาทีถ้าไม่ใช่ Vercel
    max_items = 10000 if is_vercel else 100000
    
    length = 500 # เพิ่มจาก 100 เป็น 500 เพื่อให้ดึงเร็วขึ้น (ลดจำนวนครั้งที่เรียก API)
    start = 0
    all_items = []
    batch_count = 0
    start_time = time.time()
    
    print(f"📊 Fetching for branch {filters.get('branch_id')} (Batch size: {length})...")
    
    while True:
        # ตรวจสอบเวลา
        elapsed = time.time() - start_time
        if elapsed > max_time:
            print(f"⚠️ Timeout protection: stopped at {len(all_items)} items after {elapsed:.1f}s (Max: {max_time}s)")
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
            date_start = filters.get('date_start')
            date_end = filters.get('date_end')
            today_str = datetime.now().strftime('%d/%m/%Y')
            
            # 🚀 OPTIMIZATION: Use Turso Batch Fetch if not today
            is_today = (date_end == today_str)
            if not is_today:
                print(f"📦 [Zone Batch] Attempting to fetch {len(branch_ids)} branches from Turso...")
                turso = TursoHandler()
                import re
                
                # Map sequential IDs to real IDs
                real_id_map = {} # {real_id: seq_id}
                real_ids = []
                for bid in branch_ids:
                    try:
                        branch_info = find_branch_by_sequential_id(bid)
                        if branch_info and 'branch_name' in branch_info:
                            match = re.search(r'ID(\d+)', branch_info['branch_name'])
                            if match:
                                rid = match.group(1)
                                real_id_map[str(rid)] = str(bid)
                                real_ids.append(rid)
                            else:
                                real_ids.append(str(bid))
                        else:
                            real_ids.append(str(bid))
                    except:
                        real_ids.append(str(bid))
                
                # Check which ones are synced
                sync_status = turso.check_sync_status_batch(real_ids, date_start, date_end)
                synced_real_ids = [rid for rid, synced in sync_status.items() if synced]
                
                if synced_real_ids:
                    print(f"✅ [Turso Batch] Found {len(synced_real_ids)}/{len(real_ids)} branches already synced.")
                    batch_items = turso.get_trades_batch(date_start, date_end, branch_ids=synced_real_ids)
                    all_items.extend(batch_items)
                    
                    # Identify branches that still need fetching (not synced)
                    synced_seq_ids = [real_id_map.get(rid, rid) for rid in synced_real_ids]
                    remaining_branch_ids = [bid for bid in branch_ids if str(bid) not in synced_seq_ids]
                else:
                    remaining_branch_ids = branch_ids
                
                turso.close()
                
                # Fetch remaining from API
                if remaining_branch_ids:
                    print(f"🔄 [API Fallback] Fetching remaining {len(remaining_branch_ids)} branches from Eve...")
                    for i, branch_id in enumerate(remaining_branch_ids):
                        print(f"   [{i+1}/{len(remaining_branch_ids)}] Processing branch {branch_id}...")
                        branch_filters = filters.copy()
                        branch_filters['branch_id'] = branch_id
                        if 'zone_id' in branch_filters: del branch_filters['zone_id']
                        items = fetch_all_for_branch(branch_filters)
                        all_items.extend(items)
            else:
                # Is today, fetch all from API sequentially (or as before)
                print(f"⏩ [Skip Cache] Date is 'Today'. Fetching all {len(branch_ids)} branches from Eve.")
                for i, branch_id in enumerate(branch_ids):
                    print(f"   [{i+1}/{len(branch_ids)}] Processing branch {branch_id}...")
                    branch_filters = filters.copy()
                    branch_filters['branch_id'] = branch_id
                    if 'zone_id' in branch_filters: del branch_filters['zone_id']
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
    
    # โหลด supersale config
    supersale_ids = get_supersale_branch_ids()
    current_branch_id = filters.get('branch_id')
    # ถ้าเป็นสาขาเดียว (ไม่ใช่ zone) ให้เช็คว่าเป็น supersale หรือไม่
    is_supersale_branch = False
    if current_branch_id and not zone_id:
        try:
            is_supersale_branch = int(current_branch_id) in supersale_ids
        except (ValueError, TypeError):
            pass
    
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
        
        # สรุปตามพนักงานขาย (ถ้าเป็น supersale ให้ใช้ SALE_NAME เป็น key แทน)
        sale_code = item.get('SALE_CODE', '')
        sale_name = item.get('SALE_NAME', '')
        
        if is_supersale_branch:
            # supersale branch: รหัส sale ปกติอยู่ใน SALE_NAME
            sale_key = sale_name
            sale_display = sale_code  # SALE_CODE คือ supersale code
        else:
            sale_key = sale_code
            sale_display = sale_name
        
        if sale_key:
            sales_summary[sale_key]['name'] = sale_display
            sales_summary[sale_key]['count'] += 1
            sales_summary[sale_key]['totalAmount'] += amount
            if is_confirmed:
                sales_summary[sale_key]['confirmedCount'] += 1
                sales_summary[sale_key]['confirmedAmount'] += amount
        
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
    """ค้นหาสาขาจาก ID number (เช่น 9 จาก ID9, 13 จาก ID13, 2957) หรือ branch_id"""
    import os
    import re
    
    # 1. พยายามดึงจาก DB ก่อน (Source of Truth)
    branches_data = get_branches_from_db()
    
    # 2. ถ้าไม่มีใน DB ให้ลองดึงจากไฟล์เดิม (Fallback)
    if not branches_data:
        try:
            branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
            if os.path.exists(branches_file):
                with open(branches_file, 'r', encoding='utf-8') as f:
                    branches_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Fallback file error: {e}")
            
    if not branches_data:
        return None
    
    branch_id_str = str(branch_id_input).strip()
    
    # พยายามแปลงเป็นตัวเลขเพื่อค้นหาแบบ ID number
    search_num = None
    try:
        # ตัด 0 ข้างหน้าออกถ้ามี (เช่น "09" -> 9)
        search_num = int(branch_id_str)
    except ValueError:
        pass
        
    for branch in branches_data:
        bid = str(branch.get('branch_id', ''))
        bname = branch.get('branch_name', '')
        
        # 1. เช็ค branch_id ตรงๆ (internal ID)
        if bid == branch_id_str:
            return branch
            
        if search_num is not None:
            # 2. เช็คจาก ID prefix ในชื่อ (เช่น "ID9", "ID2957")
            match = re.search(r'ID(\d+)', bname)
            if match and int(match.group(1)) == search_num:
                return branch
                
            # 3. เช็คจากตัวเลขที่ปรากฏในชื่อ (เช่น "02957 : 2957 : ...")
            # ค้นหาตัวเลขทั้งหมดในชื่อ แล้วเช็คว่ามีตัวไหนตรงกับ search_num
            numbers_in_name = re.findall(r'\d+', bname)
            for n_str in numbers_in_name:
                try:
                    if int(n_str) == search_num:
                        return branch
                except:
                    continue
                    
        # 4. เช็คชื่อเต็มแบบ Case-insensitive
        if branch_id_str.lower() in bname.lower():
            return branch
    
    return None

_BRANCHES_DICT_CACHE = None

def find_branch_by_sequential_id(seq_id):
    """ค้นหาสาขาจาก branch_id (sequential index) ด้วยระบบ Cache"""
    global _BRANCHES_DICT_CACHE
    import os
    import json
    
    # 1. โหลดข้อมูลเข้า Cache ครั้งแรกครั้งเดียว
    if _BRANCHES_DICT_CACHE is None:
        try:
            branches_file = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
            if os.path.exists(branches_file):
                with open(branches_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # สร้าง Dict สำหรับค้นหาด้วย branch_id อย่างรวดเร็ว
                    _BRANCHES_DICT_CACHE = {str(b.get('branch_id')): b for b in data}
                    print(f"📦 [Cache Build] Loaded {len(_BRANCHES_DICT_CACHE)} branches into memory.")
            else:
                _BRANCHES_DICT_CACHE = {}
                print(f"⚠️ [Cache Build] extracted_branches.json not found.")
        except Exception as e:
            print(f"❌ [Cache Build] Error loading branches: {e}")
            _BRANCHES_DICT_CACHE = {}

    # 2. ค้นหาจาก Cache
    try:
        s_id = str(seq_id)
        branch = _BRANCHES_DICT_CACHE.get(s_id)
        if branch:
            # print(f"✅ [Cache Hit] Found branch: {branch.get('branch_name')}") # ลด Log เพื่อความเร็ว
            return branch
        # print(f"⚠️ [Cache Miss] No branch found with ID {s_id}")
    except:
        pass
        
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

@app.route('/api/supersale-config', methods=['GET'])
@login_required
def get_supersale_config():
    """API endpoint สำหรับดึง config สาขา supersale"""
    branch_ids = get_supersale_branch_ids()
    return jsonify({
        'success': True,
        'branch_ids': branch_ids
    })

@app.route('/api/supersale-config', methods=['POST'])
@login_required
def save_supersale_config():
    """API endpoint สำหรับบันทึก config สาขา supersale"""
    try:
        data = request.get_json()
        branch_ids = data.get('branch_ids', [])
        
        # บันทึกลง system_settings
        success = save_system_setting('supersale_branch_ids', json.dumps(branch_ids))
        
        if success:
            print(f"✅ บันทึก supersale config: {len(branch_ids)} สาขา → {branch_ids}")
            return jsonify({
                'success': True,
                'message': f'บันทึกสำเร็จ ({len(branch_ids)} สาขา)',
                'branch_ids': branch_ids
            })
        else:
            return jsonify({
                'success': False,
                'error': 'ไม่สามารถบันทึกได้'
            }), 500
    except Exception as e:
        print(f"❌ Error saving supersale config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
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
        source = 'database'
        
        # 2. ถ้าไม่มีใน DB ให้ลองดึงจากไฟล์เดิม (Fallback)
        if not branches:
            print("⚠️ No branches in DB, checking static file...")
            source = 'static_file'
            try:
                json_path = os.path.join(os.path.dirname(__file__), 'extracted_branches.json')
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        branches = json.load(f)
            except Exception as e:
                print(f"⚠️ File fallback failed: {e}")
        
        # Debug: แสดงจำนวนสาขาที่ส่งกลับ
        branch_count = len(branches) if branches else 0
        print(f"📤 /api/branches -> Serving {branch_count} branches from {source}")
        if branches and branch_count > 0:
            # แสดง branch_id ล่าสุด 5 ตัว
            last_ids = [b.get('branch_id', '?') for b in branches[-5:]]
            print(f"📤 Last 5 branch IDs: {last_ids}")
        
        response = jsonify({
            'success': True,
            'branches': branches,
            'source': source,
            'count': branch_count
        })
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
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
        # บังคับ login ใหม่เสมอเมื่อกดอัปเดตสาขา (ไม่ใช้ cache เพราะ session อาจหมดอายุ)
        print(f"🔄 [update-branches] Force refreshing Eve session...")
        session_id = get_eve_session(force_refresh=True)
        
        if not session_id:
            print(f"❌ [update-branches] Auto-Login failed!")
            return jsonify({'success': False, 'error': 'Auto-Login ล้มเหลว กรุณาตรวจสอบ Eve Credentials'}), 400
        
        print(f"✅ [update-branches] Got session: {session_id[:10]}...")
            
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
             # ลอง login ใหม่อีกครั้ง (second attempt)
             print(f"⚠️ [update-branches] First attempt failed, trying fresh login...")
             session_id_retry, error = perform_eve_login()
             if session_id_retry:
                 success_retry, count_retry = trigger_branch_update(session_id_retry)
                 if success_retry:
                     # อัปเดต cache ด้วย session ใหม่
                     import time
                     EVE_SESSION_CACHE['session_id'] = session_id_retry
                     EVE_SESSION_CACHE['timestamp'] = time.time()
                     return jsonify({
                         'success': True,
                         'message': f'อัปเดตสาขาเรียบร้อย ({count_retry} สาขา) [retry]',
                         'count': count_retry
                     })
             
             return jsonify({'success': False, 'error': 'ไม่สามารถดึงข้อมูลสาขาจาก Eve API ได้ (ตรวจสอบ Log เพิ่มเติม)'}), 500

    except Exception as e:
        print(f"❌ Error in update_branches_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# Auto-Cancel Scheduler System (Vercel Cron Version)
# ============================================================

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
            # Fix: RealDictRow is already a dict-like object, don't use zip with keys!
            return dict(row)
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

def run_auto_cancel(force=False):
    """ฟังก์ชันหลัก: ยกเลิกรายการเทรดอัตโนมัติ"""
    print("\n" + "="*60)
    print(f"⏰ Auto-Cancel Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    config = get_auto_cancel_config()
    if not config:
        print("⚠️ No auto-cancel config found")
        return {'success': False, 'message': 'ไม่พบ config กรุณาบันทึกก่อน'}
    
    if not force and not config.get('enabled'):
        print("⚠️ Auto-cancel is disabled, skipping")
        return {'success': False, 'message': 'ระบบปิดอยู่'}
    
    branch_ids_str = config.get('branch_ids', '')
    if not branch_ids_str:
        print("⚠️ No branches configured, skipping")
        return {'success': False, 'message': 'ยังไม่ได้ตั้งค่าสาขา'}
    
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
    
    # คำนวณเวลาไทย (UTC+7) แล้วย้อนหลัง 1 วัน
    thai_time_now = datetime.utcnow() + timedelta(hours=7)
    target_date = (thai_time_now - timedelta(days=1)).strftime('%d/%m/%Y')
    total_found = 0
    total_cancelled = 0
    total_skipped = 0
    total_failed = 0
    details_list = []
    
    for branch_id in branch_ids:
        print(f"\n🔍 Processing branch: {branch_id} for date: {target_date}")
        try:
            # ดึงข้อมูลเทรดย้อนหลัง 1 วัน (เฉพาะสถานะ รอผู้ขายยืนยันราคา = ID 3)
            result = fetch_data_from_api(
                start=0, length=200,
                branch_id=branch_id,
                date_start=target_date,
                date_end=target_date,
                status="3"
            )
            
            if not result or 'data' not in result:
                print(f"  ⚠️ No data for branch {branch_id}")
                details_list.append(f"⚠️ Branch {branch_id}: ไม่มีข้อมูล")
                continue
            
            items = result['data']
            
            # Debug: แสดง field names ของ item แรก
            if items:
                first_item = items[0]
                keys_sample = list(first_item.keys())[:5]
                # แสดงสถานะทั้งหมดที่เจอ
                all_statuses = set(item.get('BIDDING_STATUS_NAME', 'N/A') for item in items)
                print(f"  Clipboard: {all_statuses}")
                details_list.append(f"🔍 Debug Branch {branch_id}: Statuses={all_statuses}")
                details_list.append(f"🔍 Debug Keys: {keys_sample}")
            
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
    
    # ส่ง Telegram (เฉพาะเมื่อมีการยกเลิกสำเร็จ)
    telegram_sent = False
    if total_cancelled > 0:
        telegram_sent = send_telegram_notification(
            config.get('telegram_bot_token', ''),
            config.get('telegram_chat_id', ''),
            summary
        )
    else:
        print("ℹ️ ไม่มีการยกเลิกสำเร็จ ข้ามการส่ง Telegram")
    
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
    
    return {
        'success': True,
        'total_found': total_found,
        'total_cancelled': total_cancelled,
        'total_skipped': total_skipped,
        'total_failed': total_failed
    }

# Removed APScheduler functions (start_auto_cancel_scheduler, reschedule_auto_cancel)
# because Vercel Serverless Functions do not support persistent background tasks.
# We now use Vercel Cron Jobs to hit /api/admin/auto-cancel-cron instead.

@app.route('/api/admin/auto-cancel-cron', methods=['GET', 'POST'])
def vercel_cron_auto_cancel():
    """Endpoint สำหรับ GitHub Actions Cron ยิงมาทุกๆ 15 นาที"""
    try:
        # Check authorization
        cron_secret = os.environ.get("CRON_SECRET", "")
        auth_header = request.headers.get('Authorization', '')
        
        # If secret is set in env, enforce it
        if cron_secret and auth_header != f'Bearer {cron_secret}':
            print("❌ Unauthorized cron attempt")
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
        config = get_auto_cancel_config()
        if not config or not config.get('enabled'):
            print("⏰ Cron Triggered: Auto-cancel is disabled in DB.")
            return jsonify({'success': False, 'message': 'System disabled'}), 200
            
        schedule_time = config.get('schedule_time', '00:00')
        target_hour, target_minute = schedule_time.split(':')
        
        bkk_tz = pytz.timezone('Asia/Bangkok')
        now_bkk = datetime.now(bkk_tz)
        
        target_dt_today = now_bkk.replace(hour=int(target_hour), minute=int(target_minute), second=0, microsecond=0)
        if now_bkk < target_dt_today:
            # If current time hasn't passed today's target yet, the most recent target is yesterday's.
            target_dt_past = target_dt_today - timedelta(days=1)
        else:
            target_dt_past = target_dt_today
            
        print(f"⏰ Cron Ping: Now={now_bkk.strftime('%H:%M')}, Target={schedule_time}. Most recent schedule={target_dt_past.strftime('%Y-%m-%d %H:%M')}")
        
        # Check database for last run
        conn = get_db_connection()
        already_run = False
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT run_at FROM auto_cancel_log ORDER BY run_at DESC LIMIT 1")
                last_log = cur.fetchone()
                if last_log and last_log.get('run_at'):
                    last_run_utc = last_log['run_at']
                    if last_run_utc.tzinfo is None:
                        last_run_utc = last_run_utc.replace(tzinfo=pytz.UTC)
                    last_run_bkk = last_run_utc.astimezone(bkk_tz)
                    
                    if last_run_bkk >= target_dt_past:
                        already_run = True
                cur.close()
            except Exception as db_e:
                print(f"❌ DB Check Error: {db_e}")
            finally:
                conn.close()
                
        if not already_run:
            print(f"✅ Time to run! Executing auto-cancel...")
            result = run_auto_cancel(force=True)
            return jsonify({'success': True, 'message': 'Cron executed successfully', 'result': result}), 200
        else:
            return jsonify({'success': True, 'message': f'Skipped. Already ran for schedule {schedule_time}'}), 200
            
    except Exception as e:
        print(f"❌ Cron Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
# Removed reschedule_auto_cancel() call because we now rely on Vercel Cron
            return jsonify({'success': True, 'message': 'บันทึกสำเร็จ'})
        return jsonify({'success': False, 'error': 'บันทึกไม่สำเร็จ'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/auto-cancel-test', methods=['POST'])
def test_auto_cancel():
    """ทดสอบรัน auto-cancel ทันที (ข้ามการเช็ค enabled)"""
    try:
        config = get_auto_cancel_config()
        if not config or not config.get('branch_ids'):
            return jsonify({'success': False, 'error': 'กรุณาบันทึก config ก่อน (ระบุสาขา + ข้อมูลพนักงาน)'}), 400
        
        # รัน synchronously กับ force=True (ข้ามเช็ค enabled)
        result = run_auto_cancel(force=True)
        return jsonify({'success': True, 'message': 'รัน auto-cancel เสร็จแล้ว ดูผลลัพธ์ใน Telegram และ Log', 'result': result})
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
        cur.execute("SELECT * FROM auto_cancel_log WHERE total_cancelled > 0 ORDER BY run_at DESC LIMIT 10")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        logs = []
        for row in rows:
            # row is RealDictRow, convert to dict
            log = dict(row)
            if log.get('run_at'):
                if isinstance(log['run_at'], datetime):
                    log['run_at'] = log['run_at'].strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    log['run_at'] = str(log['run_at']).replace(' ', 'T') + 'Z'
            logs.append(log)
        
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# Auto Daily Export System
# ============================================================

def get_auto_export_config_from_db():
    """ดึง config auto-export จาก DB"""
    try:
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
        print(f"❌ Error getting auto-export config: {e}")
        return None

def save_auto_export_config_to_db(config):
    """บันทึก config auto-export ลง DB"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("DELETE FROM auto_export_config")
        
        zone_ids = config.get('zone_ids', [])
        if isinstance(zone_ids, list):
            zone_ids = json.dumps(zone_ids)
        
        cur.execute("""
            INSERT INTO auto_export_config
            (enabled, schedule_time, zone_ids, gdrive_folder_id, gdrive_credentials, max_files_per_zone)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            config.get('enabled', False),
            config.get('schedule_time', '00:05'),
            zone_ids,
            config.get('gdrive_folder_id', ''),
            config.get('gdrive_credentials', ''),
            config.get('max_files_per_zone', 365)
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error saving auto-export config: {e}")
        return False

@app.route('/api/admin/auto-export-config', methods=['GET', 'POST'])
def manage_auto_export_config():
    """API สำหรับจัดการ config auto-export"""
    if request.method == 'GET':
        config = get_auto_export_config_from_db()
        if config:
            config['updated_at'] = str(config.get('updated_at', ''))
            # ไม่ส่ง credentials กลับไป (security)
            config['gdrive_credentials'] = '***' if config.get('gdrive_credentials') else ''
            return jsonify({'success': True, 'config': config})
        return jsonify({'success': True, 'config': None})
    
    # POST - save config
    try:
        data = request.get_json()
        
        # ถ้าส่ง credentials มาเป็น '***' หมายถึงไม่เปลี่ยน
        if data.get('gdrive_credentials') == '***':
            existing = get_auto_export_config_from_db()
            if existing:
                data['gdrive_credentials'] = existing.get('gdrive_credentials', '')
        
        success = save_auto_export_config_to_db(data)
        if success:
            return jsonify({'success': True, 'message': 'บันทึก config auto-export สำเร็จ'})
        return jsonify({'success': False, 'error': 'บันทึกไม่สำเร็จ'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/auto-export-test', methods=['POST'])
def test_auto_export():
    """ทดสอบรัน auto-sync (Turso) ทันที"""
    try:
        from auto_daily_export import run_daily_export
        result = run_daily_export(force=True)
        return jsonify({'success': True, 'message': 'รัน Turso Sync เสร็จแล้ว', 'result': result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/auto-export-cron', methods=['GET', 'POST'])
def vercel_cron_auto_export():
    """Endpoint สำหรับ GitHub Actions Cron ยิงมาทุกๆ 15 นาที สำหรับ auto-export"""
    try:
        # Check authorization
        cron_secret = os.environ.get("CRON_SECRET", "")
        auth_header = request.headers.get('Authorization', '')
        if cron_secret and auth_header != f'Bearer {cron_secret}':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        config = get_auto_export_config_from_db()
        if not config or not config.get('enabled'):
            return jsonify({'success': False, 'message': 'Auto-export is disabled'}), 200
        
        schedule_time = config.get('schedule_time', '00:05')
        target_hour, target_minute = schedule_time.split(':')
        
        bkk_tz = pytz.timezone('Asia/Bangkok')
        now_bkk = datetime.now(bkk_tz)
        
        target_dt_today = now_bkk.replace(hour=int(target_hour), minute=int(target_minute), second=0, microsecond=0)
        if now_bkk < target_dt_today:
            target_dt_past = target_dt_today - timedelta(days=1)
        else:
            target_dt_past = target_dt_today
        
        print(f"📤 Export Cron Ping: Now={now_bkk.strftime('%H:%M')}, Target={schedule_time}")
        
        # Check if already ran for this schedule
        conn = get_db_connection()
        already_run = False
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT run_at FROM auto_export_log WHERE status='success' ORDER BY run_at DESC LIMIT 1")
                last_log = cur.fetchone()
                if last_log and last_log.get('run_at'):
                    last_run_utc = last_log['run_at']
                    if last_run_utc.tzinfo is None:
                        last_run_utc = last_run_utc.replace(tzinfo=pytz.UTC)
                    last_run_bkk = last_run_utc.astimezone(bkk_tz)
                    if last_run_bkk >= target_dt_past:
                        already_run = True
                cur.close()
            except Exception as db_e:
                print(f"❌ DB Check Error: {db_e}")
            finally:
                conn.close()
        
        if not already_run:
            print(f"✅ Time to run! Executing auto-export...")
            from auto_daily_export import run_daily_export
            result = run_daily_export(force=True)
            return jsonify({'success': True, 'message': 'Export executed', 'result': result}), 200
        else:
            return jsonify({'success': True, 'message': f'Skipped. Already ran for schedule {schedule_time}'}), 200
    
    except Exception as e:
        print(f"❌ Export Cron Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/auto-export-logs', methods=['GET'])
def get_auto_export_logs():
    """ดึง log การรัน auto-export"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'DB connection failed'}), 500
        cur = conn.cursor()
        cur.execute("SELECT * FROM auto_export_log ORDER BY run_at DESC LIMIT 50")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        logs = []
        for row in rows:
            log = dict(row)
            if log.get('run_at'):
                if isinstance(log['run_at'], datetime):
                    log['run_at'] = log['run_at'].strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    log['run_at'] = str(log['run_at']).replace(' ', 'T') + 'Z'
            logs.append(log)
        
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# เริ่ม scheduler เมื่อ app start (เฉพาะ non-debug reloader)
# import os as _os # Moved to top
# ============================================================
# Line Bot Webhook (Manual Implementation - No SDK)
# ============================================================

# ============================================================
# Line Bot Webhook (Restored from Working Version)
# ============================================================

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '').strip()

def reply_line_message(reply_token, message):
    """ส่ง Reply Message ไปยัง LINE (Original Working Version)"""
    try:
        url = 'https://api.line.me/v2/bot/message/reply'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
        }
        payload = {
            'replyToken': reply_token,
            'messages': [{'type': 'text', 'text': message}]
        }
        
        log_debug(f"Sending reply to {reply_token[:10]}...")
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            log_debug(f"❌ Failed to reply: {response.status_code} {response.text}")
        else:
            log_debug("✅ Reply success")
            
        return response.json()
    except Exception as e:
        log_debug(f"❌ Error sending reply: {e}")
        return None

@app.route('/webhook/line', methods=['POST'])
def line_webhook():
    """Webhook สำหรับรับข้อความจาก LINE (Restored Logic)"""
    # Also handle /callback for compatibility
    try:
        log_debug(f"Webhook called: {request.path}")
        
        # Original logic used get_json() directly without signature verification
        body = request.get_json()
        if not body:
            log_debug("❌ No JSON body")
            return 'No Body', 400
            
        # Log parsed body slightly sanitized
        log_debug(f"Body keys: {list(body.keys())}")
        
        events = body.get('events', [])
        log_debug(f"Events: {len(events)}")
        
        for event in events:
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                user_message = event['message']['text']
                
                log_debug(f"Msg: {user_message}")
                
                 # ตรวจสอบว่าเป็นกลุ่มหรือไม่
                source_type = event.get('source', {}).get('type')
                if source_type == 'group' and not user_message.strip().startswith('รายงาน'):
                    log_debug("Ignored group message (no 'รายงาน')")
                    continue

                # Logic
                reply = handle_line_message(
                    user_message,
                    fetch_data_from_api,
                    load_zones_data,
                    find_zone_by_name,
                    find_branch_by_id,
                    parse_thai_month,
                    get_month_date_range,
                    fetch_batch_func=fetch_zone_data_batch
                )
                
                if reply:
                    if isinstance(reply, dict) and reply.get('type') == 'excel_annual':
                         reply_line_message(reply_token, "ฟีเจอร์ Excel ยังไม่เปิดใช้งานในเวอร์ชันนี้")
                    else:
                         reply_line_message(reply_token, reply)
            else:
                log_debug(f"Ignored event type: {event.get('type')}")

        return jsonify({'status': 'ok'})

    except Exception as e:
        log_debug(f"❌ Webhook Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Backward compatibility alias
@app.route("/callback", methods=['POST'])
def callback_alias():
    return line_webhook()

@app.route("/api/admin/logs", methods=['GET'])
def view_debug_logs():
    logs = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            # Ensure table exists (in case hook never fired)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS debug_logs (
                    id SERIAL PRIMARY KEY,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
            cur.execute("SELECT message FROM debug_logs ORDER BY id DESC LIMIT 50")
            rows = cur.fetchall()
            logs = [row['message'] for row in rows] # RealDictCursor returns dict
            cur.close()
            conn.close()
    except Exception as e:
        logs = [f"Error reading logs: {e}"]
        
    return jsonify({
        "logs": logs,
        "version": "v5 RESTORED Working Logic"
    })

@app.route("/api/admin/line-bot-test", methods=['GET'])
def line_bot_test():
    """Endpoint สำหรับทดสอบ Logic ของ Line Bot"""
    msg = request.args.get('msg', 'วิธีใช้')
    
    reply = handle_line_message(
        msg,
        fetch_data_from_api,
        load_zones_data,
        find_zone_by_name,
        find_branch_by_id,
        parse_thai_month,
        get_month_date_range
    )
    
    return jsonify({
        'success': True,
        'input_message': msg,
        'reply': reply,
        'version': 'v5 RESTORED Working Logic'
    })


try:
    if _os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        # start_auto_cancel_scheduler() # Removed for Vercel Cron
        pass
except Exception as e:
    print(f"❌ CRITICAL STARTUP ERROR: {e}")
    # Don't crash the app, just log it.

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
