import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    # This will trigger init_database() in app.py
    from app import perform_eve_login, get_datatables_payload, get_system_setting
    print("✅ Successfully imported app.py functions")
except ImportError as e:
    print(f"❌ Failed to import app.py: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error during import: {e}")

API_URL = "https://eve.techswop.com/ti/index.aspx/Getdata"
BRANCH_ID = "231"

def debug_fetch_data(start=0, length=50, **filters):
    """Custom fetch function to see error details"""
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=utf-8',
        'Origin': 'https://eve.techswop.com',
        'Referer': 'https://eve.techswop.com/ti/index.aspx',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
    }
    
    cookies = {}
    session_id = filters.pop('session_id', '')
    if session_id:
        cookies['ASP.NET_SessionId'] = session_id
        
    branch_id = filters.pop('branch_id', BRANCH_ID)
    
    # Use the payload generator from app
    payload = get_datatables_payload(start, length, branch_id=branch_id, **filters)
    
    
    print("\n--- Request Details ---")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    print(f"Cookies: {cookies}")
    print(f"Payload (JSON):")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, cookies=cookies, timeout=30)
        
        print(f"\n--- Response Status: {response.status_code} ---")
        print(f"Elapsed: {response.elapsed.total_seconds()}s")
        
        if response.status_code != 200:
            print("❌ Server Error!")
            print("Response Content Preview:")
            print(response.text[:2000])
            
            with open("error_500.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("\n✅ Saved full error response to 'error_500.html'")
            return {'error': f"HTTP {response.status_code}"}
            
        try:
            return response.json()
        except json.JSONDecodeError:
            print("❌ Invalid JSON response!")
            print(response.text[:500])
            return {'error': 'Invalid JSON'}
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return {'error': str(e)}

def main():
    print("\n--- Debugging Eve API 500 Error ---")
    
    # Try Auto Login
    session_id, error = perform_eve_login()
    
    if not session_id:
        print(f"❌ Auto-Login Failed: {error}")
        return

    print(f"✅ Login Success! Session ID: {session_id[:10]}...")
    
    from datetime import datetime
    today = datetime.now().strftime("%d/%m/%Y")
    
    # Test 1: Standard Request using app.fetch_data_from_api
    print("\n--- Test 1: Standard Request ---")
    
    # We call the APP's function directly to verify everything including headers, retries, etc.
    from app import fetch_data_from_api
    
    # Note: app.fetch_data_from_api returns a dict, not a request object
    result = fetch_data_from_api(
        session_id=session_id,
        branch_id='231',
        date_start=today,
        date_end=today
    )
    
    if 'error' in result:
         print(f"❌ API returned error: {result['error']}")
    else:
         print(f"✅ API Success! Records: {result.get('recordsTotal')}")
         
    # Optional: Check dynamic params
    from app import get_dynamic_params
    params = get_dynamic_params()
    if params:
        print(f"ℹ️ Current Dynamic Params: {params}")


if __name__ == "__main__":
    main()
