from app import fetch_data_from_api
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

load_dotenv()
target_date = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
print("Testing payload filtering for:", target_date)

# Try with no status
res_none = fetch_data_from_api(
    start=0, length=200, branch_id="231",
    date_start=target_date, date_end=target_date, status=""
)
data_none = res_none.get('data', [])
print(f"\n--- No status: Found {len(data_none)} items ---")
if data_none:
    statuses = set([i.get('BIDDING_STATUS_NAME') for i in data_none])
    print("Available statuses:", statuses)
    pending = [i for i in data_none if i.get('BIDDING_STATUS_NAME') == 'รอผู้ขายยืนยันราคา']
    print(f"Pending items: {len(pending)}")

# Try with '3'
res_3 = fetch_data_from_api(
    start=0, length=200, branch_id="231",
    date_start=target_date, date_end=target_date, status="3"
)
data_3 = res_3.get('data', [])
print(f"\n--- Status '3': Found {len(data_3)} items ---")

