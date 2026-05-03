import os
import math
import requests
import re
from datetime import datetime

# Safe import for libsql_client to prevent crashes on incompatible environments (like Vercel)
try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False
    print("⚠️ [Turso] libsql_client not found or failed to load. Using HTTP fallback.")
except Exception as e:
    HAS_LIBSQL = False
    print(f"⚠️ [Turso] libsql_client error: {e}. Using HTTP fallback.")

# Mock Statement class if libsql_client is missing
if not HAS_LIBSQL:
    class MockStatement:
        def __init__(self, sql, args=None):
            self.sql = sql
            self.args = args or []
    
    # Create a dummy libsql_client namespace
    class DummyLibsql:
        Statement = MockStatement
    
    libsql_client = DummyLibsql()

class TursoHandler:
    def __init__(self, url=None, token=None):
        self.url = url or os.getenv('TURSO_DATABASE_URL')
        self.token = token or os.getenv('TURSO_AUTH_TOKEN')
        self.client = None
        
        if HAS_LIBSQL and self.url and self.token:
            try:
                # Use the standard create_client which handles sync/async context
                self.client = libsql_client.create_client(url=self.url, auth_token=self.token)
            except Exception as e:
                print(f"⚠️ [Turso] Client init warning: {e}")
                self.client = None

    def init_db(self, reset=False):
        """สร้างตาราง trades พร้อมคอลัมน์ที่ครบถ้วน"""
        # อนุญาตให้รันผ่าน HTTP Fallback ได้ถ้าไม่มี client
            
        try:
            if reset:
                print("🗑️ [Turso] Dropping old tables as requested...")
                self._execute_sql("DROP TABLE IF EXISTS trades")
                self._execute_sql("DROP TABLE IF EXISTS sync_history")

            self._execute_sql("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_in_id TEXT PRIMARY KEY,
                    branch_id TEXT,
                    real_branch_id TEXT,
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
                    employee_name TEXT,
                    customer_name TEXT,
                    customer_phone_number TEXT,
                    customer_email TEXT,
                    customer_tax_no TEXT,
                    buyer_name TEXT,
                    BIDDING_STATUS_NAME TEXT,
                    DOCUMENT_REF_1 TEXT,
                    CHANGE_REQUEST_COUNT INTEGER,
                    status INTEGER,
                    grade TEXT,
                    cosmetic TEXT,
                    ontop_amount REAL,
                    campaign_name TEXT,
                    zone_name TEXT,
                    exported_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_zone_date ON trades(zone_name, document_date)")
            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_branch ON trades(branch_id)")
            
            # ตารางประวัติการ Sync
            self._execute_sql("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    branch_id TEXT,
                    sync_date TEXT,
                    record_count INTEGER,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (branch_id, sync_date)
                )
            """)
            
            print("✅ Turso database initialized with full schema")
            return True
        except Exception as e:
            print(f"❌ Database init error: {e}")
            return False

    def _execute_sql(self, sql, params=None):
        if not self.client:
            return self._execute_http(sql, params)
        try:
            return self.client.execute(sql, params)
        except Exception as e:
            if "505" in str(e) or "Invalid response status" in str(e):
                print("🔄 [Turso] 505 Error detected. Using HTTP Fallback...")
                return self._execute_http(sql, params)
            raise e

    def _execute_http(self, sql, params=None):
        url = self.url
        if not url: return None
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://")
            
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        data = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": self._format_args(params)}}]}
        
        try:
            response = requests.post(f"{url}/v2/pipeline", headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                result_data = response.json()
                result_item = result_data.get('results', [{}])[0]
                
                if result_item.get('type') == 'error':
                    error_msg = result_item.get('error', {}).get('message', 'Unknown Turso Error')
                    print(f"❌ [Turso API Error] {error_msg}")
                    return None
                
                if 'response' in result_item and 'result' in result_item['response']:
                    res_obj = result_item['response']['result']
                    class MockResult:
                        def __init__(self, r_obj):
                            self.columns = [c['name'] for c in r_obj.get('cols', [])]
                            self.rows = [[(val.get('value') if isinstance(val, dict) else val) for val in r] for r in r_obj.get('rows', [])]
                    return MockResult(res_obj)
            else:
                print(f"❌ [Turso HTTP Error] Status: {response.status_code}, Body: {response.text}")
            return None
        except Exception as e:
            print(f"❌ [Turso Fallback Exception] Error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _format_args(self, params):
        if not params: return []
        formatted = []
        for p in params:
            if p is None: formatted.append({"type": "null"})
            elif isinstance(p, bool): formatted.append({"type": "integer", "value": "1" if p else "0"})
            elif isinstance(p, int): formatted.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float): formatted.append({"type": "float", "value": p})
            else: formatted.append({"type": "text", "value": str(p)})
        return formatted

    def is_synced(self, branch_id, sync_date):
        try:
            # 1. ตรวจสอบจาก sync_history (วิธีดั้งเดิม)
            search_date = sync_date
            if '-' not in sync_date and '/' in sync_date:
                parts = sync_date.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    search_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            res = self._execute_sql("SELECT branch_id FROM sync_history WHERE branch_id = ? AND sync_date = ?", [str(branch_id), search_date])
            if res and len(res.rows) > 0:
                return True
                
            # 2. Fallback: ตรวจสอบจากตาราง trades โดยตรง (กรณีข้อมูลมีอยู่แล้วแต่ประวัติหาย หรือเป็นช่วงวันที่)
            iso_start = None
            iso_end = None
            
            if '-' in sync_date:
                start_str, end_str = sync_date.split('-')
                try:
                    d1, m1, y1 = start_str.split('/')
                    d2, m2, y2 = end_str.split('/')
                    iso_start = f"{y1}-{m1.zfill(2)}-{d1.zfill(2)} 00:00:00"
                    iso_end = f"{y2}-{m2.zfill(2)}-{d2.zfill(2)} 23:59:59"
                except: pass
            else:
                try:
                    parts = sync_date.split('/')
                    if len(parts) == 3:
                        d, m, y = parts
                        iso_start = f"{y}-{m.zfill(2)}-{d.zfill(2)} 00:00:00"
                        iso_end = f"{y}-{m.zfill(2)}-{d.zfill(2)} 23:59:59"
                except: pass

            if iso_start and iso_end:
                try:
                    # ตรวจสอบว่า branch_id เป็นตัวเลขหรือไม่
                    try:
                        b_id_val = int(branch_id)
                    except:
                        b_id_val = str(branch_id)
                    
                    check_sql = "SELECT COUNT(*) FROM trades WHERE real_branch_id = ? AND document_date BETWEEN ? AND ?"
                    count_res = self._execute_sql(check_sql, [b_id_val, iso_start, iso_end])
                    if count_res:
                        try:
                            count = int(count_res.rows[0][0])
                            # ถ้าเป็นวันเดียว ข้อมูลอาจจะน้อยกว่า 10 ก็ได้ แต่ถ้ามีข้อมูลก็ถือว่า Sync แล้ว
                            threshold = 10 if '-' in sync_date else 0
                            if count > threshold:
                                return True
                        except: pass
                except: pass
            
            return False
        except Exception as e:
            print(f"⚠️ [is_synced Error] {e}")
            return False

    def mark_synced(self, branch_id, sync_date, count):
        try:
            # ป้องกัน Error 'too many values to unpack' กรณีเป็นช่วงวันที่
            if '-' not in sync_date and '/' in sync_date:
                parts = sync_date.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    sync_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            self._execute_sql("INSERT OR REPLACE INTO sync_history (branch_id, sync_date, record_count) VALUES (?, ?, ?)", [str(branch_id), sync_date, count])
            return True
        except Exception as e:
            print(f"⚠️ mark_synced error: {e}")
            return False

    def _clean_val(self, val, default=None, is_num=False):
        if val is None: return 0.0 if is_num else default
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val): return 0.0 if is_num else default
            return val
        if isinstance(val, str):
            if val.lower() in ['nan', 'none', 'null', '']: return 0.0 if is_num else default
            return val
        return val

    def _parse_eve_date(self, date_val):
        if not date_val: return ""
        if isinstance(date_val, str) and "/Date(" in date_val:
            try:
                match = re.search(r"(\d+)", date_val)
                if match:
                    dt = datetime.fromtimestamp(int(match.group(1)) / 1000.0)
                    return dt.strftime("%Y-%m-%d")
            except: pass
        if isinstance(date_val, str) and "/" in date_val:
            try:
                parts = date_val.split('/')
                if len(parts) == 3: return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            except: pass
        return str(date_val)

    def insert_trades_batch(self, trades_data, zone_name):
        if not trades_data: return 0
        try:
            stmts = []
            for item in trades_data:
                trade_in_id = self._clean_val(item.get('trade_in_id') or item.get('TRADE_IN_ID'))
                if not trade_in_id: continue

                # Extraction with Case-insensitive keys
                branch_id = str(self._clean_val(item.get('branch_id') or item.get('BRANCH_ID'), ""))
                
                # ทำความสะอาดชื่อสาขา และสกัด real_branch_id (เช่น "ID645 : Studio 7" -> "645")
                raw_branch_name = self._clean_val(item.get('branch_name') or item.get('BRANCH_NAME'), "")
                real_branch_id = ""
                
                # ลองแกะ ID จากรูปแบบ "ID645"
                import re
                id_match = re.search(r'ID(\d+)', raw_branch_name)
                if id_match:
                    real_branch_id = id_match.group(1)
                else:
                    real_branch_id = branch_id # fallback
                
                if ':' in raw_branch_name:
                    branch_name = raw_branch_name.split(':')[-1].strip()
                else:
                    branch_name = raw_branch_name
                
                doc_no = self._clean_val(item.get('document_no') or item.get('DOCUMENT_NO'), "")
                doc_date = self._parse_eve_date(item.get('document_date') or item.get('DOCUMENT_DATE'))
                
                is_signed = self._clean_val(item.get('IS_SIGNED') or item.get('is_signed'), "")
                sign_date = self._parse_eve_date(item.get('SIGN_DATE') or item.get('sign_date'))
                
                series = self._clean_val(item.get('series') or item.get('SERIES'), "")
                brand = self._clean_val(item.get('brand_name') or item.get('BRAND_NAME') or item.get('brand'), "")
                cat = self._clean_val(item.get('category_name') or item.get('CATEGORY_NAME') or item.get('category'), "")
                part = self._clean_val(item.get('part_number') or item.get('PART_NUMBER'), "")
                
                amount = float(self._clean_val(item.get('amount') or item.get('AMOUNT') or 0, 0, True))
                
                # Campaign & Coupons
                coupon_code = self._clean_val(item.get('COUPON_TRADE_IN_CODE') or item.get('coupon_trade_in_code'), "")
                inv_no = self._clean_val(item.get('invoice_no') or item.get('INVOICE_NO'), "")
                camp_name = self._clean_val(item.get('campaign_name') or item.get('CAMPAIGN_NAME') or item.get('CAMPAIGN_ON_TOP_NAME'), "")
                b_cp_code = self._clean_val(item.get('COUPON_ON_TOP_BRAND_CODE') or item.get('coupon_on_top_brand_code'), "")
                b_cp_price = float(self._clean_val(item.get('COUPON_ON_TOP_BRAND_PRICE') or 0, 0, True))
                c_cp_code = self._clean_val(item.get('COUPON_ON_TOP_COMPANY_CODE') or item.get('coupon_on_top_company_code'), "")
                c_cp_price = float(self._clean_val(item.get('COUPON_ON_TOP_COMPANY_PRICE') or 0, 0, True))
                
                net_price = float(item.get('net_price') or item.get('NET_PRICE') or (amount + b_cp_price + c_cp_price))

                # Extra Info from JSON
                sale_name = self._clean_val(item.get('SALE_NAME') or item.get('sale_name'), "")
                sale_code = self._clean_val(item.get('SALE_CODE') or item.get('sale_code'), "")
                emp_name = self._clean_val(item.get('employee_name') or item.get('EMPLOYEE_NAME'), "")
                cust_name = self._clean_val(item.get('customer_name') or item.get('CUSTOMER_NAME'), "")
                cust_phone = self._clean_val(item.get('customer_phone_number') or item.get('customer_phone'), "")
                cust_email = self._clean_val(item.get('customer_email') or item.get('CUSTOMER_EMAIL'), "")
                cust_tax = self._clean_val(item.get('customer_tax_no') or item.get('CUSTOMER_TAX_NO'), "")
                buyer = self._clean_val(item.get('buyer_name') or item.get('BUYER_NAME'), "")
                bid_status = self._clean_val(item.get('BIDDING_STATUS_NAME') or item.get('bidding_status_name'), "")
                ref1 = self._clean_val(item.get('DOCUMENT_REF_1') or item.get('document_ref_1'), "")
                chg_count = int(self._clean_val(item.get('CHANGE_REQUEST_COUNT') or item.get('change_request_count') or 0, 0, True))
                
                status = self._clean_val(item.get('status') or item.get('STATUS'), 0, True)
                grade = self._clean_val(item.get('grade') or item.get('GRADE'), "")
                cosmetic = self._clean_val(item.get('cosmetic') or item.get('COSMETIC'), "")
                ot_amount = float(self._clean_val(item.get('ontop_amount') or item.get('ONTOP_AMOUNT') or 0, 0, True))

                stmts.append(libsql_client.Statement(
                    """
                    INSERT OR REPLACE INTO trades 
                    (trade_in_id, branch_id, real_branch_id, branch_name, document_no, document_date, 
                     IS_SIGNED, SIGN_DATE, series, brand_name, category_name, part_number, 
                     amount, net_price, COUPON_TRADE_IN_CODE, invoice_no, 
                     CAMPAIGN_ON_TOP_NAME, COUPON_ON_TOP_BRAND_CODE, COUPON_ON_TOP_BRAND_PRICE,
                     COUPON_ON_TOP_COMPANY_CODE, COUPON_ON_TOP_COMPANY_PRICE,
                     SALE_NAME, SALE_CODE, employee_name, customer_name, customer_phone_number, customer_email,
                     customer_tax_no, buyer_name, BIDDING_STATUS_NAME, DOCUMENT_REF_1, CHANGE_REQUEST_COUNT,
                     status, grade, cosmetic, ontop_amount, campaign_name, zone_name, exported_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(trade_in_id), branch_id, real_branch_id, branch_name, doc_no, doc_date,
                        is_signed, sign_date, series, brand, cat, part,
                        amount, net_price, coupon_code, inv_no,
                        camp_name, b_cp_code, b_cp_price, c_cp_code, c_cp_price,
                        sale_name, sale_code, emp_name, cust_name, cust_phone, cust_email,
                        cust_tax, buyer, bid_status, ref1, chg_count,
                        status, grade, cosmetic, ot_amount, camp_name, zone_name,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                ))
            
            if stmts:
                # ลองแบบ Batch ก่อน ถ้ามี client และไม่พัง
                try:
                    if self.client and HAS_LIBSQL: 
                        self.client.batch(stmts)
                        return len(stmts)
                    else:
                        return len(stmts) if self._execute_batch_http(stmts) else 0
                except Exception as e:
                    if "505" in str(e) or "Invalid response status" in str(e) or "not defined" in str(e):
                        print("🔄 [Turso] Batch Error or 505. Using HTTP Fallback...")
                        return len(stmts) if self._execute_batch_http(stmts) else 0
                    print(f"❌ [Turso] Insert batch error: {e}")
                    return 0
            return 0
        except Exception as e:
            print(f"❌ [Turso] insert_trades_batch outer error: {e}")
            return 0

    def _execute_batch_http(self, stmts):
        url = self.url
        if url.startswith("libsql://"): url = url.replace("libsql://", "https://")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        reqs = [{"type": "execute", "stmt": {"sql": s.sql, "args": self._format_args(s.args)}} for s in stmts]
        try:
            requests.post(f"{url}/v2/pipeline", headers=headers, json={"requests": reqs}, timeout=30)
            return True
        except: return False

    def get_trades(self, date_start, date_end, branch_id=None):
        try:
            def to_sql(d):
                try: 
                    p = d.split('/')
                    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                except: return d
            s, e = to_sql(date_start), to_sql(date_end)
            q = "SELECT * FROM trades WHERE document_date BETWEEN ? AND ?"
            p = [s, e]
            if branch_id and str(branch_id) != '0':
                q += " AND real_branch_id = ?"
                p.append(str(branch_id))
            q += " ORDER BY document_date DESC, trade_in_id DESC"
            res = self._execute_sql(q, p)
            if not res: return []
            trades = []
            for r in res.rows:
                t = dict(zip(res.columns, r))
                t.update({'TRADE_ID': t.get('trade_in_id'), 'TRADE_DATE': t.get('document_date'), 
                          'BRANCH_ID': t.get('branch_id'), 'BRANCH_NAME': t.get('branch_name'), 'PRODUCT_NAME': t.get('series')})
                trades.append(t)
            return trades
        except: return []

    def close(self):
        if self.client: self.client.close()
