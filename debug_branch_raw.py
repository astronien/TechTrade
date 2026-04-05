"""Quick check: Eve API raw 'd' field structure"""
import os, json, requests, re
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

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
print(f"Session: {sid[:10]}...")

url = 'https://eve.techswop.com/TI/inventory/stock-view-list.aspx/GetDropDownBranch'
headers = {'Content-Type': 'application/json; charset=utf-8', 'Cookie': f'ASP.NET_SessionId={sid}', 'X-Requested-With': 'XMLHttpRequest'}
resp = requests.post(url, headers=headers, json={}, timeout=30)
result = resp.json()

d = result.get('d')
print(f"\nType of 'd': {type(d)}")
if isinstance(d, dict):
    print(f"Keys of 'd': {list(d.keys())}")
    for k, v in d.items():
        if isinstance(v, list):
            print(f"\n  '{k}' is a list with {len(v)} items")
            if len(v) > 0:
                print(f"  First item: {v[0]}")
                print(f"  First item type: {type(v[0])}")
                # Search for 2957
                found = [x for x in v if '2957' in json.dumps(x)]
                if found:
                    print(f"  🔍 Found '2957': {found[0]}")
                print(f"  Last item: {v[-1]}")
        elif isinstance(v, str) and len(v) > 100:
            print(f"\n  '{k}' is string, length={len(v)}")
            # Try parse as JSON
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    print(f"  Parsed as list with {len(parsed)} items")
                    if len(parsed) > 0:
                        print(f"  First item: {parsed[0]}")
                        found = [x for x in parsed if '2957' in json.dumps(x)]
                        if found:
                            print(f"  🔍 Found '2957': {found[0]}")
            except:
                print(f"  Not JSON, first 200 chars: {v[:200]}")
        else:
            print(f"\n  '{k}': {v}")
elif isinstance(d, str):
    print(f"'d' is string, length={len(d)}")
    try:
        parsed = json.loads(d)
        print(f"Parsed type: {type(parsed)}, length: {len(parsed) if isinstance(parsed, list) else 'N/A'}")
    except:
        print(f"Not JSON: {d[:200]}")
