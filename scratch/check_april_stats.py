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

def check_april_stats():
    turso = TursoHandler()
    print("📅 Checking April 2026 Stats from Turso...")
    
    query = """
        SELECT 
            branch_name, 
            real_branch_id,
            COUNT(*) as count
        FROM trades 
        WHERE substr(document_date, 1, 10) >= '2026-04-01' 
          AND substr(document_date, 1, 10) <= '2026-04-30'
        GROUP BY branch_name, real_branch_id
        ORDER BY count DESC
    """
    
    try:
        result = turso._execute_sql(query)
        if result and result.rows:
            print(f"✅ Found {len(result.rows)} branches with data in April.")
            print("\nTop 20 Branches in April:")
            for row in result.rows[:20]:
                print(f"   - {row[0]} (ID: {row[1]}): {row[2]} trades")
            
            # เช็คเฉพาะ 645
            print("\n🔍 Searching for Branch 645 / 1594...")
            found_645 = [r for r in result.rows if str(r[1]) == '645' or str(r[1]) == '1594' or '645' in str(row[0])]
            if found_645:
                for r in found_645:
                    print(f"   🎯 Found: {r[0]} (ID: {r[1]}): {r[2]} trades")
            else:
                print("❌ Not found in Top list. Checking all rows...")
                all_match = [r for r in result.rows if '645' in str(r[0]) or str(r[1]) == '645' or str(r[1]) == '1594']
                if all_match:
                    for r in all_match:
                        print(f"   🎯 Found in deep search: {r[0]} (ID: {r[1]}): {r[2]} trades")
                else:
                    print("❌ Branch 645 definitely has 0 records in Turso for April.")
                
        else:
            print("⚠️ No data found in Turso for April 2026.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        turso.close()

if __name__ == "__main__":
    check_april_stats()
