import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app import get_db_connection

def test_fetch():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM system_settings WHERE key = 'supersale_branch_ids'")
    row = cur.fetchone()
    if row:
        print("supersale_branch_ids:", row['value'])
    else:
        print("Not found in DB")
    cur.close()
    conn.close()

if __name__ == '__main__':
    test_fetch()
