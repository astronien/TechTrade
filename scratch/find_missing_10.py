import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add path for turso_handler
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

try:
    from turso_handler import TursoHandler
except ImportError as e:
    print(f"❌ Error importing TursoHandler: {e}")
    sys.exit(1)

def find_missing_10():
    turso = TursoHandler()
    print("🔍 Deep Scanning for Branch 645 (April 2026)...")
    
    # ดึงข้อมูลทุกอย่างที่อาจจะเกี่ยวกับ Westgate หรือ 645
    query = """
        SELECT 
            branch_name, 
            real_branch_id,
            document_date,
            document_no
        FROM trades 
        WHERE substr(document_date, 1, 10) BETWEEN '2026-04-01' AND '2026-04-30'
          AND (branch_name LIKE '%Westgate%' OR real_branch_id='645' OR branch_name LIKE '%645%')
    """
    
    try:
        result = turso._execute_sql(query)
        if result and result.rows:
            print(f"✅ Found total {len(result.rows)} candidates in Turso.")
            
            # แยกกลุ่มตามสาขาที่เจอ
            groups = {}
            for row in result.rows:
                key = f"{row[0]} (ID: {row[1]})"
                if key not in groups: groups[key] = 0
                groups[key] += 1
            
            for key, count in groups.items():
                print(f"   📍 {key}: {count} records")
                
            if len(result.rows) == 441:
                print("\n✨ Confirmed: Turso has exactly 441 records for Westgate criteria.")
            else:
                print(f"\n⚠️ Note: Total found {len(result.rows)} is not 441. Checking ALL April data for 645 pattern...")
                
        else:
            print("⚠️ No matching records found.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        turso.close()

if __name__ == "__main__":
    find_missing_10()
