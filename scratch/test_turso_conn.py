
import os
import libsql_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('TURSO_DATABASE_URL')
token = os.getenv('TURSO_AUTH_TOKEN')

print(f"Testing connection to: {url}")
try:
    client = libsql_client.create_client_sync(url, auth_token=token)
    res = client.execute("SELECT 1")
    print("✅ Connection Successful!")
    client.close()
except Exception as e:
    print(f"❌ Connection Failed: {e}")
