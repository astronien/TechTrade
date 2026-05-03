import libsql_client
import os
import math
import requests
from datetime import datetime

class TursoHandler:
    def __init__(self, url=None, token=None):
        self.url = url or os.getenv('TURSO_DATABASE_URL')
        self.token = token or os.getenv('TURSO_AUTH_TOKEN')
        self.client = None
        
        if self.url and self.token:
            try:
                # ลองเชื่อมต่อแบบปกติ
                self.client = libsql_client.create_client_sync(self.url, auth_token=self.token)
            except Exception as e:
                print(f"⚠️ [Turso] Client init warning: {e}")
                # จะใช้ HTTP Fallback ในฟังก์ชันต่างๆ แทน

    def init_db(self):
        """สร้างตาราง trades หากยังไม่มี"""
        if not self.client:
            print("❌ Turso client not initialized")
            return False
            
        try:
            self._execute_sql("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_in_id TEXT PRIMARY KEY,
                    branch_id TEXT,
                    branch_name TEXT,
                    document_no TEXT,
                    document_date TEXT,
                    IS_SIGNED TEXT,
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
                    customer_name TEXT,
                    customer_phone_number TEXT,
                    customer_email TEXT,
                    buyer_name TEXT,
                    BIDDING_STATUS_NAME TEXT,
                    DOCUMENT_REF_1 TEXT,
                    CHANGE_REQUEST_COUNT INTEGER,
                    zone_name TEXT,
                    exported_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_zone_date ON trades(zone_name, document_date)")
            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_branch ON trades(branch_id)")
            
            print("✅ Turso table and indexes initialized")
            # 3. ตารางประวัติการ Sync (เพื่อเช็คว่าสาขาไหนดึงมาแล้ว แม้จะมี 0 รายการ)
            self._execute_sql("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    branch_id TEXT,
                    sync_date TEXT,
                    record_count INTEGER,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (branch_id, sync_date)
                )
            """)
            
            print("✅ Database tables ready")
            return True
        except Exception as e:
            print(f"❌ Database init error: {e}")
            return False

    def _execute_sql(self, sql, params=None):
        """ตัวกลางสำหรับรัน SQL พร้อมระบบ HTTP Fallback"""
        if not self.client:
            return self._execute_http(sql, params)
            
        try:
            return self.client.execute(sql, params)
        except Exception as e:
            if "505" in str(e) or "Invalid response status" in str(e):
                print("🔄 [Turso] 505 Error detected in execute. Switching to HTTP Fallback...")
                return self._execute_http(sql, params)
            raise e

    def _execute_http(self, sql, params=None):
        """ประมวลผล SQL เดี่ยวผ่าน HTTP API (v2 pipeline)"""
        url = self.url
        if not url: return None
        if url and url.startswith("libsql://"):
            url = url.replace("libsql://", "https://")
            
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": self._format_args(params)}}
            ]
        }
        
        try:
            response = requests.post(f"{url}/v2/pipeline", headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                result_data = response.json()
                # สร้าง Mock Result Object
                class MockResult:
                    def __init__(self, res_obj):
                        self.columns = [c['name'] for c in res_obj['cols']]
                        self.rows = []
                        for r in res_obj['rows']:
                            row_vals = []
                            for val in r:
                                if isinstance(val, dict) and "value" in val:
                                    row_vals.append(val.get('value'))
                                else:
                                    row_vals.append(val)
                            self.rows.append(row_vals)
                
                res_obj = result_data['results'][0]['response']['result']
                return MockResult(res_obj)
            else:
                return None
        except Exception as e:
            print(f"❌ [Turso Fallback] Error: {e}")
            return None

    def _format_args(self, params):
        """แปลง Python params เป็น Turso HTTP API format"""
        if not params: return []
        formatted = []
        for p in params:
            if p is None:
                formatted.append({"type": "null"})
            elif isinstance(p, bool):
                formatted.append({"type": "integer", "value": "1" if p else "0"})
            elif isinstance(p, int):
                formatted.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                formatted.append({"type": "float", "value": p})
            else:
                formatted.append({"type": "text", "value": str(p)})
        return formatted

    def is_synced(self, branch_id, sync_date):
        """ตรวจสอบว่าสาขานี้ในวันที่นี้ถูก Sync แล้วหรือยัง"""
        try:
            # แปลงวันที่เป็น format SQL (YYYY-MM-DD)
            if '-' not in sync_date and '/' in sync_date:
                try:
                    parts = sync_date.split('/')
                    if len(parts) == 3:
                        d, m, y = parts
                        sync_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except:
                    pass
                    
            res = self._execute_sql(
                "SELECT branch_id FROM sync_history WHERE branch_id = ? AND sync_date = ?",
                [str(branch_id), sync_date]
            )
            return res and len(res.rows) > 0
        except:
            return False

    def mark_synced(self, branch_id, sync_date, count):
        """บันทึกว่าสาขานี้ในวันที่นี้ดึงข้อมูลมาแล้ว"""
        try:
            # ถ้าเป็นช่วงวันที่ (มีขีดกลาง) ไม่ต้องพยายามแปลงเป็น SQL date แบบละเอียด
            if '-' not in sync_date and '/' in sync_date:
                try:
                    parts = sync_date.split('/')
                    if len(parts) == 3:
                        d, m, y = parts
                        sync_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except:
                    pass
                
            self._execute_sql(
                "INSERT OR REPLACE INTO sync_history (branch_id, sync_date, record_count) VALUES (?, ?, ?)",
                [str(branch_id), sync_date, count]
            )
            return True
        except Exception as e:
            print(f"⚠️ [Turso] mark_synced error: {e}")
            return False

    def _clean_val(self, val, default=None, is_num=False):
        """จัดการค่า NaN หรือ Null ให้เป็นค่าที่ Database รับได้"""
        if val is None:
            return 0.0 if is_num else default
            
        # ถ้าเป็น float และเป็น NaN หรือ Infinity
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return 0.0 if is_num else default
            return val
            
        # ถ้าเป็น string
        if isinstance(val, str):
            if val.lower() in ['nan', 'none', 'null', '']:
                return 0.0 if is_num else default
            return val
            
        return val

    def insert_trades_batch(self, trades_data, zone_name):
        """บันทึกข้อมูลแบบ Batch"""
        if not trades_data:
            return 0
            
        try:
            print(f"📦 [Turso] Attempting to insert {len(trades_data)} records...")
            stmts = []
            for item in trades_data:
                # จัดการ trade_in_id (ลองทั้งตัวเล็กและตัวใหญ่)
                trade_in_id = item.get('trade_in_id') or item.get('TRADE_IN_ID')
                trade_in_id = self._clean_val(trade_in_id)
                
                if not trade_in_id:
                    continue
                
                # ทำความสะอาดข้อมูลอื่นๆ
                # ข้อมูลหลัก
                branch_id = str(self._clean_val(item.get('branch_id'), ""))
                branch_name = self._clean_val(item.get('branch_name'), "")
                document_no = self._clean_val(item.get('document_no'), "")
                document_date = self._clean_val(item.get('document_date'), "")
                is_signed = self._clean_val(item.get('IS_SIGNED'), "")
                sign_date = self._clean_val(item.get('SIGN_DATE'), "")
                series = self._clean_val(item.get('series'), "")
                brand_name = self._clean_val(item.get('brand_name'), "")
                category_name = self._clean_val(item.get('category_name'), "")
                part_number = self._clean_val(item.get('part_number'), "")
                
                amount = float(self._clean_val(item.get('amount', 0), 0, True))
                
                # คูปองและ Campaign
                coupon_trade_in = self._clean_val(item.get('COUPON_TRADE_IN_CODE'), "")
                invoice_no = self._clean_val(item.get('invoice_no'), "")
                campaign_name = self._clean_val(item.get('CAMPAIGN_ON_TOP_NAME'), "")
                brand_coupon_code = self._clean_val(item.get('COUPON_ON_TOP_BRAND_CODE'), "")
                brand_coupon_price = float(self._clean_val(item.get('COUPON_ON_TOP_BRAND_PRICE', 0), 0, True))
                company_coupon_code = self._clean_val(item.get('COUPON_ON_TOP_COMPANY_CODE'), "")
                company_coupon_price = float(self._clean_val(item.get('COUPON_ON_TOP_COMPANY_PRICE', 0), 0, True))

                # คำนวณ net_price
                if 'net_price' in item:
                    net_price = float(self._clean_val(item.get('net_price', 0), 0, True))
                else:
                    net_price = amount + brand_coupon_price + company_coupon_price

                # ข้อมูลพนักงานและลูกค้า
                sale_name = self._clean_val(item.get('SALE_NAME'), "")
                sale_code = self._clean_val(item.get('SALE_CODE'), "")
                customer_name = self._clean_val(item.get('customer_name'), "")
                customer_phone = self._clean_val(item.get('customer_phone_number'), "")
                customer_email = self._clean_val(item.get('customer_email'), "")
                buyer_name = self._clean_val(item.get('buyer_name'), "")
                bidding_status = self._clean_val(item.get('BIDDING_STATUS_NAME'), "")
                doc_ref_1 = self._clean_val(item.get('DOCUMENT_REF_1'), "")
                change_count = int(self._clean_val(item.get('CHANGE_REQUEST_COUNT', 0), 0, True))

                stmts.append(libsql_client.Statement(
                    """
                    INSERT OR REPLACE INTO trades 
                    (trade_in_id, branch_id, branch_name, document_no, document_date, 
                     IS_SIGNED, SIGN_DATE, series, brand_name, category_name, part_number, 
                     amount, net_price, COUPON_TRADE_IN_CODE, invoice_no, 
                     CAMPAIGN_ON_TOP_NAME, COUPON_ON_TOP_BRAND_CODE, COUPON_ON_TOP_BRAND_PRICE,
                     COUPON_ON_TOP_COMPANY_CODE, COUPON_ON_TOP_COMPANY_PRICE,
                     SALE_NAME, SALE_CODE, customer_name, customer_phone_number, customer_email,
                     buyer_name, BIDDING_STATUS_NAME, DOCUMENT_REF_1, CHANGE_REQUEST_COUNT, zone_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(trade_in_id), branch_id, branch_name, document_no, document_date,
                        is_signed, sign_date, series, brand_name, category_name, part_number,
                        amount, net_price, coupon_trade_in, invoice_no,
                        campaign_name, brand_coupon_code, brand_coupon_price,
                        company_coupon_code, company_coupon_price,
                        sale_name, sale_code, customer_name, customer_phone, customer_email,
                        buyer_name, bidding_status, doc_ref_1, change_count, zone_name
                    ]
                ))
            
            if stmts:
                print(f"⚡ [Turso] Executing batch of {len(stmts)} statements...")
                try:
                    if self.client:
                        self.client.batch(stmts)
                        print(f"✅ [Turso] Successfully inserted/updated {len(stmts)} records")
                    else:
                        print("🔄 [Turso] No client found. Using HTTP Fallback...")
                        self._execute_batch_http(stmts)
                except Exception as batch_err:
                    # ถ้าเจอ 505 หรือ Error อื่นๆ ให้ใช้ HTTP Fallback
                    print(f"⚠️ [Turso] Batch error: {batch_err}. Switching to HTTP Fallback...")
                    self._execute_batch_http(stmts)
                return len(stmts)
            else:
                print("⚠️ [Turso] No valid records to insert (missing trade_in_id?)")
                return 0
                
        except Exception as e:
            print(f"❌ [Turso] Insert batch error: {e}")
            if trades_data:
                print(f"   Sample data keys: {list(trades_data[0].keys())}")
            return 0

    def _execute_batch_http(self, stmts):
        """ส่งข้อมูลแบบ Batch ผ่าน HTTP API (v2 pipeline)"""
        url = self.url
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://")
            
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # แปลง Statements เป็นรูปแบบที่ v2 pipeline รองรับ
        requests_list = []
        for stmt in stmts:
            requests_list.append({
                "type": "execute",
                "stmt": {
                    "sql": stmt.sql,
                    "args": self._format_args(stmt.args)
                }
            })
            
        try:
            response = requests.post(f"{url}/v2/pipeline", headers=headers, json={"requests": requests_list}, timeout=30)
            if response.status_code == 200:
                print(f"✅ [Turso Fallback] Successfully inserted {len(stmts)} records via HTTP")
                return True
            else:
                print(f"❌ [Turso Fallback] HTTP Error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ [Turso Fallback] Error: {e}")
            return False

    def get_trades(self, date_start, date_end, branch_id=None):
        """ดึงข้อมูลรายการเทรดจาก Turso ตามช่วงวันที่และสาขา"""
        try:
            # แปลงวันที่จาก DD/MM/YYYY เป็น YYYY-MM-DD สำหรับ SQL
            def to_sql_date(d_str):
                try:
                    d, m, y = d_str.split('/')
                    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except:
                    return d_str

            s_date = to_sql_date(date_start)
            e_date = to_sql_date(date_end)
            
            query = "SELECT * FROM trades WHERE document_date BETWEEN ? AND ?"
            params = [s_date, e_date]
            
            if branch_id and str(branch_id) != '0':
                query += " AND branch_id = ?"
                params.append(str(branch_id))
            
            query += " ORDER BY document_date DESC, trade_in_id DESC"
            
            result = self._execute_sql(query, params)
            if not result:
                return []
            
            # ดึงรายชื่อคอลัมน์เพื่อให้แมพเป็น Dict ได้อัตโนมัติ
            columns = result.columns
            trades = []
            for row in result.rows:
                # สร้าง Dict จาก row และชื่อคอลัมน์
                trade = dict(zip(columns, row))
                
                # 💡 ปรับปรุงคีย์บางตัวให้ตรงกับที่ Frontend/Line Bot คาดหวัง (Compatibility Layer)
                # เพื่อให้ไม่ต้องแก้โค้ดที่เรียกใช้เยอะ
                trade['TRADE_ID'] = trade.get('trade_in_id')
                trade['TRADE_DATE'] = trade.get('document_date')
                trade['BRANCH_ID'] = trade.get('branch_id')
                trade['BRANCH_NAME'] = trade.get('branch_name')
                trade['PRODUCT_NAME'] = trade.get('series')
                
                trades.append(trade)
                
            return trades
        except Exception as e:
            print(f"❌ Turso query error: {e}")
            return []

    def close(self):
        if self.client:
            self.client.close()
