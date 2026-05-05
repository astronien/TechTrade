"""
verify_sync.py
==============
ตรวจสอบว่าข้อมูลใน Turso ตรงกับ Eve API หรือไม่
โดยเปรียบเทียบ:
  1. จำนวน records (count comparison)
  2. trade_in_id ที่หายไป (missing records)
  3. ค่าที่อาจ stale (BIDDING_STATUS_NAME, amount)

วิธีใช้:
  python verify_sync.py --branch 645 --month 5 --year 2025
  python verify_sync.py --branch 645 --date-start 01/05/2025 --date-end 31/05/2025
"""

import os
import sys
import argparse
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
EVE_API_URL  = "https://eve.techswop.com/ti/index.aspx/Getdata"
TURSO_URL    = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN  = os.getenv("TURSO_AUTH_TOKEN", "")

# ── Turso HTTP helper ────────────────────────────────────────────────
def turso_query(sql, params=None):
    url = TURSO_URL.replace("libsql://", "https://")
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

    def fmt(p):
        if p is None:             return {"type": "null"}
        if isinstance(p, bool):   return {"type": "integer", "value": "1" if p else "0"}
        if isinstance(p, int):    return {"type": "integer", "value": str(p)}
        if isinstance(p, float):  return {"type": "float",   "value": p}
        return {"type": "text", "value": str(p)}

    body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [fmt(p) for p in (params or [])]}}]}
    r = requests.post(f"{url}/v2/pipeline", headers=headers, json=body, timeout=20)
    r.raise_for_status()
    res = r.json().get("results", [{}])[0]
    if res.get("type") == "error":
        raise RuntimeError(res.get("error", {}).get("message", "Turso Error"))
    result = res.get("response", {}).get("result", {})
    cols = [c["name"] for c in result.get("cols", [])]
    rows = [[v.get("value") if isinstance(v, dict) else v for v in row] for row in result.get("rows", [])]
    return cols, rows


# ── Eve API helper ───────────────────────────────────────────────────
def eve_fetch_all(branch_id, date_start, date_end, session_id=None):
    """ดึงข้อมูลทั้งหมดจาก Eve API สำหรับสาขา+ช่วงวันที่"""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://eve.techswop.com",
        "Referer": "https://eve.techswop.com/ti/index.aspx",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    cookies = {}
    if session_id:
        cookies["ASP.NET_SessionId"] = session_id

    all_items = []
    start = 0
    length = 500

    while True:
        payload = {
            "draw": 1, "columns": [], "order": [],
            "start": start, "length": length,
            "search": {"value": "", "regex": False, "fixed": []},
            "textfield": "", "textSearch": "",
            "textdateStart": date_start,
            "textdateEnd": date_end,
            "status": "", "series": [], "brands": [],
            "saleCode": "", "branchID": str(branch_id),
            "txtSearchRef1": "", "txtSearchCOTN": "",
            "DocumentRef1": "", "customerSign": "0",
            "ufund": "",
        }
        try:
            r = requests.post(EVE_API_URL, headers=headers, json=payload, cookies=cookies, timeout=30)
            r.raise_for_status()
            data = r.json().get("d", {})
            items = data.get("data", [])
            total = data.get("recordsFiltered", 0)
            all_items.extend(items)
            print(f"   📥 Eve page start={start}: got {len(items)} | total={total}")
            if len(all_items) >= total or len(items) < length:
                break
            start += length
        except Exception as e:
            print(f"   ❌ Eve API Error: {e}")
            break

    return all_items


# ── Date helpers ─────────────────────────────────────────────────────
def month_range(year, month):
    """คืนค่า (date_start, date_end) ในรูปแบบ DD/MM/YYYY"""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return f"01/{month:02d}/{year}", f"{last_day}/{month:02d}/{year}"

def to_iso(d):
    """DD/MM/YYYY → YYYY-MM-DD"""
    p = d.split("/")
    return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"


# ── Main comparison ──────────────────────────────────────────────────
def compare(branch_id, date_start, date_end, session_id=None, show_missing=False, show_stale=False):
    iso_start = to_iso(date_start) + " 00:00:00"
    iso_end   = to_iso(date_end)   + " 23:59:59"

    print(f"\n{'='*60}")
    print(f"🔍 Verifying Branch {branch_id} | {date_start} → {date_end}")
    print(f"{'='*60}")

    # ── Turso ────────────────────────────────────────────────────────
    print("\n📦 Querying Turso...")
    cols, rows = turso_query(
        "SELECT trade_in_id, BIDDING_STATUS_NAME, amount FROM trades "
        "WHERE real_branch_id = ? AND document_date BETWEEN ? AND ?",
        [str(branch_id), iso_start, iso_end]
    )
    turso_records = {row[0]: {"status": row[1], "amount": row[2]} for row in rows}
    print(f"   Turso count : {len(turso_records)}")

    # ── Eve API ──────────────────────────────────────────────────────
    print("\n🌐 Querying Eve API...")
    eve_items = eve_fetch_all(branch_id, date_start, date_end, session_id)
    eve_records = {
        str(item.get("trade_in_id") or item.get("TRADE_IN_ID", "")): {
            "status": item.get("BIDDING_STATUS_NAME", ""),
            "amount": item.get("amount", 0),
        }
        for item in eve_items
        if item.get("trade_in_id") or item.get("TRADE_IN_ID")
    }
    print(f"   Eve count   : {len(eve_records)}")

    # ── Compare ──────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    turso_ids = set(turso_records.keys())
    eve_ids   = set(eve_records.keys())

    missing_in_turso = eve_ids - turso_ids      # มีใน Eve แต่ไม่มีใน Turso
    extra_in_turso   = turso_ids - eve_ids      # มีใน Turso แต่ไม่มีใน Eve (ถูกลบออก?)
    common_ids       = turso_ids & eve_ids

    # เช็ค stale (ค่าต่างกันแม้ trade_in_id เหมือนกัน)
    stale = []
    for tid in common_ids:
        t = turso_records[tid]
        e = eve_records[tid]
        if t["status"] != e["status"] or str(t["amount"]) != str(e["amount"]):
            stale.append({
                "trade_in_id": tid,
                "turso_status": t["status"], "eve_status": e["status"],
                "turso_amount": t["amount"], "eve_amount": e["amount"],
            })

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n📊 RESULT SUMMARY")
    count_match = len(turso_records) == len(eve_records)
    print(f"  Count match      : {'✅' if count_match else '❌'}  Turso={len(turso_records)} | Eve={len(eve_records)}")
    print(f"  Missing in Turso : {'✅ 0' if not missing_in_turso else f'❌ {len(missing_in_turso)}'}")
    print(f"  Extra in Turso   : {'✅ 0' if not extra_in_turso   else f'⚠️  {len(extra_in_turso)}'}")
    print(f"  Stale records    : {'✅ 0' if not stale             else f'⚠️  {len(stale)}'}")

    if missing_in_turso and show_missing:
        print(f"\n🔴 Missing trade_in_ids in Turso ({len(missing_in_turso)}):")
        for tid in sorted(missing_in_turso)[:30]:
            e = eve_records[tid]
            print(f"   - {tid} | status={e['status']} | amount={e['amount']}")

    if stale and show_stale:
        print(f"\n🟡 Stale records (value mismatch) ({len(stale)}):")
        for s in stale[:20]:
            print(f"   - {s['trade_in_id']}")
            if s["turso_status"] != s["eve_status"]:
                print(f"     status: Turso='{s['turso_status']}' | Eve='{s['eve_status']}'")
            if str(s["turso_amount"]) != str(s["eve_amount"]):
                print(f"     amount: Turso={s['turso_amount']} | Eve={s['eve_amount']}")

    # overall verdict
    ok = count_match and not missing_in_turso and not stale
    print(f"\n{'✅ DATA IS IN SYNC' if ok else '❌ DATA IS OUT OF SYNC'}")
    print(f"{'='*60}\n")

    return {
        "turso_count": len(turso_records),
        "eve_count": len(eve_records),
        "missing": list(missing_in_turso),
        "extra": list(extra_in_turso),
        "stale": stale,
        "in_sync": ok,
    }


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Turso vs Eve data integrity")
    parser.add_argument("--branch",     required=True,  help="Real branch ID (เช่น 645)")
    parser.add_argument("--month",      type=int,       help="Month number (1-12)")
    parser.add_argument("--year",       type=int,       default=datetime.now().year, help="Year (CE)")
    parser.add_argument("--date-start", dest="date_start", help="DD/MM/YYYY")
    parser.add_argument("--date-end",   dest="date_end",   help="DD/MM/YYYY")
    parser.add_argument("--session",    help="Eve ASP.NET_SessionId cookie (optional)")
    parser.add_argument("--show-missing", action="store_true", help="แสดง trade_in_id ที่หายจาก Turso")
    parser.add_argument("--show-stale",   action="store_true", help="แสดง records ที่ค่าต่างกัน")
    args = parser.parse_args()

    if not TURSO_URL or not TURSO_TOKEN:
        print("❌ กรุณากำหนด TURSO_DATABASE_URL และ TURSO_AUTH_TOKEN ใน .env")
        sys.exit(1)

    if args.month:
        d_start, d_end = month_range(args.year, args.month)
    elif args.date_start and args.date_end:
        d_start, d_end = args.date_start, args.date_end
    else:
        print("❌ กรุณาระบุ --month หรือ --date-start และ --date-end")
        sys.exit(1)

    compare(
        branch_id  = args.branch,
        date_start = d_start,
        date_end   = d_end,
        session_id = args.session,
        show_missing = args.show_missing,
        show_stale   = args.show_stale,
    )
