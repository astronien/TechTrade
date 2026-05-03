import os, requests
from dotenv import load_dotenv

def recreate():
    load_dotenv()
    url = os.environ.get('TURSO_DATABASE_URL').replace('libsql://', 'https://')
    token = os.environ.get('TURSO_AUTH_TOKEN')
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    # คำสั่งทุบทิ้ง
    drop_stmts = [
        {'type': 'execute', 'stmt': {'sql': 'DROP TABLE IF EXISTS trades'}},
        {'type': 'execute', 'stmt': {'sql': 'DROP TABLE IF EXISTS sync_history'}}
    ]
    
    # คำสั่งสร้างใหม่พร้อม real_branch_id
    create_stmts = [
        {'type': 'execute', 'stmt': {'sql': """
            CREATE TABLE trades (
                trade_in_id TEXT PRIMARY KEY,
                branch_id TEXT,
                real_branch_id TEXT,
                branch_name TEXT,
                document_no TEXT,
                document_date TEXT,
                IS_SIGNED INTEGER,
                SIGN_DATE TEXT,
                series TEXT,
                brand_name TEXT,
                category_name TEXT,
                part_number TEXT,
                amount REAL,
                net_price REAL,
                COUPON_TRADE_IN_CODE TEXT,
                invoice_no TEXT,
                CAMPAIGN_ON_TOP_NAME TEXT,
                COUPON_ON_TOP_BRAND_CODE TEXT,
                COUPON_ON_TOP_BRAND_PRICE REAL,
                COUPON_ON_TOP_COMPANY_CODE TEXT,
                COUPON_ON_TOP_COMPANY_PRICE REAL,
                SALE_NAME TEXT,
                SALE_CODE TEXT,
                employee_name TEXT,
                customer_name TEXT,
                customer_phone_number TEXT,
                customer_email TEXT,
                customer_tax_no TEXT,
                buyer_name TEXT,
                BIDDING_STATUS_NAME TEXT,
                DOCUMENT_REF_1 TEXT,
                CHANGE_REQUEST_COUNT INTEGER,
                status TEXT,
                grade TEXT,
                cosmetic TEXT,
                ontop_amount REAL,
                campaign_name TEXT,
                zone_name TEXT
            )
        """}},
        {'type': 'execute', 'stmt': {'sql': """
            CREATE TABLE sync_history (
                branch_id TEXT,
                sync_date TEXT,
                record_count INTEGER,
                last_sync_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (branch_id, sync_date)
            )
        """}}
    ]
    
    print("🗑️ Dropping tables...")
    r1 = requests.post(f'{url}/v2/pipeline', headers=headers, json={'requests': drop_stmts})
    print(f"Drop Status: {r1.status_code}")
    
    print("🏗️ Creating tables with real_branch_id...")
    r2 = requests.post(f'{url}/v2/pipeline', headers=headers, json={'requests': create_stmts})
    print(f"Create Status: {r2.status_code}")
    if r2.status_code == 200:
        print("✅ Success! Table 'trades' now has 'real_branch_id' column.")
    else:
        print(f"❌ Error: {r2.text}")

if __name__ == "__main__":
    recreate()
