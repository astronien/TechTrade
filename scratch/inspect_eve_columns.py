
import requests
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ข้อมูลสำหรับ Login (ใช้จาก ENV หรือระบุตรงๆ สำหรับการ Test)
USERNAME = os.environ.get('EVE_USERNAME')
PASSWORD = os.environ.get('EVE_PASSWORD')
API_URL = "https://tradein.evetechswop.com/WebServices/TechswopWebService.asmx/SearchTradeInDataTable"
LOGIN_URL = "https://tradein.evetechswop.com/WebServices/TechswopWebService.asmx/Login"

def get_all_columns():
    with requests.Session() as session:
        # 1. Login
        login_payload = {"username": USERNAME, "password": PASSWORD}
        login_res = session.post(LOGIN_URL, json=login_payload)
        if not login_res.ok:
            print("❌ Login Failed")
            return
        
        # 2. Fetch Sample Data (1 record is enough)
        payload = {
            "draw": 1,
            "start": 0,
            "length": 1,
            "branch_id": "1635", # ใช้สาขาตัวอย่าง
            "sale_code": "",
            "date_start": "01/05/2026",
            "date_end": "03/05/2026",
            "status": "",
            "brand": [],
            "series": "",
            "doc_ref_number": "",
            "promo_code": "",
            "customer_sign": "0"
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        response = session.post(API_URL, headers=headers, json=payload)
        if not response.ok:
            print(f"❌ Fetch Failed: {response.status_code}")
            return
        
        result = response.json()
        data = result.get('d', {}).get('data', [])
        
        if not data:
            print("📭 No data found to analyze columns.")
            return
        
        first_record = data[0]
        print("\n=== All Columns Found in Eve API ===")
        all_keys = sorted(first_record.keys())
        for i, key in enumerate(all_keys, 1):
            print(f"{i}. {key}")
        
        # แสดงตัวอย่างข้อมูล
        print("\n=== Sample Data ===")
        print(json.dumps(first_record, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    get_all_columns()
