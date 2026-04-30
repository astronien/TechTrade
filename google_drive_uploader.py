# Google Drive Uploader Module
# ใช้ Service Account สำหรับ upload ไฟล์ Excel ไป Google Drive อัตโนมัติ

import json
import os
import tempfile
from datetime import datetime

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False
    print("⚠️ Google Drive libraries not installed. Install: pip install google-api-python-client google-auth")


class GoogleDriveUploader:
    """จัดการ Google Drive: สร้าง folder, upload, delete, FIFO"""
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(self, credentials_json=None):
        """
        Initialize uploader
        Args:
            credentials_json: Service Account JSON string หรือ dict
        """
        self.service = None
        self.credentials = None
        
        if not GDRIVE_AVAILABLE:
            print("❌ Google Drive libraries not available")
            return
            
        if credentials_json:
            self.authenticate(credentials_json)
    
    def authenticate(self, credentials_json):
        """Authenticate with Service Account
        Args:
            credentials_json: JSON string หรือ dict ของ Service Account credentials
        Returns:
            bool: True ถ้าสำเร็จ
        """
        try:
            if isinstance(credentials_json, str):
                creds_dict = json.loads(credentials_json)
            elif isinstance(credentials_json, dict):
                creds_dict = credentials_json
            else:
                print("❌ Invalid credentials format")
                return False
            
            self.credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=self.SCOPES
            )
            self.service = build('drive', 'v3', credentials=self.credentials)
            print("✅ Google Drive authenticated successfully")
            return True
        except Exception as e:
            print(f"❌ Google Drive authentication failed: {e}")
            return False
    
    def _ensure_service(self):
        """ตรวจสอบว่ามี service พร้อมใช้งาน"""
        if not self.service:
            raise Exception("Google Drive service not initialized. Call authenticate() first.")
    
    def find_folder(self, folder_name, parent_id=None):
        """ค้นหา folder ที่มีอยู่แล้ว
        Args:
            folder_name: ชื่อ folder
            parent_id: ID ของ parent folder (optional)
        Returns:
            str: folder ID หรือ None ถ้าไม่พบ
        """
        self._ensure_service()
        try:
            safe_name = folder_name.replace("'", "\\'")
            query = f"name='{safe_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
        except Exception as e:
            print(f"❌ Error finding folder '{folder_name}': {e}")
            return None
    
    def create_folder(self, folder_name, parent_id=None):
        """สร้าง folder ใน Google Drive (ถ้ายังไม่มี)
        Args:
            folder_name: ชื่อ folder
            parent_id: ID ของ parent folder (optional)
        Returns:
            str: folder ID
        """
        self._ensure_service()
        
        # ตรวจสอบว่ามีอยู่แล้วหรือไม่
        existing_id = self.find_folder(folder_name, parent_id)
        if existing_id:
            print(f"📁 Folder '{folder_name}' already exists: {existing_id}")
            return existing_id
        
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            print(f"✅ Created folder '{folder_name}': {folder_id}")
            return folder_id
        except Exception as e:
            print(f"❌ Error creating folder '{folder_name}': {e}")
            return None
    
    def ensure_folder_path(self, root_folder_id, zone_name, year_month):
        """สร้าง folder path: root > zone_name > YYYY-MM
        Args:
            root_folder_id: Root folder ID ใน Google Drive
            zone_name: ชื่อ Zone
            year_month: เดือน format "YYYY-MM"
        Returns:
            str: month folder ID
        """
        try:
            # สร้าง Zone folder
            print(f"📁 Creating zone folder '{zone_name}' in root {root_folder_id}")
            zone_folder_id = self.create_folder(zone_name, root_folder_id)
            if not zone_folder_id:
                print(f"❌ Failed to create zone folder '{zone_name}'")
                return None
            
            # สร้าง Month folder
            print(f"📁 Creating month folder '{year_month}' in zone {zone_folder_id}")
            month_folder_id = self.create_folder(year_month, zone_folder_id)
            if not month_folder_id:
                print(f"❌ Failed to create month folder '{year_month}'")
                return None
            
            return month_folder_id
        except Exception as e:
            print(f"❌ Error in ensure_folder_path: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_file(self, filepath, folder_id, filename=None):
        """Upload ไฟล์ไป Google Drive
        Args:
            filepath: path ของไฟล์ local
            folder_id: Google Drive folder ID
            filename: ชื่อไฟล์ที่ต้องการ (ถ้าไม่ระบุใช้ชื่อเดิม)
        Returns:
            dict: {'id': file_id, 'name': filename, 'webViewLink': url} หรือ None
        """
        self._ensure_service()
        
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            return None
        
        if not filename:
            filename = os.path.basename(filepath)
        
        try:
            # ตรวจสอบว่ามีไฟล์ชื่อเดียวกันอยู่แล้วหรือไม่
            existing = self._find_file(filename, folder_id)
            
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            # Determine MIME type
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            if filepath.endswith('.csv'):
                mime_type = 'text/csv'
            elif filepath.endswith('.json'):
                mime_type = 'application/json'
            
            media = MediaFileUpload(filepath, mimetype=mime_type, resumable=True)
            
            if existing:
                # Update existing file
                file = self.service.files().update(
                    fileId=existing['id'],
                    body={'name': filename},
                    media_body=media,
                    fields='id, name, webViewLink'
                ).execute()
                print(f"🔄 Updated file '{filename}': {file.get('id')}")
            else:
                # Create new file
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink'
                ).execute()
                print(f"✅ Uploaded file '{filename}': {file.get('id')}")
            
            return {
                'id': file.get('id'),
                'name': file.get('name'),
                'webViewLink': file.get('webViewLink', '')
            }
        except Exception as e:
            print(f"❌ Error uploading file '{filename}': {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_file(self, filename, folder_id):
        """ค้นหาไฟล์ที่มีชื่อตรงกันใน folder
        Returns:
            dict: {'id': ...} หรือ None
        """
        try:
            safe_name = filename.replace("'", "\\'")
            query = f"name='{safe_name}' and '{folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            files = results.get('files', [])
            return files[0] if files else None
        except Exception:
            return None
    
    def list_files(self, folder_id, order_by='createdTime'):
        """ลิสต์ไฟล์ใน folder
        Args:
            folder_id: Google Drive folder ID
            order_by: 'createdTime' หรือ 'name'
        Returns:
            list: [{'id', 'name', 'createdTime'}, ...]
        """
        self._ensure_service()
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
                spaces='drive',
                fields='files(id, name, createdTime)',
                orderBy=order_by,
                pageSize=500
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"❌ Error listing files: {e}")
            return []
    
    def list_all_zone_files(self, root_folder_id, zone_name):
        """นับไฟล์ทั้งหมดใน Zone (ทุก month folder)
        Returns:
            list: [{'id', 'name', 'createdTime', 'month_folder'}, ...] เรียงตาม createdTime
        """
        self._ensure_service()
        all_files = []
        
        try:
            # หา Zone folder
            zone_folder_id = self.find_folder(zone_name, root_folder_id)
            if not zone_folder_id:
                return []
            
            # หา month folders ทั้งหมดใน zone
            results = self.service.files().list(
                q=f"'{zone_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)',
                orderBy='name',
                pageSize=100
            ).execute()
            
            month_folders = results.get('files', [])
            
            for mf in month_folders:
                files = self.list_files(mf['id'], order_by='createdTime')
                for f in files:
                    f['month_folder_id'] = mf['id']
                    f['month_folder_name'] = mf['name']
                all_files.extend(files)
            
            # เรียงตาม createdTime (oldest first)
            all_files.sort(key=lambda x: x.get('createdTime', ''))
            
            return all_files
        except Exception as e:
            print(f"❌ Error listing zone files: {e}")
            return []
    
    def delete_file(self, file_id):
        """ลบไฟล์จาก Google Drive
        Args:
            file_id: Google Drive file ID
        Returns:
            bool: True ถ้าสำเร็จ
        """
        self._ensure_service()
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"🗑️ Deleted file: {file_id}")
            return True
        except Exception as e:
            print(f"❌ Error deleting file {file_id}: {e}")
            return False
    
    def fifo_cleanup(self, root_folder_id, zone_name, max_files=365):
        """FIFO cleanup: ลบไฟล์เก่าสุดเมื่อเกิน max_files
        Args:
            root_folder_id: Root folder ID
            zone_name: ชื่อ Zone
            max_files: จำนวนไฟล์สูงสุดที่เก็บ (default 365 = 1 ปี)
        Returns:
            int: จำนวนไฟล์ที่ลบ
        """
        all_files = self.list_all_zone_files(root_folder_id, zone_name)
        
        total_files = len(all_files)
        deleted_count = 0
        
        if total_files <= max_files:
            print(f"✅ Zone '{zone_name}': {total_files}/{max_files} files, no cleanup needed")
            return 0
        
        # ลบไฟล์เก่าสุด (FIFO)
        files_to_delete = total_files - max_files
        print(f"🗑️ Zone '{zone_name}': {total_files} files, deleting {files_to_delete} oldest files")
        
        for i in range(files_to_delete):
            file_to_delete = all_files[i]
            success = self.delete_file(file_to_delete['id'])
            if success:
                deleted_count += 1
                print(f"   🗑️ Deleted: {file_to_delete['name']} (from {file_to_delete.get('month_folder_name', '?')})")
        
        # ลบ month folder ที่ว่างเปล่า
        self._cleanup_empty_month_folders(root_folder_id, zone_name)
        
        print(f"✅ FIFO cleanup complete: deleted {deleted_count} files from zone '{zone_name}'")
        return deleted_count
    
    def _cleanup_empty_month_folders(self, root_folder_id, zone_name):
        """ลบ month folders ที่ไม่มีไฟล์เหลืออยู่"""
        try:
            zone_folder_id = self.find_folder(zone_name, root_folder_id)
            if not zone_folder_id:
                return
            
            results = self.service.files().list(
                q=f"'{zone_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)',
                pageSize=100
            ).execute()
            
            for folder in results.get('files', []):
                files = self.list_files(folder['id'])
                if not files:
                    self.delete_file(folder['id'])
                    print(f"   🗑️ Deleted empty month folder: {folder['name']}")
        except Exception as e:
            print(f"⚠️ Error cleaning empty folders: {e}")
    
    def test_connection(self):
        """ทดสอบการเชื่อมต่อ Google Drive
        Returns:
            dict: {'success': bool, 'message': str, 'email': str}
        """
        if not GDRIVE_AVAILABLE:
            return {'success': False, 'message': 'Google Drive libraries not installed'}
        
        if not self.service:
            return {'success': False, 'message': 'Not authenticated'}
        
        try:
            about = self.service.about().get(fields='user').execute()
            user_email = about.get('user', {}).get('emailAddress', 'unknown')
            return {
                'success': True,
                'message': f'Connected as {user_email}',
                'email': user_email
            }
        except Exception as e:
            return {'success': False, 'message': f'Connection failed: {str(e)}'}
