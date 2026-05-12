import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("POSTGRES_URL_NON_POOLING") or os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No database URL found.")
    exit(1)

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("--- Recent Debug Logs ---")
    cur.execute("SELECT * FROM debug_logs ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()

    for row in rows:
        print(f"[{row['created_at']}] {row['message']}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
