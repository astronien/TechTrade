
import os
import sys

# เพิ่ม path เพื่อให้ import turso_handler ได้
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# โหลด .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip('"').strip("'")

from turso_handler import TursoHandler

def rebuild_optimized():
    print("🚀 Starting Optimized Sync History Rebuild...")
    turso = TursoHandler()
    
    if not turso.client and not turso.url:
        print("❌ Turso connection not configured.")
        return

    # 1. Rebuild Daily History (YYYY-MM-DD format)
    print("📝 Rebuilding Daily Sync History...")
    sql_daily = """
        INSERT OR REPLACE INTO sync_history (branch_id, sync_date, record_count)
        SELECT 
            real_branch_id as branch_id,
            SUBSTR(document_date, 1, 10) as sync_date,
            COUNT(*) as record_count
        FROM trades
        GROUP BY real_branch_id, sync_date;
    """
    try:
        turso._execute_sql(sql_daily)
        print("   ✅ Daily history rebuilt successfully.")
    except Exception as e:
        print(f"   ❌ Error rebuilding daily history: {e}")

    # 2. Rebuild Monthly History (DD/MM/YYYY-DD/MM/YYYY format)
    # This is a bit complex in SQLite/libSQL but doable.
    # We'll fetch the month-branch groups and format them in Python to be safe.
    print("📝 Rebuilding Monthly Sync History...")
    sql_months = """
        SELECT 
            real_branch_id, 
            SUBSTR(document_date, 1, 7) as month_key, 
            COUNT(*) as count
        FROM trades
        GROUP BY real_branch_id, month_key
    """
    try:
        res = turso._execute_sql(sql_months)
        if res and res.rows:
            import calendar
            from datetime import datetime
            
            monthly_entries = []
            for row in res.rows:
                bid, m_key, count = str(row[0]), str(row[1]), int(row[2])
                # m_key is YYYY-MM
                y, m = map(int, m_key.split('-'))
                last_day = calendar.monthrange(y, m)[1]
                
                # Format: 01/MM/YYYY-DD/MM/YYYY
                range_key = f"01/{m:02d}/{y}-{last_day:02d}/{m:02d}/{y}"
                monthly_entries.append((bid, range_key, count))
            
            # Batch mark monthly (still individual calls but much fewer than daily)
            success = 0
            for bid, key, count in monthly_entries:
                if turso.mark_synced(bid, key, count):
                    success += 1
            print(f"   ✅ {success} monthly entries rebuilt.")
    except Exception as e:
        print(f"   ❌ Error rebuilding monthly history: {e}")

    print("\n✨ Optimized Rebuild Complete!")
    turso.close()

if __name__ == "__main__":
    rebuild_optimized()
