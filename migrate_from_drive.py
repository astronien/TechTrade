import os
import pandas as pd
import tempfile
import json
from datetime import datetime
from dotenv import load_dotenv

# Import handlers ของเรา
from google_drive_uploader import GoogleDriveUploader
from turso_handler import TursoHandler
from auto_daily_export import get_auto_export_config

# Load environment variables จาก .env
load_dotenv()

def migrate():
    print("\n" + "=" * 60)
    print(f"🚀 Data Migration from Google Drive to Turso Started")
    print("=" * 60)

    # 1. ดึง config
    config = get_auto_export_config()
    if not config:
        print("❌ No auto-export config found in DB")
        return
    
    root_folder_id = config.get('gdrive_folder_id')
    gdrive_creds = config.get('gdrive_credentials')
    
    if not root_folder_id or not gdrive_creds:
        print("❌ Google Drive Folder ID or Credentials not found in config")
        return

    # 2. Initialize Handlers
    uploader = GoogleDriveUploader(gdrive_creds)
    turso = TursoHandler()
    
    if not turso.init_db():
        print("❌ Failed to initialize Turso Database")
        return

    # Mapping หัวตาราง (Thai Label -> Key ใน DB)
    label_to_key = {
        'รหัสสาขา': 'branch_id',
        'ชื่อสาขา': 'branch_name',
        'เลขที่คำสั่งเทรด': 'document_no',
        'วันที่คำสั่งเทรด': 'document_date',
        'วันที่ลูกค้าคืนเครื่อง': 'SIGN_DATE',
        'สินค้า': 'series',
        'แบรนด์': 'brand_name',
        'ประเภทสินค้า': 'category_name',
        'อีมี่/ซีเรียล': 'part_number',
        'ราคายืนยัน': 'amount',
        'ราคาสุทธิ': 'net_price',
        'ชื่อพนักงานขาย': 'SALE_NAME',
        'รหัสพนักงานขาย': 'SALE_CODE',
        'ชื่อผู้ขาย': 'customer_name',
        'เบอร์โทรศัพท์ผู้ขาย': 'customer_phone_number',
        'ผู้รับซื้อ': 'buyer_name',
        'สถานะ': 'BIDDING_STATUS_NAME',
        'Trade In ID': 'trade_in_id'
    }

    # 3. ลิสต์โฟลเดอร์ใน Root (แต่ละโซน)
    try:
        results = uploader.service.files().list(
            q=f"'{root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)"
        ).execute()
        zone_folders = results.get('files', [])
    except Exception as e:
        print(f"❌ Error listing zone folders: {e}")
        return

    total_files_processed = 0
    total_rows_inserted = 0

    # 4. วนลูปแต่ละ Zone
    for zone in zone_folders:
        zone_name = zone['name']
        zone_id = zone['id']
        print(f"\n📂 Processing Zone: {zone_name}")

        # ลิสต์ไฟล์ Excel ในโซนนั้น
        try:
            results = uploader.service.files().list(
                q=f"'{zone_id}' in parents and name contains '.xlsx' and trashed=false",
                fields="files(id, name)"
            ).execute()
            files = results.get('files', [])
        except Exception as e:
            print(f"   ⚠️ Error listing files in {zone_name}: {e}")
            continue

        for file in files:
            file_name = file['name']
            file_id = file['id']
            print(f"   📄 Downloading: {file_name}")

            # สร้างไฟล์ชั่วคราว
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                tmp_path = tmp.name
            
            try:
                if uploader.download_file(file_id, tmp_path):
                    # อ่าน Excel
                    df = pd.read_excel(tmp_path)
                    
                    # แปลงคอลัมน์จากภาษาไทยเป็น Key ใน DB
                    # หาหัวตารางที่ตรงกับ mapping ของเรา
                    found_cols = {col: label_to_key[col] for col in df.columns if col in label_to_key}
                    df_mapped = df[list(found_cols.keys())].rename(columns=found_cols)
                    
                    # แปลงข้อมูลเป็น list of dicts
                    records = df_mapped.to_dict('records')
                    
                    # ส่งเข้า Turso
                    if records:
                        inserted = turso.insert_trades_batch(records, zone_name)
                        total_rows_inserted += inserted
                        print(f"   ✅ Inserted {inserted} rows from {file_name}")
                        total_files_processed += 1
                
            except Exception as e:
                print(f"   ❌ Error processing {file_name}: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    print("\n" + "=" * 60)
    print(f"🏁 Migration Completed!")
    print(f"📊 Summary:")
    print(f"   - Files Processed: {total_files_processed}")
    print(f"   - Total Rows Inserted: {total_rows_inserted:,}")
    print("=" * 60 + "\n")
    
    turso.close()

if __name__ == "__main__":
    migrate()
