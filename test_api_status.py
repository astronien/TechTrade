import requests
import json
from datetime import datetime, timedelta

# Get session ID (assuming debug_eve_login.py works and saves it)
import sys
sys.path.append('.')
from app import get_eve_session

session_id = get_eve_session()
print(f"Session ID: {session_id}")

target_date = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
print(f"Target Date: {target_date}")

payload = {
    "draw": 1,
    "columns": [],
    "order": [],
    "start": 0,
    "length": 50,
    "search": {"value": "", "regex": False, "fixed": []},
    "textfield": "",
    "textSearch": "",
    "textdateStart": target_date,
    "textdateEnd": target_date,
    "status": "", # Let's try empty first to see all, then we can filter
    "series": [],
    "brands": [],
    "saleCode": "",
    "branchID": "231",
    "txtSearchRef1": "",
    "txtSearchCOTN": "",
    "DocumentRef1": "",
    "customerSign": "0",
    "ufund": ""
}

headers = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/json; charset=utf-8',
    'Origin': 'https://eve.techswop.com',
    'Referer': 'https://eve.techswop.com/ti/index.aspx',
}

cookies = {'ASP.NET_SessionId': session_id} if session_id else {}

print("Fetching data with empty status...")
r = requests.post("https://eve.techswop.com/ti/index.aspx/Getdata", json=payload, headers=headers, cookies=cookies)
data = r.json()
print(f"Total records found with no status filter: {len(data.get('data', []))}")

if len(data.get('data', [])) > 0:
    statuses = set([item.get('BIDDING_STATUS_NAME') for item in data['data']])
    print(f"Available statuses: {statuses}")
    
    # Try to find one with 'รอผู้ขายยืนยันราคา'
    pending = [item for item in data['data'] if item.get('BIDDING_STATUS_NAME') == 'รอผู้ขายยืนยันราคา']
    print(f"Found {len(pending)} pending items manually")

print("\nFetching data with status='3'...")
payload['status'] = '3'
r = requests.post("https://eve.techswop.com/ti/index.aspx/Getdata", json=payload, headers=headers, cookies=cookies)
print(f"Status 3 records: {len(r.json().get('data', []))}")

print("\nFetching data with status='รอผู้ขายยืนยันราคา'...")
payload['status'] = 'รอผู้ขายยืนยันราคา'
r = requests.post("https://eve.techswop.com/ti/index.aspx/Getdata", json=payload, headers=headers, cookies=cookies)
print(f"Text status records: {len(r.json().get('data', []))}")
