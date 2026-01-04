import requests
import re

def extract_aspnet_fields(html_content):
    fields = {}
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='ignore')
        
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
        found = False
        for regex in regex_list:
            match = re.search(regex, html_content)
            if match:
                fields[field] = match.group(1)
                found = True
                break
        if not found:
            print(f"⚠️ Failed to find {field}")
            
    return fields

url = 'https://eve.techswop.com/TI/login.aspx'
print(f"Fetching {url}...")
try:
    r = requests.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Encoding: {r.encoding}")
    
    fields = extract_aspnet_fields(r.content)
    print("\nExtracted Fields:")
    for k, v in fields.items():
        print(f"{k}: {len(v)} chars (Prefix: {v[:20]}...)")
        
    # Check for button name
    if b'btnSignin' in r.content:
        print("\n✅ Found 'btnSignin' in content.")
    else:
        print("\n❌ 'btnSignin' NOT found in content.")
        
    # Check for button value
    if 'เข้าสู่ระบบ' in r.text:
        print("✅ Found 'เข้าสู่ระบบ' in text (UTF-8 decoded).")
    else:
        print("❌ 'เข้าสู่ระบบ' NOT found in text.")

except Exception as e:
    print(f"Error: {e}")
