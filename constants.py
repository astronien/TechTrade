# Shared constants used across app.py, line_bot_handler.py,
# excel_report_generator.py, and turso_handler.py.
# Single source of truth so all reports agree on what "ตกลงราคา" means.

CONFIRMED_STATUSES = ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']

# ==========================================
# Pre Trade
# ------------------------------------------
# techswop ไม่ได้ใช้ฟิลด์ IS_PRE_TRADE (เป็น false เสมอ) แต่บันทึก pre trade
# เป็นแคมเปญ on-top ชื่อเช่น "4.Pre Trade iPhone Lock Price"
# จึงต้องดูจากชื่อแคมเปญเป็นหลัก และเผื่อ IS_PRE_TRADE ไว้ด้วยถ้าเปิดใช้ทีหลัง
# ==========================================

PRETRADE_KEYWORDS = ('pre trade', 'pretrade', 'pre-trade', 'pre_trade')

# ค่าที่ Eve ส่งมาแทน "ไม่มีแคมเปญ"
EMPTY_CAMPAIGN_VALUES = ('', '-', 'none', 'null', 'n/a')


def pick_campaign_name(item):
    """ดึงชื่อแคมเปญจริงจากรายการ

    ระวัง: Eve ส่ง campaign_name = "-" มาเกือบทุกแถว ซึ่งเป็น truthy
    ถ้าใช้ `a or b or c` จะหยุดที่ "-" แล้วไม่ถึง CAMPAIGN_ON_TOP_NAME
    ทำให้ชื่อแคมเปญจริงหายไปทั้งหมด
    """
    if not isinstance(item, dict):
        return ''
    for key in ('CAMPAIGN_ON_TOP_NAME', 'campaign_on_top_name',
                'campaign_name', 'CAMPAIGN_NAME'):
        val = item.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s and s.lower() not in EMPTY_CAMPAIGN_VALUES:
            return s
    return ''


def is_pretrade(item):
    """รายการนี้เป็น pre trade หรือไม่ (รองรับทั้งข้อมูลดิบจาก Eve และแถวจาก Turso)"""
    if not isinstance(item, dict):
        return False

    # 1. คอลัมน์ที่เราคำนวณเก็บไว้แล้วใน Turso
    flag = item.get('is_pre_trade')
    if flag in (1, '1', True, 'true', 'True'):
        return True

    # 2. ฟิลด์ของ Eve เอง (ยังไม่ถูกใช้งานจริง แต่เผื่อไว้)
    if item.get('IS_PRE_TRADE') is True:
        return True

    # 3. ดูจากชื่อแคมเปญ — วิธีที่ใช้ได้จริงตอนนี้
    name = pick_campaign_name(item).lower()
    return any(kw in name for kw in PRETRADE_KEYWORDS)
