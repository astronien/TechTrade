"""ทดสอบคำสั่งรายงาน pre trade ทาง LINE — mock ข้อมูล Eve ทั้งหมด"""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import line_bot_handler as L
from constants import is_pretrade, pick_campaign_name

ok = lambda m: print(f"  ✅ {m}")

PRE = "4.Pre Trade iPhone Lock Price"

def rec(sale, amount, pretrade, status='ยืนยันราคาแล้ว'):
    return {
        'trade_in_id': f'{sale}-{amount}',
        'campaign_name': '-',
        'CAMPAIGN_ON_TOP_NAME': PRE if pretrade else None,
        'amount': amount, 'SALE_NAME': sale,
        'BIDDING_STATUS_NAME': status,
    }

ITEMS = {
    '231': [rec('สมชาย', 28000, True), rec('สมชาย', 15000, True),
            rec('สมหญิง', 9000, True, 'ยกเลิกรายการ')] + [rec('สมชาย', 5000, False)] * 7,
    '232': [rec('มานี', 12000, True)] + [rec('มานะ', 3000, False)] * 4,
    '233': [rec('ปิติ', 1000, False)] * 3,
}

def fake_fetch(start=0, length=50, **f):
    items = ITEMS.get(str(f.get('branch_id')), [])
    return {'data': items, 'recordsFiltered': len(items), 'source': 'eve_api'}

ZONE = {'zone_id': 'Z1', 'zone_name': 'Studio7', 'branch_ids': ['231', '232', '233']}
find_zone = lambda n: ZONE if n.strip().lower() in ('studio7', 'studio 7') else None
BRANCHES = {'645': {'branch_id': '231', 'branch_name': '00645 : ID645 : Studio 7-Central-Westgate'}}
find_branch = lambda b: BRANCHES.get(str(b))
THAI = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
        'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
parse_month = lambda t: (THAI.index(t.strip()) + 1) if t.strip() in THAI else None
def date_range(m):
    import calendar
    y = 2026
    return f"01/{m:02d}/{y}", f"{calendar.monthrange(y, m)[1]}/{m:02d}/{y}"

L.load_branches_map = lambda: {
    '231': '00645 : ID645 : Studio 7-Central-Westgate',
    '232': '00646 : ID646 : BN-Central-Westgate 2.1',
    '233': '00647 : ID647 : Studio 7-Central-East Vile'}

def run(msg):
    return L.handle_line_message(msg, fake_fetch, lambda: [ZONE], find_zone,
                                 find_branch, parse_month, date_range)

print("\n[1] แยก pre trade ออกจากเทรดปกติได้")
assert is_pretrade(ITEMS['231'][0]) and not is_pretrade(ITEMS['231'][3])
assert pick_campaign_name(ITEMS['231'][0]) == PRE
assert pick_campaign_name(ITEMS['231'][3]) == ''
ok('campaign_name="-" ไม่บังชื่อแคมเปญจริงแล้ว')

print("\n[2] รายงาน pretrade zone Studio7 (เดือนปัจจุบัน)")
r = run('รายงาน pretrade zone Studio7')
assert '🎯 รายงาน Pre Trade' in r and 'Studio7' in r, r
assert 'Pre Trade: 4 รายการ' in r, r
assert '64,000 บาท' in r, r
assert 'ลูกค้าตกลง: 3' in r, r
assert 'สาขาที่มี Pre Trade: 2/3' in r, r
ok('รวม 4 รายการ 64,000 บาท ตกลง 3 จาก 2 สาขา')

print("\n[3] เรียงสาขาตามจำนวน pre trade")
i231 = r.index('Central-Westgate')
i232 = r.index('Central-Westgate 2.1')
assert i231 < i232, 'สาขาที่มากกว่าต้องอยู่บน'
assert 'Central-East Vile' not in r, 'สาขาที่ไม่มี pre trade ไม่ควรโผล่'
ok('เรียงมาก->น้อย และซ่อนสาขาที่ไม่มี pre trade')

print("\n[4] ระบุเดือน")
r2 = run('รายงาน pretrade zone Studio7 กันยายน')
assert 'กันยายน 2569' in r2, r2
ok('รายงาน pretrade zone Studio7 กันยายน -> ระบุเดือนถูก')

print("\n[5] รายวัน")
r3 = run('รายงาน pretrade zone Studio7 วันนี้')
assert 'วันนี้ (' in r3, r3
r3b = run('รายงาน pretrade zone Studio7 เมื่อวาน')
assert 'เมื่อวาน (' in r3b, r3b
ok('รองรับ วันนี้ / เมื่อวาน')

print("\n[6] รายสาขา แยกตามพนักงาน")
r4 = run('รายงาน pretrade 645')
assert 'Studio 7-Central-Westgate' in r4, r4
assert '👤 สมชาย' in r4 and '2 รายการ · 43,000 บาท' in r4, r4
assert '👤 สมหญิง' in r4, r4
assert 'Pre Trade: 3 รายการ (30% ของ 10)' in r4, r4
ok('สมชาย 2 รายการ 43,000 / รวม 3 จาก 10 รายการ = 30%')

print("\n[7] รายสาขา + เดือน / + วัน")
r5 = run('รายงาน pretrade 645 กันยายน')
assert 'กันยายน 2569' in r5
r6 = run('รายงาน pretrade 645 วันนี้')
assert 'วันนี้ (' in r6
ok('รายงาน pretrade 645 กันยายน / วันนี้ ใช้ได้')

print("\n[8] ไม่มี pre trade -> ข้อความชัดเจน")
saved = ITEMS['231']
ITEMS['231'] = [rec('สมชาย', 5000, False)] * 3
r7 = run('รายงาน pretrade 645')
assert 'ไม่มีรายการ Pre Trade' in r7 and 'ตรวจแล้ว 3 รายการ' in r7, r7
ITEMS['231'] = saved
ok('บอกว่าไม่มี พร้อมจำนวนที่ตรวจ')

print("\n[9] คำสั่งผิด / ไม่พบ zone / ไม่พบสาขา")
assert 'รูปแบบคำสั่ง Pre Trade' in run('รายงาน pretrade')
assert 'ไม่พบ Zone' in run('รายงาน pretrade zone ไม่มีจริง')
assert 'ไม่พบสาขา' in run('รายงาน pretrade 99999')
assert 'ไม่รู้จักช่วงเวลา' in run('รายงาน pretrade 645 สัปดาห์นี้')
ok('ข้อความ error ครบทุกกรณี')

print("\n[10] ไม่กระทบคำสั่งเดิม")
r8 = run('รายงาน zone Studio7')
assert '📊 รายงานยอดเทรด' in r8 and 'Pre Trade' not in r8, r8[:200]
ok('รายงาน zone แบบเดิมยังทำงานปกติ ไม่มี pre trade ปน')

print("\n" + "=" * 58)
print("✅ ผ่านทั้งหมด 10 กลุ่มทดสอบ (รายงาน pre trade)")
print("=" * 58)
print("\nตัวอย่างผลลัพธ์จริง — รายงาน pretrade zone Studio7\n")
print(r)
