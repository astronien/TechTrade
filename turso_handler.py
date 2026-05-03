import libsql_client
import os
import math
from datetime import datetime

class TursoHandler:
    def __init__(self, url=None, token=None):
        self.url = url or os.getenv('TURSO_DATABASE_URL')
        self.token = token or os.getenv('TURSO_AUTH_TOKEN')
        self.client = None
        
        if self.url and self.token:
            self.client = libsql_client.create_client_sync(self.url, auth_token=self.token)

    def init_db(self):
        """สร้างตาราง trades หากยังไม่มี"""
        if not self.client:
            print("❌ Turso client not initialized")
            return False
            
        try:
            self.client.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_in_id TEXT PRIMARY KEY,
                    branch_id TEXT,
                    branch_name TEXT,
                    document_no TEXT,
                    document_date TEXT,
                    SIGN_DATE TEXT,
                    series TEXT,
                    brand_name TEXT,
                    category_name TEXT,
                    part_number TEXT,
                    amount REAL,
                    net_price REAL,
                    SALE_NAME TEXT,
                    SALE_CODE TEXT,
                    customer_name TEXT,
                    customer_phone_number TEXT,
                    buyer_name TEXT,
                    BIDDING_STATUS_NAME TEXT,
                    zone_name TEXT,
                    exported_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.client.execute("CREATE INDEX IF NOT EXISTS idx_zone_date ON trades(zone_name, document_date)")
            self.client.execute("CREATE INDEX IF NOT EXISTS idx_branch ON trades(branch_id)")
            
            print("✅ Turso table and indexes initialized")
            return True
        except Exception as e:
            print(f"❌ Turso init error: {e}")
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
        if not self.client or not trades_data:
            return 0
            
        try:
            stmts = []
            for item in trades_data:
                # จัดการ trade_in_id (ต้องมีค่า)
                trade_in_id = self._clean_val(item.get('trade_in_id'))
                if not trade_in_id: continue
                
                # ทำความสะอาดข้อมูลอื่นๆ
                branch_id = str(self._clean_val(item.get('branch_id'), ""))
                branch_name = self._clean_val(item.get('branch_name'), "")
                document_no = self._clean_val(item.get('document_no'), "")
                document_date = self._clean_val(item.get('document_date'), "")
                sign_date = self._clean_val(item.get('SIGN_DATE'), "")
                series = self._clean_val(item.get('series'), "")
                brand_name = self._clean_val(item.get('brand_name'), "")
                category_name = self._clean_val(item.get('category_name'), "")
                part_number = self._clean_val(item.get('part_number'), "")
                
                amount = float(self._clean_val(item.get('amount', 0), 0, True))
                
                # คำนวณ net_price ถ้ามีในข้อมูล หรือใช้ amount แทน
                if 'net_price' in item:
                    net_price = float(self._clean_val(item.get('net_price', 0), 0, True))
                else:
                    try:
                        tub = float(self._clean_val(item.get('COUPON_ON_TOP_BRAND_PRICE', 0), 0, True))
                        tuc = float(self._clean_val(item.get('COUPON_ON_TOP_COMPANY_PRICE', 0), 0, True))
                        net_price = amount + tub + tuc
                    except:
                        net_price = amount

                sale_name = self._clean_val(item.get('SALE_NAME'), "")
                sale_code = self._clean_val(item.get('SALE_CODE'), "")
                customer_name = self._clean_val(item.get('customer_name'), "")
                customer_phone = self._clean_val(item.get('customer_phone_number'), "")
                buyer_name = self._clean_val(item.get('buyer_name'), "")
                bidding_status = self._clean_val(item.get('BIDDING_STATUS_NAME'), "")

                stmts.append(libsql_client.Statement(
                    """
                    INSERT OR REPLACE INTO trades 
                    (trade_in_id, branch_id, branch_name, document_no, document_date, SIGN_DATE,
                     series, brand_name, category_name, part_number, amount, net_price,
                     SALE_NAME, SALE_CODE, customer_name, customer_phone_number, 
                     buyer_name, BIDDING_STATUS_NAME, zone_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(trade_in_id), branch_id, branch_name, document_no, document_date, sign_date,
                        series, brand_name, category_name, part_number, amount, net_price,
                        sale_name, sale_code, customer_name, customer_phone, 
                        buyer_name, bidding_status, zone_name
                    ]
                ))
            
            if stmts:
                self.client.batch(stmts)
                return len(stmts)
            return 0
            
        except Exception as e:
            print(f"❌ Turso batch insert error: {e}")
            return 0

    def get_trades(self, date_start, date_end, branch_id=None):
        """ดึงข้อมูลรายการเทรดจาก Turso ตามช่วงวันที่และสาขา"""
        if not self.client:
            return []
            
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
            
            query = "SELECT * FROM trades WHERE trade_date BETWEEN ? AND ?"
            params = [s_date, e_date]
            
            if branch_id and str(branch_id) != '0':
                query += " AND branch_id = ?"
                params.append(str(branch_id))
            
            query += " ORDER BY trade_date DESC, trade_id DESC"
            
            result = self.client.execute(query, params)
            
            # แปลงกลับเป็น format ที่หน้าเว็บ/Line Bot ต้องการ
            trades = []
            for row in result.rows:
                # แมพชื่อคอลัมน์กลับ (Turso columns -> API fields)
                # หมายเหตุ: ใน app.py ใช้คีย์ตัวพิมพ์ใหญ่ตาม API ของ Eve
                trade = {
                    'TRADE_ID': row[0],
                    'TRADE_DATE': datetime.strptime(row[1], '%Y-%m-%d').strftime('%d/%m/%Y') if row[1] else '',
                    'BRANCH_ID': row[2],
                    'BRANCH_NAME': row[3],
                    'SALE_CODE': row[4],
                    'SALE_NAME': row[5],
                    'CUSTOMER_NAME': row[6],
                    'PRODUCT_NAME': row[7],
                    'IMEI': row[8],
                    'BIDDING_STATUS_NAME': row[9],
                    'amount': row[10], # API ใช้ตัวพิมพ์เล็กสำหรับยอดเงิน
                    'zone_name': row[11]
                }
                trades.append(trade)
                
            return trades
        except Exception as e:
            print(f"❌ Turso query error: {e}")
            return []

    def close(self):
        if self.client:
            self.client.close()
