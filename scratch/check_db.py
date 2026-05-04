
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from turso_handler import TursoHandler

def check_db():
    turso = TursoHandler()
    print(f"Connected to: {turso.url}")
    
    print("\n📋 Tables List:")
    res = turso._execute_sql("SELECT name FROM sqlite_master WHERE type='table'")
    if res:
        for row in res.rows:
            print(f" - {row[0]}")
            
    print("\n📊 Rows Count:")
    for table in ['trades', 'sync_history']:
        try:
            res = turso._execute_sql(f"SELECT COUNT(*) FROM {table}")
            if res:
                print(f" - {table}: {res.rows[0][0]} rows")
        except:
            print(f" - {table}: Table not found")
            
    turso.close()

if __name__ == "__main__":
    check_db()
