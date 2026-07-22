# Shared constants used across app.py, line_bot_handler.py,
# excel_report_generator.py, and turso_handler.py.
# Single source of truth so all reports agree on what "ตกลงราคา" means.

CONFIRMED_STATUSES = ['ยืนยันราคาแล้ว', 'สิ้นสุดการประเมินราคา']
