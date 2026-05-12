import os
from dotenv import load_dotenv
from auto_daily_export import run_daily_export

load_dotenv()

# Ensure we have the necessary env vars for the script to run
# Note: auto_daily_export.py imports from app.py, so we need app's env vars too
os.environ['POSTGRES_URL_NON_POOLING'] = os.environ.get('POSTGRES_URL_NON_POOLING', '')

print("🚀 Starting manual Turso sync test...")
result = run_daily_export(force=True)
print("\n--- Sync Result ---")
print(result)
