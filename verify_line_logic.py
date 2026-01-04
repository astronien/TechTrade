# verify_line_logic.py
import os
import json
from line_bot_handler import handle_line_message

# Mock functions
def fetch_data_from_api(filters):
    return []

def load_zones_data():
    return []

def find_zone_by_name(name):
    return None

def find_branch_by_id(branch_id):
    return {"branch_name": f"สาขา {branch_id}"}

def parse_thai_month(month_str):
    return 1

def get_month_date_range(month, year):
    return "01/01/2026", "31/01/2026"

# Test Cases
test_messages = [
    "วิธีใช้",
    "help",
    "รายงาน zone พี่โอ๊ค",
    "รายงาน 9 รายวัน",
    "สวัสดี",
    "รายงาน excel รายปี 2024"
]

print("🔍 Testing handle_line_message logic:")
print("-" * 50)

for msg in test_messages:
    print(f"\nInput: '{msg}'")
    response = handle_line_message(
        msg,
        fetch_data_from_api,
        load_zones_data,
        find_zone_by_name,
        find_branch_by_id,
        parse_thai_month,
        get_month_date_range
    )
    
    if response:
        if isinstance(response, dict):
             print(f"Output: [Dictionary Type: {response.get('type')}]")
        else:
             print(f"Output: {response[:100]}...") # Print first 100 chars
    else:
        print("Output: None (Ignored)")

print("-" * 50)
print("✅ Test Complete")
