import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DB_URL = os.environ.get("POSTGRES_URL_NON_POOLING") or os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No database URL found (POSTGRES_URL_NON_POOLING or DATABASE_URL).")
    exit(1)

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("--- Recent Auto Export Logs ---")
    cur.execute("SELECT * FROM auto_export_log ORDER BY run_at DESC LIMIT 10")
    rows = cur.fetchall()

    for row in rows:
        print(f"Time: {row['run_at']} | Zone: {row['zone_name']} | Status: {row['status']} | Records: {row['total_records']} | Error: {row['error_message']}")

    print("\n--- Config Status ---")
    cur.execute("SELECT enabled, schedule_time FROM auto_export_config LIMIT 1")
    config = cur.fetchone()
    if config:
        print(f"Enabled: {config['enabled']} | Schedule: {config['schedule_time']}")
    else:
        print("No config found in auto_export_config table.")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
