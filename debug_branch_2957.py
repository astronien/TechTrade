"""
Debug script: ดึงข้อมูลสาขาจาก Eve API ตรงๆ แล้วค้นหาสาขา 2957
"""
import os
import sys
import json
import requests
import re

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- DB Connection ---
def get_db_connection():
    db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
    if not db_url:
        print("❌ POSTGRES_URL_NON_POOLING not set")
        return None
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor, connect_timeout=10)

def get_system_setting(key):
    conn = get_db_connection()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row['value'] if row else None

# --- Eve Login ---
def eve_login():
    username = get_system_setting('eve_username')
    password = get_system_setting('eve_password')
    if not username or not password:
        print("❌ No credentials"); return None
    
    login_url = 'https://eve.techswop.com/TI/login.aspx'
    session = requests.Session()
    resp = session.get(login_url, timeout=15)
    
    # Extract ASP.NET fields
    fields = {}
    for field in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']:
        m = re.search(rf'id="{field}" value="([^"]+)"', resp.text)
        if m: fields[field] = m.group(1)
    
    payload = {'txtUsername': username.strip(), 'txtPassword': password.strip(), 'btnSignin': 'เข้าสู่ระบบ', **fields}
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': login_url, 'Content-Type': 'application/x-www-form-urlencoded'}
    session.post(login_url, data=payload, headers=headers, timeout=30)
    
    sid = session.cookies.get('ASP.NET_SessionId')
    if sid:
        print(f"✅ Login OK! Session: {sid[:10]}...")
        return sid
    print("❌ No session ID")
    return None

# --- Get Branch List ---
def get_branches(session_id):
    url = 'https://eve.techswop.com/TI/inventory/stock-view-list.aspx/GetDropDownBranch'
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Cookie': f'ASP.NET_SessionId={session_id}',
        'X-Requested-With': 'XMLHttpRequest'
    }
    resp = requests.post(url, headers=headers, json={}, timeout=30, allow_redirects=False)
    print(f"📥 Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Bad status: {resp.text[:300]}")
        return []
    
    result = resp.json()
    
    # Extract from 'd' field
    if isinstance(result, dict) and 'd' in result:
        raw = result['d']
        if isinstance(raw, str):
            branches = json.loads(raw)
        elif isinstance(raw, list):
            branches = raw
        else:
            print(f"❓ Unexpected 'd' type: {type(raw)}")
            return []
    elif isinstance(result, list):
        branches = result
    else:
        print(f"❓ Unexpected format: {list(result.keys())}")
        return []
    
    return branches

# --- Check DB cached branches ---
def get_cached_branches():
    conn = get_db_connection()
    if not conn: return []
    cur = conn.cursor()
    cur.execute("SELECT branch_data FROM cached_branches ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    cur.close(); conn.close()
    if row:
        data = row['branch_data']
        if isinstance(data, str):
            return json.loads(data)
        return data
    return []

# =============== MAIN ===============
print("=" * 60)
print("🔍 DEBUG: ค้นหาสาขา 2957")
print("=" * 60)

# 1. Check static file
print("\n--- 1. Static File (branches-data.js) ---")
static_path = os.path.join(os.path.dirname(__file__), 'static', 'branches-data.js')
if os.path.exists(static_path):
    with open(static_path, 'r') as f:
        content = f.read()
    matches = [m for m in re.finditer(r'2957', content)]
    if matches:
        # Find the context around the match
        for m in matches:
            start = max(0, m.start() - 100)
            end = min(len(content), m.end() + 100)
            print(f"  ✅ Found '2957' in static file: ...{content[start:end]}...")
    else:
        print("  ❌ '2957' NOT found in static file")
    
    # Count total branches
    branch_count = content.count('branch_id')
    print(f"  📊 Total branches in static file: {branch_count}")
else:
    print("  ❌ Static file not found")

# 2. Check DB cached branches
print("\n--- 2. Database (cached_branches) ---")
try:
    cached = get_cached_branches()
    print(f"  📊 Total branches in DB: {len(cached)}")
    
    # Search for 2957
    found = [b for b in cached if '2957' in str(b.get('branch_id', '')) or '2957' in str(b.get('branch_name', ''))]
    if found:
        print(f"  ✅ Found branches matching '2957':")
        for b in found:
            print(f"     {b}")
    else:
        print("  ❌ '2957' NOT found in cached branches")
    
    # Show last 10 branches
    print(f"\n  📋 Last 10 branches in DB:")
    for b in cached[-10:]:
        print(f"     branch_id={b.get('branch_id')}, name={b.get('branch_name', '')[:60]}")
except Exception as e:
    print(f"  ❌ DB Error: {e}")

# 3. Live API call
print("\n--- 3. Live Eve API ---")
try:
    session_id = eve_login()
    if session_id:
        branches = get_branches(session_id)
        print(f"  📊 Total branches from API: {len(branches)}")
        
        if branches:
            # Show first item keys
            print(f"  📦 First item keys: {list(branches[0].keys())}")
            print(f"  📦 First item: {branches[0]}")
            
            # Search for 2957
            found_api = []
            for b in branches:
                b_str = json.dumps(b)
                if '2957' in b_str:
                    found_api.append(b)
            
            if found_api:
                print(f"\n  ✅ Found {len(found_api)} branches matching '2957' in API:")
                for b in found_api:
                    print(f"     {b}")
            else:
                print("\n  ❌ '2957' NOT found in live API data!")
            
            # Show last 10 from API
            print(f"\n  📋 Last 10 branches from API:")
            for b in branches[-10:]:
                print(f"     {b}")
        
except Exception as e:
    print(f"  ❌ API Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("🏁 Debug complete")
