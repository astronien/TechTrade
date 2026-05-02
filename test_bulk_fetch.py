import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# เพิ่ม path เพื่อให้ import app.py ได้
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import fetch_all_for_branch
except ImportError as e:
    print(f"❌ Error importing from app.py: {e}")
    sys.exit(1)

def test_bulk_fetch():
    # วันที่วันนี้ (รูปแบบ dd/mm/yyyy)
    target_date = datetime.now().strftime("%d/%m/%Y")
    
    # หรือถ้าอยากระบุวันที่เจาะจง (เช่น วันที่ user ขอคือ 02/05/2026)
    # target_date = "02/05/2026"
    
    print(f"🚀 Starting Bulk Fetch Test for ALL BRANCHES (ID: 0)")
    print(f"📅 Date: {target_date}")
    
    filters = {
        'date_start': target_date,
        'date_end': target_date,
        'sale_code': '',
        'customer_sign': '',
        'branch_id': '0'  # รหัส 0 คือดึงทั้งประเทศ
    }
    
    try:
        print("⏳ Fetching data... (This may take a while if there are many records)")
        items = fetch_all_for_branch(filters)
        
        print("\n" + "="*50)
        print(f"✅ Fetch Complete!")
        print(f"📊 Total Records Found: {len(items)}")
        print("="*50)
        
        if items:
            # วิเคราะห์ข้อมูลเบื้องต้น
            branches_found = set()
            total_amount = 0
            
            for item in items:
                branches_found.add(item.get('branch_name', 'Unknown'))
                try:
                    total_amount += float(item.get('amount', 0) or 0)
                except: pass
            
            print(f"🏢 Unique Branches in Data: {len(branches_found)}")
            print(f"💰 Total Amount Sum: {total_amount:,.2f}")
            print("-" * 30)
            
            # แสดงตัวอย่าง 3 รายการแรก
            print("📝 Sample Data (Top 3):")
            for i, item in enumerate(items[:3]):
                print(f"   [{i+1}] Branch: {item.get('branch_name')} (ID: {item.get('branch_id')})")
                print(f"       Doc No: {item.get('document_no')}")
                print(f"       Product: {item.get('series')}")
                print(f"       Status: {item.get('BIDDING_STATUS_NAME')}")
                print(f"       Amount: {item.get('amount')}")
                print("-" * 20)
        else:
            print("⚠️ No data found for today.")
            print("💡 Tip: Make sure the Eve system has data for this date.")
            
    except Exception as e:
        print(f"❌ Error during fetch: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bulk_fetch()
