import os, json, requests, re, sys
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(os.environ['POSTGRES_URL_NON_POOLING'], cursor_factory=RealDictCursor, connect_timeout=10)

def get_system_setting(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row['value'] if row else None

def eve_login():
    username = get_system_setting('eve_username')
    password = get_system_setting('eve_password')
    login_url = 'https://eve.techswop.com/TI/login.aspx'
    session = requests.Session()
    resp = session.get(login_url, timeout=15)
    fields = {}
    for field in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']:
        m = re.search(rf'id="{field}" value="([^"]+)"', resp.text)
        if m: fields[field] = m.group(1)
    payload = {'txtUsername': username.strip(), 'txtPassword': password.strip(), 'btnSignin': 'เข้าสู่ระบบ', **fields}
    session.post(login_url, data=payload, headers={'User-Agent': 'Mozilla/5.0', 'Referer': login_url}, timeout=30)
    return session.cookies.get('ASP.NET_SessionId')

sid = eve_login()
url = 'https://eve.techswop.com/ti/index.aspx/Getdata'
headers = {'Content-Type': 'application/json; charset=utf-8', 'Cookie': f'ASP.NET_SessionId={sid}', 'X-Requested-With': 'XMLHttpRequest'}

# ดึงข้อมูลตัวอย่าง (วันนี้)
payload = {
    "start": 0,
    "length": 1,
    "date_start": "02/05/2026",
    "date_end": "03/05/2026",
    "branch_id": "0"
}

resp = requests.post(url, headers=headers, json=payload, timeout=30)
print(f"Status: {resp.status_code}")
try:
    data = resp.json()
except Exception as e:
    print(f"❌ JSON Decode Error: {e}")
    print(f"First 500 chars of response: {resp.text[:500]}")
    sys.exit(1)
if 'd' in data and 'data' in data['d'] and len(data['d']['data']) > 0:
    first_item = data['d']['data'][0]
    print("\n✅ API Keys found:")
    print(json.dumps(list(first_item.keys()), indent=2))
    print("\n✅ Sample Data:")
    print(json.dumps(first_item, indent=2))
else:
    print("❌ No data found or API structure changed")
