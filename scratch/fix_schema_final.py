import os, requests
from dotenv import load_dotenv

def fix():
    load_dotenv()
    url = os.environ.get('TURSO_DATABASE_URL').replace('libsql://', 'https://')
    token = os.environ.get('TURSO_AUTH_TOKEN')
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    # คำสั่งเพิ่มคอลัมน์ที่ขาดหายไป
    alter_stmts = [
        {'type': 'execute', 'stmt': {'sql': 'ALTER TABLE trades ADD COLUMN exported_at DATETIME DEFAULT CURRENT_TIMESTAMP'}},
    ]
    
    print("🛠️ Adding missing column 'exported_at'...")
    resp = requests.post(f'{url}/v2/pipeline', headers=headers, json={'requests': alter_stmts})
    
    if resp.status_code == 200:
        print("✅ Column 'exported_at' added successfully!")
    else:
        # ถ้าคอลัมน์มีอยู่แล้ว (Error) ก็ไม่เป็นไร
        print(f"ℹ️ Status: {resp.text}")

if __name__ == "__main__":
    fix()
