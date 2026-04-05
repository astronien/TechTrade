import requests
import json
from datetime import datetime

# API endpoint
url = "https://sellpromotion.remobie.com/api/getBiddingList"

# Request parameters for a February test
payload = {
    "start": 0,
    "length": 10,  # Just 10 items
    "columns": [{"data": "document_no", "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False}}],
    "order": [{"column": 0, "dir": "asc"}],
    "search": {"value": "", "regex": False},
    "dateStart": "01/02/2026",
    "dateEnd": "28/02/2026",
    "machineCode": "",
    "customerEmail": "",
    "dealerDocNo": "",
    "dealerId": "",
    "saleCode": "",
    "branchId": "1847", # Assuming some branch ID that has data
    "pageType": "1",
    "status": "",
    "customerSign": "",
    "sessionId": "",
    "category": "",
    "brand": "",
    "series": "",
    "color": "",
    "capacity": "",
}

try:
    response = requests.post(url, json=payload, timeout=20)
    data = response.json()
    
    if data.get('data'):
        print(f"Found {len(data['data'])} items.")
        for item in data['data'][:5]:
            print("---")
            print(f"Doc No: {item.get('document_no')}")
            print(f"SALE_CODE: '{item.get('SALE_CODE')}'")
            print(f"SALE_NAME: '{item.get('SALE_NAME')}'")
    else:
        print("No data found or error:", data)
except Exception as e:
    print("Error:", e)
