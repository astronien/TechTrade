import os
import psycopg2
import pytz
import datetime
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("SELECT run_at FROM auto_cancel_log ORDER BY run_at DESC LIMIT 1")
last_log = cur.fetchone()

bkk_tz = pytz.timezone('Asia/Bangkok')
now_bkk = datetime.datetime.now(bkk_tz)
today_str = now_bkk.strftime('%Y-%m-%d')
has_run_today = False

if last_log and last_log[0]:
    last_run_utc = last_log[0]
    if last_run_utc.tzinfo is None:
        last_run_utc = last_run_utc.replace(tzinfo=pytz.UTC)
    last_run_bkk = last_run_utc.astimezone(bkk_tz)
    print(f"Last run BKK: {last_run_bkk}, Today string: {today_str}")
    if last_run_bkk.strftime('%Y-%m-%d') == today_str:
        has_run_today = True

print(f"Has run today: {has_run_today}")

cur.close()
conn.close()
