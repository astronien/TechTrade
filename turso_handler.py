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
                # Use HTTP-only client to avoid event loop warnings in sync context
                url_http = self.url
                if url_http.startswith("libsql://"):
                    url_http = url_http.replace("libsql://", "https://")

                self.client = libsql_client.create_client(url=url_http, auth_token=self.token)
            except Exception as e:
                # Silence common event loop warnings as we are using HTTP intentionaly
                if "event loop" not in str(e).lower():
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
                    exported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_zone_date ON trades(zone_name, document_date)")
            self._execute_sql("CREATE INDEX IF NOT EXISTS idx_branch ON trades(branch_id)")
            # Backward-compatible migration for databases created before created_at existed.
            try:
                self._execute_sql("ALTER TABLE trades ADD COLUMN created_at DATETIME")
            except Exception:
                pass

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

    def _normalize_date_only(self, date_value):
        """Normalize Eve/SQL date input to YYYY-MM-DD for robust comparisons."""
        if not date_value:
            return ""
        date_str = str(date_value).strip()
        if "/Date(" in date_str:
            return self._parse_eve_date(date_str)
        if " " in date_str:
            date_str = date_str.split(" ")[0]
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        if "/" in date_str:
            try:
                d, m, y = date_str.split("/")[:3]
                return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            except Exception:
                return date_str
        return date_str

    def _extract_trade_id(self, item):
        return str(self._clean_val(
            item.get('trade_in_id') or item.get('TRADE_IN_ID') or item.get('TRADE_ID'),
            ""
        )).strip()

    def _extract_trade_signature(self, item):
        """Create a deterministic lightweight signature for future integrity checks."""
        trade_id = self._extract_trade_id(item)
        amount = self._clean_val(item.get('net_price') or item.get('NET_PRICE') or item.get('amount') or item.get('AMOUNT') or 0, 0, True)
        doc_no = self._clean_val(item.get('document_no') or item.get('DOCUMENT_NO'), "")
        doc_date = self._normalize_date_only(item.get('document_date') or item.get('DOCUMENT_DATE') or item.get('TRADE_DATE'))
        return f"{trade_id}|{doc_date}|{doc_no}|{amount}"

    def reconcile_snapshot(self, trades_data, zone_name, target_date):
        """
        Verify that an Eve snapshot for one zone/date exists in Turso after sync.

        Returns a JSON-serializable dict with exact ID-set comparison plus a checksum
        based on important fields. This is intentionally read-only and safe to call
        after every sync run.
        """
        try:
            date_only = self._normalize_date_only(target_date)
            eve_ids = set()
            eve_signatures = []

            for item in trades_data or []:
                trade_id = self._extract_trade_id(item)
                if trade_id:
                    eve_ids.add(trade_id)
                    eve_signatures.append(self._extract_trade_signature(item))

            res = self._execute_sql(
                """
                SELECT trade_in_id, document_date, document_no, net_price, amount
                FROM trades
                WHERE zone_name = ? AND substr(document_date, 1, 10) = ?
                """,
                [zone_name, date_only]
            )

            turso_ids = set()
            turso_signatures = []
            if res:
                columns = list(res.columns)
                for row in res.rows:
                    data = dict(zip(columns, row))
                    trade_id = str(data.get('trade_in_id') or '').strip()
                    if trade_id:
                        turso_ids.add(trade_id)
                        turso_signatures.append(
                            f"{trade_id}|{self._normalize_date_only(data.get('document_date'))}|{data.get('document_no') or ''}|{data.get('net_price') or data.get('amount') or 0}"
                        )

            missing_ids = sorted(eve_ids - turso_ids)
            extra_ids = sorted(turso_ids - eve_ids)
            eve_checksum = self._hash_strings(eve_signatures)
            turso_checksum = self._hash_strings(turso_signatures)

            return {
                'success': len(missing_ids) == 0 and len(extra_ids) == 0 and len(eve_ids) == len(turso_ids),
                'zone_name': zone_name,
                'date': date_only,
                'eve_count': len(eve_ids),
                'turso_count': len(turso_ids),
                'missing_count': len(missing_ids),
                'extra_count': len(extra_ids),
                'missing_ids_sample': missing_ids[:20],
                'extra_ids_sample': extra_ids[:20],
                'eve_checksum': eve_checksum,
                'turso_checksum': turso_checksum,
                'checksum_match': eve_checksum == turso_checksum,
            }
        except Exception as e:
            print(f"⚠️ [reconcile_snapshot Error] {e}")
            return {
                'success': False,
                'zone_name': zone_name,
                'date': self._normalize_date_only(target_date),
                'error': str(e),
            }

    def _hash_strings(self, values):
        import hashlib
        payload = "\n".join(sorted(str(v) for v in values if v is not None))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def get_sync_health(self, start_date=None, end_date=None, zone_name=None):
        """Read-only summary for admins/API consumers to know current Turso coverage."""
        try:
            conditions = []
            params = []
            if start_date:
                conditions.append("substr(document_date, 1, 10) >= ?")
                params.append(self._normalize_date_only(start_date))
            if end_date:
                conditions.append("substr(document_date, 1, 10) <= ?")
                params.append(self._normalize_date_only(end_date))
            if zone_name:
                conditions.append("zone_name = ?")
                params.append(zone_name)

            where_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            res = self._execute_sql(f"""
                SELECT
                    zone_name,
                    substr(document_date, 1, 10) AS trade_date,
                    COUNT(*) AS turso_count,
                    MIN(exported_at) AS first_exported_at,
                    MAX(exported_at) AS last_exported_at
                FROM trades
                {where_sql}
                GROUP BY zone_name, substr(document_date, 1, 10)
                ORDER BY trade_date DESC, zone_name ASC
            """, params)

            rows = []
            if res:
                columns = list(res.columns)
                for row in res.rows:
                    rows.append(dict(zip(columns, row)))

            return {'success': True, 'count': len(rows), 'data': rows}
        except Exception as e:
            print(f"⚠️ [get_sync_health Error] {e}")
            return {'success': False, 'error': str(e), 'data': []}

    def check_sync_status_batch(self, branch_ids, date_start, date_end):
        """ตรวจสอบสถานะการ Sync ของหลายสาขาพร้อมกัน"""
        if not branch_ids: return {}
        try:
            # 1. เตรียม sync_key สำหรับ sync_history
            sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
            search_date = sync_key
            if '-' not in sync_key and '/' in sync_key:
                parts = sync_key.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    search_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

            # 2. เช็คจาก sync_history ก่อน
            placeholders = ', '.join(['?'] * len(branch_ids))
            sql = f"SELECT branch_id FROM sync_history WHERE sync_date = ? AND branch_id IN ({placeholders})"
            params = [search_date] + [str(bid) for bid in branch_ids]
            res = self._execute_sql(sql, params)

            sync_map = {str(bid): False for bid in branch_ids}
            if res:
                for r in res.rows:
                    sync_map[str(r[0])] = True

            # 3. Fallback: สำหรับตัวที่ยัง False ลองเช็คจากตาราง trades โดยตรง
            remaining_ids = [bid for bid, synced in sync_map.items() if not synced]
            if remaining_ids:
                def to_iso(d):
                    try:
                        p = d.split('/')
                        return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                    except: return d

                iso_start = to_iso(date_start)
                iso_end = to_iso(date_end)

                placeholders_rem = ', '.join(['?'] * len(remaining_ids))
                # กรองเฉพาะตัวเลข
                valid_rem_ids = []
                for rid in remaining_ids:
                    try: valid_rem_ids.append(str(int(rid)))
                    except: pass

                if valid_rem_ids:
                    sql_rem = f"""
                        SELECT real_branch_id, COUNT(*)
                        FROM trades
                        WHERE real_branch_id IN ({', '.join(['?']*len(valid_rem_ids))})
                        AND substr(document_date, 1, 10) BETWEEN ? AND ?
                        GROUP BY real_branch_id
                    """
                    params_rem = valid_rem_ids + [iso_start, iso_end]
                    res_rem = self._execute_sql(sql_rem, params_rem)

                    if res_rem:
                        for r in res_rem.rows:
                            rb_id = str(r[0])
                            actual_count = int(r[1])
                            sync_map[rb_id] = True
                            # 🛠️ Auto-Repair: บันทึกลง sync_history ทันทีพร้อมจำนวนจริง
                            try:
                                self.mark_synced(rb_id, search_date, actual_count)
                                print(f"🔧 [Auto-Repair] Marked Branch {rb_id} as synced with {actual_count} records for {search_date}")
                            except: pass

            return sync_map
        except Exception as e:
            print(f"⚠️ [check_sync_status_batch Error] {e}")
            return {}

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
                    iso_start = f"{y1}-{m1.zfill(2)}-{d1.zfill(2)}"
                    iso_end = f"{y2}-{m2.zfill(2)}-{d2.zfill(2)}"
                except: pass
            else:
                try:
                    parts = sync_date.split('/')
                    if len(parts) == 3:
                        d, m, y = parts
                        iso_start = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                        iso_end = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except: pass

            if iso_start and iso_end:
                try:
                    # ตรวจสอบว่า branch_id เป็นตัวเลขหรือไม่
                    try:
                        b_id_val = int(branch_id)
                    except:
                        b_id_val = str(branch_id)

                    check_sql = "SELECT COUNT(*) FROM trades WHERE real_branch_id = ? AND substr(document_date, 1, 10) BETWEEN ? AND ?"
                    count_res = self._execute_sql(check_sql, [b_id_val, iso_start, iso_end])
                    if count_res:
                        try:
                            count = int(count_res.rows[0][0])
                            # ถ้าเป็นวันเดียว ข้อมูลอาจจะน้อยกว่า 10 ก็ได้ แต่ถ้ามีข้อมูลก็ถือว่า Sync แล้ว
                            threshold = 10 if '-' in sync_date else 0
                            if count > threshold:
                                # 🛠️ Auto-Repair: บันทึกลง sync_history ทันที
                                try:
                                    self.mark_synced(branch_id, sync_date, count)
                                    print(f"🔧 [Auto-Repair] Marked Branch {branch_id} as synced for {sync_date}")
                                except: pass
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

    def invalidate_sync(self, branch_id, sync_date):
        """ลบประวัติ sync เพื่อบังคับให้ดึงข้อมูลใหม่จาก Eve API"""
        try:
            search_date = sync_date
            if '-' not in sync_date and '/' in sync_date:
                parts = sync_date.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    search_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            self._execute_sql(
                "DELETE FROM sync_history WHERE branch_id = ? AND sync_date = ?",
                [str(branch_id), search_date]
            )
            print(f"🗑️ [Invalidate] Cleared sync record for Branch {branch_id} on {search_date}")
            return True
        except Exception as e:
            print(f"⚠️ invalidate_sync error: {e}")
            return False

    def verify_sync_count(self, branch_id, date_start, date_end):
        """
        เปรียบ record_count ที่บันทึกไว้ตอน sync กับ count จริงในตาราง trades
        คืนค่า (is_valid, stored_count, actual_count)
          - is_valid=True  → ข้อมูลน่าจะครบ (หรือตรวจสอบไม่ได้)
          - is_valid=False → จำนวนไม่ตรง ควร re-sync
        """
        try:
            def to_iso(d):
                try:
                    p = d.split('/')
                    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                except: return d

            sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
            search_date = sync_key
            if '-' not in sync_key and '/' in sync_key:
                parts = sync_key.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    search_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

            # 1. ดึง stored count จาก sync_history
            res = self._execute_sql(
                "SELECT record_count FROM sync_history WHERE branch_id = ? AND sync_date = ?",
                [str(branch_id), search_date]
            )
            if not res or not res.rows:
                # ไม่มีใน sync_history เลย → ไม่สามารถตรวจสอบได้ (ถือว่า pass)
                return True, None, None

            stored_count = int(res.rows[0][0]) if res.rows[0][0] is not None else None
            if stored_count is None:
                return True, None, None

            # 2. นับ count จริงใน trades table
            iso_start = to_iso(date_start)
            iso_end   = to_iso(date_end)
            count_res = self._execute_sql(
                "SELECT COUNT(*) FROM trades WHERE real_branch_id = ? AND substr(document_date, 1, 10) BETWEEN ? AND ?",
                [str(branch_id), iso_start, iso_end]
            )
            if not count_res or not count_res.rows:
                return True, stored_count, None

            actual_count = int(count_res.rows[0][0])

            # 3. เปรียบเทียบ — ยอมรับความต่างได้ไม่เกิน 5% หรือ 3 records (เผื่อ Eve มี record เพิ่มทีหลัง)
            if stored_count == 0:
                is_valid = actual_count == 0
            else:
                diff = abs(actual_count - stored_count)
                diff_pct = diff / stored_count
                is_valid = diff <= 3 or diff_pct <= 0.05  # ต่างไม่เกิน 3 records หรือ 5%

            if not is_valid:
                print(f"⚠️ [Count Mismatch] Branch {branch_id} | stored={stored_count} actual={actual_count} | diff={actual_count - stored_count:+d}")

            return is_valid, stored_count, actual_count

        except Exception as e:
            print(f"⚠️ [verify_sync_count Error] {e}")
            return True, None, None  # ถ้า error ให้ผ่านไปก่อน (fail-safe)

    def verify_sync_count_batch(self, branch_ids, date_start, date_end):
        """
        Batch version of verify_sync_count to check multiple branches at once.
        Returns a dict: {branch_id: (is_valid, stored, actual)}
        """
        if not branch_ids: return {}
        try:
            def to_iso(d):
                try:
                    p = d.split('/')
                    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                except: return d

            sync_key = date_end if date_start == date_end else f"{date_start}-{date_end}"
            search_date = sync_key
            if '-' not in sync_key and '/' in sync_key:
                parts = sync_key.split('/')
                if len(parts) == 3:
                    d, m, y = parts
                    search_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

            # 1. ดึง stored counts ทั้งหมดจาก sync_history
            placeholders = ', '.join(['?'] * len(branch_ids))
            sql_stored = f"SELECT branch_id, record_count FROM sync_history WHERE sync_date = ? AND branch_id IN ({placeholders})"
            params_stored = [search_date] + [str(bid) for bid in branch_ids]
            res_stored = self._execute_sql(sql_stored, params_stored)

            stored_map = {}
            if res_stored:
                for r in res_stored.rows:
                    stored_map[str(r[0])] = int(r[1]) if r[1] is not None else None

            # 2. นับ counts จริงทั้งหมดจาก trades table
            iso_start = to_iso(date_start)
            iso_end   = to_iso(date_end)

            # กรองเฉพาะตัวเลขเพื่อความเร็ว
            valid_ids = []
            for rid in branch_ids:
                try: valid_ids.append(str(int(rid)))
                except: pass

            actual_map = {}
            if valid_ids:
                placeholders_act = ', '.join(['?'] * len(valid_ids))
                sql_act = f"""
                    SELECT real_branch_id, COUNT(*)
                    FROM trades
                    WHERE real_branch_id IN ({placeholders_act})
                    AND substr(document_date, 1, 10) BETWEEN ? AND ?
                    GROUP BY real_branch_id
                """
                params_act = valid_ids + [iso_start, iso_end]
                res_act = self._execute_sql(sql_act, params_act)
                if res_act:
                    for r in res_act.rows:
                        actual_map[str(r[0])] = int(r[1])

            # 3. ประมวลผลเปรียบเทียบ
            results = {}
            for bid in branch_ids:
                bid_str = str(bid)
                stored = stored_map.get(bid_str)
                actual = actual_map.get(bid_str, 0)

                if stored is None:
                    results[bid_str] = (True, None, actual)
                    continue

                if stored == 0:
                    is_valid = actual == 0
                else:
                    diff = abs(actual - stored)
                    diff_pct = diff / stored
                    is_valid = diff <= 3 or diff_pct <= 0.05

                results[bid_str] = (is_valid, stored, actual)

            return results
        except Exception as e:
            print(f"⚠️ [verify_sync_count_batch Error] {e}")
            return {str(bid): (True, None, None) for bid in branch_ids}

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
        """ดึงข้อมูลรายการเทรดสาขาเดียว"""
        return self.get_trades_batch(date_start, date_end, branch_ids=[branch_id] if branch_id else None)

    def get_trades_batch(self, date_start, date_end, branch_ids=None):
        """ดึงข้อมูลรายการเทรดหลายสาขาพร้อมกัน (Batch Query)"""
        try:
            def to_sql(d):
                try:
                    p = d.split('/')
                    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                except: return d

            s, e = to_sql(date_start), to_sql(date_end)
            q = "SELECT * FROM trades WHERE substr(document_date, 1, 10) BETWEEN ? AND ?"
            p = [s, e]

            if branch_ids:
                # กรองค่า None หรือ '0' ออก
                valid_ids = [str(bid) for bid in branch_ids if bid and str(bid) != '0']
                if valid_ids:
                    placeholders = ', '.join(['?'] * len(valid_ids))
                    q += f" AND real_branch_id IN ({placeholders})"
                    p.extend(valid_ids)

            q += " ORDER BY document_date DESC, trade_in_id DESC"
            res = self._execute_sql(q, p)
            if not res: return []

            trades = []
            for r in res.rows:
                t = dict(zip(res.columns, r))
                # เพิ่มฟิลด์เดิมที่ API คาดหวัง
                t.update({
                    'TRADE_ID': t.get('trade_in_id'),
                    'TRADE_DATE': t.get('document_date'),
                    'BRANCH_ID': t.get('branch_id'),
                    'BRANCH_NAME': t.get('branch_name'),
                    'PRODUCT_NAME': t.get('series')
                })
                trades.append(t)
            return trades
        except Exception as err:
            print(f"❌ [Turso] get_trades_batch error: {err}")
            return []

    def close(self):
        if self.client: self.client.close()
