import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("POSTGRES_URL_NON_POOLING") or os.environ.get("DATABASE_URL")

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("--- Table Schema: auto_export_log ---")
    cur.execute("""
        SELECT column_name, data_type, column_default 
        FROM information_schema.columns 
        WHERE table_name = 'auto_export_log'
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(row)

    print("\n--- Table Schema: auto_export_config ---")
    cur.execute("""
        SELECT column_name, data_type, column_default 
        FROM information_schema.columns 
        WHERE table_name = 'auto_export_config'
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
