import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No DATABASE_URL found.")
    exit(1)

conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("SELECT * FROM auto_cancel_log ORDER BY run_at DESC LIMIT 20")
rows = cur.fetchall()

for row in rows:
    print(f"Log ID: {row['id']} | Time (UTC): {row['run_at']} | Found: {row.get('total_found')} | Cancelled: {row.get('total_cancelled')} | Details: {row.get('details', '')[:100]}")

cur.close()
conn.close()
