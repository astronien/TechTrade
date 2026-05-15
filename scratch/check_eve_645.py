import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add path to import app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from app import fetch_all_for_branch
except ImportError as e:
    print(f"❌ Error importing from app.py: {e}")
    sys.exit(1)

def check_645():
    # ระบุช่วงวันที่ เดือนเมษายน
    start_date = "01/04/2026"
    end_date = "30/04/2026"
    branch_id = "645"
    
    print(f"🚀 Fetching Eve Data for Branch {branch_id}")
    print(f"📅 Range: {start_date} - {end_date}")
    
    filters = {
        'date_start': start_date,
        'date_end': end_date,
        'sale_code': '',
        'customer_sign': '',
        'branch_id': branch_id
    }
    
    try:
        items = fetch_all_for_branch(filters)
        print("\n" + "="*40)
        print(f"✅ Eve Fetch Complete!")
        print(f"📊 Total Records in Eve: {len(items)}")
        print("="*40)
        
        if items:
            # วิเคราะห์สถานะ
            statuses = {}
            for item in items:
                st = item.get('BIDDING_STATUS_NAME', 'Unknown')
                statuses[st] = statuses.get(st, 0) + 1
            
            print("📝 Breakdown by Status:")
            for st, count in statuses.items():
                print(f"   - {st}: {count}")
        else:
            print("⚠️ No data found in Eve for this period.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_645()
