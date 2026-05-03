import libsql_client
import os
import math
import requests
import re
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
                class MockResult:
                    def __init__(self, res_obj):
                        self.columns = [c['name'] for c in res_obj['cols']]
                        self.rows = [[(val.get('value') if isinstance(val, dict) else val) for val in r] for r in res_obj['rows']]
                return MockResult(result_data['results'][0]['response']['result'])
            return None
        except Exception as e:
            print(f"❌ [Turso Fallback] Error: {e}")
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
            # ป้องกัน Error 'too many values to unpack' กรณีเป็นช่วงวันที่ (เช่น 01/01/2026-02/01/2026)
            if '-' not in sync_date and '/' in sync_date:
                parts = sync_date.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    sync_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            res = self._execute_sql("SELECT branch_id FROM sync_history WHERE branch_id = ? AND sync_date = ?", [str(branch_id), sync_date])
            return res and len(res.rows) > 0
        except: return False

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
                
                # ทำความสะอาดชื่อสาขา (เช่น "ID645 : Studio 7" -> "Studio 7")
                raw_branch_name = self._clean_val(item.get('branch_name') or item.get('BRANCH_NAME'), "")
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
                    (trade_in_id, branch_id, branch_name, document_no, document_date, 
                     IS_SIGNED, SIGN_DATE, series, brand_name, category_name, part_number, 
                     amount, net_price, COUPON_TRADE_IN_CODE, invoice_no, 
                     CAMPAIGN_ON_TOP_NAME, COUPON_ON_TOP_BRAND_CODE, COUPON_ON_TOP_BRAND_PRICE,
                     COUPON_ON_TOP_COMPANY_CODE, COUPON_ON_TOP_COMPANY_PRICE,
                     SALE_NAME, SALE_CODE, employee_name, customer_name, customer_phone_number, customer_email,
                     customer_tax_no, buyer_name, BIDDING_STATUS_NAME, DOCUMENT_REF_1, CHANGE_REQUEST_COUNT,
                     status, grade, cosmetic, ontop_amount, campaign_name, zone_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(trade_in_id), branch_id, branch_name, doc_no, doc_date,
                        is_signed, sign_date, series, brand, cat, part,
                        amount, net_price, coupon_code, inv_no,
                        camp_name, b_cp_code, b_cp_price, c_cp_code, c_cp_price,
                        sale_name, sale_code, emp_name, cust_name, cust_phone, cust_email,
                        cust_tax, buyer, bid_status, ref1, chg_count,
                        status, grade, cosmetic, ot_amount, camp_name, zone_name
                    ]
                ))
            
            if stmts:
                # ลองแบบ Batch ก่อน ถ้าพังหรือ Error 505 ให้สลับไป HTTP ทันที
                try:
                    if self.client: 
                        self.client.batch(stmts)
                        return len(stmts)
                    else:
                        return len(stmts) if self._execute_batch_http(stmts) else 0
                except Exception as e:
                    if "505" in str(e) or "Invalid response status" in str(e):
                        print("🔄 [Turso] Batch 505 Error. Using HTTP Fallback...")
                        return len(stmts) if self._execute_batch_http(stmts) else 0
                    print(f"❌ [Turso] Insert batch error: {e}")
                    return 0
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
                q += " AND branch_id = ?"
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
