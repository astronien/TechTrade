# Excel Report Generator for Annual Trade Reports
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from datetime import datetime
from collections import defaultdict
import os
import tempfile

def generate_monthly_excel_report(trade_data, year, month, branch_id=None, branch_name=None):
    """สร้างรายงานรายเดือน (แยกตามวัน)"""
    import calendar
    
    # ชื่อเดือน
    month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    month_name = month_names[month - 1]
    
    # จำนวนวันในเดือนนั้น
    num_days = calendar.monthrange(year, month)[1]
    
    # 1. เตรียมข้อมูลกราฟ (รายวัน)
    daily_counts = defaultdict(int)
    
    for item in trade_data:
        doc_date = item.get('document_date', '')
        if doc_date:
            # แปลงวันที่จาก format /Date(1704042000000)/ หรือ string
            try:
                dt = parse_date(doc_date)
                if dt.year == year and dt.month == month:
                    daily_counts[dt.day] += 1
            except Exception as e:
                print(f"Warning: Could not parse date {doc_date} in monthly report: {e}")
                pass

    # สร้าง Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = f"รายงานเดือน {month_name}"
    
    # หัวตาราง
    headers = ['วันที่', 'จำนวนรายการ']
    ws.append(headers)
    
    # ข้อมูลตาราง
    days = range(1, num_days + 1)
    categories = [] # สำหรับกราฟ
    values = []     # สำหรับกราฟ
    
    for day in days:
        count = daily_counts[day]
        date_str = f"{day}/{month}/{year}"
        ws.append([date_str, count])
        
        categories.append(str(day))
        values.append(count)
        
    # จัดรูปแบบตาราง
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')
        
    # สร้างกราฟเส้น (Line Chart)
    line_chart = LineChart()
    line_chart.title = f"สถิติการเทรดรายวัน เดือน {month_name} {year} - {branch_name or branch_id or ''}"
    line_chart.style = 12
    line_chart.y_axis.title = 'จำนวนรายการ'
    line_chart.x_axis.title = 'วันที่'
    
    data = Reference(ws, min_col=2, min_row=1, max_row=num_days + 1)
    cats = Reference(ws, min_col=1, min_row=2, max_row=num_days + 1)
    
    line_chart.add_data(data, titles_from_data=True)
    line_chart.set_categories(cats)
    
    ws.add_chart(line_chart, "D2")
    
    # สร้างกราฟแท่ง (Bar Chart)
    bar_chart = BarChart()
    bar_chart.title = "เปรียบเทียบรายวัน"
    bar_chart.style = 10
    bar_chart.add_data(data, titles_from_data=True)
    bar_chart.set_categories(cats)
    
    ws.add_chart(bar_chart, "D20")
    
    # Save file
    filename = f"monthly_report_{year}_{month:02d}_{branch_id or 'all'}.xlsx"
    filepath = os.path.join(tempfile.gettempdir(), filename)
    wb.save(filepath)
    
    return filepath

def generate_annual_excel_report_for_zone(branches_data, year, zone_name, month=None):
    """
    สร้างไฟล์ Excel รายงานรายปี (หรือรายเดือน) สำหรับ Zone
    - branches_data: list ของ dict {branch_id, branch_name, monthly_counts}
      (ถ้าเป็นรายเดือน monthly_counts จะเก็บเป็น daily_counts แทน)
    - year: ปีที่ต้องการ
    - zone_name: ชื่อ Zone
    - month: เดือนที่ต้องการ (optional)
    """
    wb = Workbook()
    ws = wb.active
    
    month_names_th = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    
    if month:
        # รายงานรายเดือน
        import calendar
        month_name = month_names_th[month - 1]
        ws.title = f"Zone {zone_name} - {month_name}"
        
        num_days = calendar.monthrange(year, month)[1]
        headers = ['สาขา'] + [str(d) for d in range(1, num_days + 1)] + ['รวม']
    else:
        # รายงานรายปี
        ws.title = f"Zone {zone_name} - {year}"
        headers = ['สาขา', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 
                   'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.', 'รวม']
                   
    ws.append(headers)
    # หัวตาราง
    ws['A1'].value = 'สาขา' # Set value after append to avoid overwriting
    ws['A1'].font = Font(bold=True, size=12, color="FFFFFF")
    ws['A1'].fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    
    # เขียนชื่อเดือน/วัน
    if month:
        for col_idx, day_num in enumerate(range(1, num_days + 1), start=2):
            cell = ws.cell(row=1, column=col_idx)
            cell.value = str(day_num)
            cell.font = Font(bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                top=Side(style='thin'), bottom=Side(style='thin'))
        # คอลัมน์รวม
        ws.cell(row=1, column=num_days + 2).value = 'รวม'
        ws.cell(row=1, column=num_days + 2).font = Font(bold=True, size=11, color="FFFFFF")
        ws.cell(row=1, column=num_days + 2).fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
        ws.cell(row=1, column=num_days + 2).alignment = Alignment(horizontal='center', vertical='center')
    else:
        month_names_short = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 
                             'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
        for col_idx, month_name_short in enumerate(month_names_short, start=2):
            cell = ws.cell(row=1, column=col_idx)
            cell.value = month_name_short
            cell.font = Font(bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                top=Side(style='thin'), bottom=Side(style='thin'))
        
        # คอลัมน์รวม
        ws.cell(row=1, column=14).value = 'รวม'
        ws.cell(row=1, column=14).font = Font(bold=True, size=11, color="FFFFFF")
        ws.cell(row=1, column=14).fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
        ws.cell(row=1, column=14).alignment = Alignment(horizontal='center', vertical='center')
    
    # เขียนข้อมูลแต่ละสาขา
    row_idx = 2
    
    # ข้อมูล
    rows = []
    
    if month:
        # Loop 1-31
        data_range = range(1, num_days + 1)
        total_by_period = [0] * num_days
        total_col_idx = num_days + 2
    else:
        # Loop 1-12
        data_range = range(1, 13)
        total_by_period = [0] * 12
        total_col_idx = 14

    grand_total = 0

    for branch in branches_data:
        branch_name_display = branch.get('branch_name', f"สาขา {branch.get('branch_id')}")
        if ' : ' in branch_name_display:
            branch_name_display = branch_name_display.split(' : ')[-1]
        
        counts = branch.get('monthly_counts', {}) # This will be daily_counts if month is specified
        
        # ชื่อสาขา
        cell = ws.cell(row=row_idx, column=1)
        cell.value = branch_name_display
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        cell.alignment = Alignment(horizontal='left', vertical='center')
        
        branch_total = 0
        
        # ข้อมูลแต่ละเดือน/วัน
        for period_num in data_range:
            col_idx = period_num + 1
            count = counts.get(period_num, 0)
            
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.value = count
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                top=Side(style='thin'), bottom=Side(style='thin'))
            
            if count > 0:
                cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
            
            total_by_period[period_num - 1] += count
            branch_total += count
        
        # คอลัมน์รวมของสาขา
        cell = ws.cell(row=row_idx, column=total_col_idx)
        cell.value = branch_total
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="d4edda", end_color="d4edda", fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center')
        
        grand_total += branch_total
        row_idx += 1
    
    # แถวรวมทั้งหมด
    cell = ws.cell(row=row_idx, column=1)
    cell.value = 'รวมทั้งหมด'
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    for period_num in data_range:
        col_idx = period_num + 1
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.value = total_by_period[period_num - 1]
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="d1ecf1", end_color="d1ecf1", fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    cell = ws.cell(row=row_idx, column=total_col_idx)
    cell.value = grand_total
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # ปรับความกว้างคอลัมน์
    ws.column_dimensions['A'].width = 30
    for col_idx in range(2, total_col_idx + 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 10
    
    # สร้างกราฟแท่ง (Bar Chart)
    chart = BarChart()
    if month:
        chart.title = f"สถิติการเทรดรายวัน Zone {zone_name} - {month_names_th[month-1]} {year}"
        chart.x_axis.title = 'วันที่'
    else:
        chart.title = f"สถิติการเทรดรายเดือน Zone {zone_name} - {year}"
        chart.x_axis.title = 'เดือน'
        
    chart.y_axis.title = 'จำนวนรายการ'
    chart.style = 10
    
    # Data for chart (Transpose rows/cols if needed, but here we plot branches as series)
    # rows: [BranchName, Val1, Val2, ..., Total]
    # We want X-axis = Time (Months/Days), Series = Branches
    
    # Reference data excluding 'Total' column
    data_len = num_days if month else 12
    data = Reference(ws, min_col=2, min_row=1, max_col=data_len + 1, max_row=row_idx) # max_row is now row_idx (including total row)
    
    chart.add_data(data, titles_from_data=True, from_rows=True)
    
    # Categories (Header row excluding 'Branch' and 'Total')
    cats = Reference(ws, min_col=2, min_row=1, max_col=data_len + 1)
    chart.set_categories(cats)
    
    ws.add_chart(chart, f"A{row_idx + 2}")
    
    filename = f"zone_report_{year}_{month if month else 'annual'}_{zone_name}.xlsx"
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    wb.save(filepath)
    print(f"✅ Excel report saved: {filepath}")
    
    return filepath


def generate_annual_excel_report(trade_data, year, branch_id=None, branch_name=None, month=None):
    """
    สร้างไฟล์ Excel รายงานรายปี (หรือรายเดือน)
    - trade_data: list ของข้อมูล trade
    - year: ปีที่ต้องการ (ค.ศ.)
    - branch_id: รหัสสาขา (optional)
    - branch_name: ชื่อสาขา (optional)
    - month: เดือนที่ต้องการ (optional) - ถ้าระบุจะเป็นรายงานรายเดือน
    """
    # ถ้ามี month ให้สร้างรายงานรายเดือน (Daily breakdown)
    if month:
        return generate_monthly_excel_report(trade_data, year, month, branch_id, branch_name)

    # 1. เตรียมข้อมูลกราฟ (รายเดือน)
    monthly_counts = defaultdict(int)
    
    import re
    
    for item in trade_data:
        doc_date = item.get('document_date', '')
        if doc_date:
            try:
                # รองรับรูปแบบ /Date(timestamp)/
                if doc_date.startswith('/Date('):
                    timestamp_match = re.search(r'/Date\((\d+)\)/', doc_date)
                    if timestamp_match:
                        timestamp = int(timestamp_match.group(1)) / 1000  # แปลง milliseconds เป็น seconds
                        date_obj = datetime.fromtimestamp(timestamp)
                        
                        if date_obj.year == year:
                            monthly_counts[date_obj.month] += 1
                else:
                    # รองรับรูปแบบ DD/MM/YYYY
                    date_parts = doc_date.split('/')
                    if len(date_parts) == 3:
                        day, month, year_str = date_parts
                        month_num = int(month)
                        
                        # นับเฉพาะเดือนที่อยู่ในปีที่ต้องการ
                        record_year = int(year_str)
                        if record_year == year:
                            monthly_counts[month_num] += 1
            except (ValueError, IndexError, AttributeError) as e:
                print(f"Warning: Could not parse date {doc_date}: {e}")
                continue
    
    # สร้าง Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = f"Trade Report {year}"
    
    # กำหนดชื่อเดือน
    month_names = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
                   'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    # สร้างหัวตาราง
    ws['A1'] = 'TRADE'
    ws['A1'].font = Font(bold=True, size=12)
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    
    # เขียนชื่อเดือน
    for col_idx, month_name in enumerate(month_names, start=2):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = month_name
        cell.font = Font(bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
    
    # เขียนข้อมูลปี
    ws['A2'] = year
    ws['A2'].font = Font(bold=True, size=11)
    ws['A2'].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
    ws['A2'].border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # เขียนจำนวนเทรดแต่ละเดือน
    for month_num in range(1, 13):
        col_idx = month_num + 1
        cell = ws.cell(row=2, column=col_idx)
        cell.value = monthly_counts.get(month_num, 0)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # ใส่สีพื้นหลังสลับ
        if monthly_counts.get(month_num, 0) > 0:
            cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
    
    # ปรับความกว้างคอลัมน์
    ws.column_dimensions['A'].width = 12
    for col_idx in range(2, 14):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 10
    
    # สร้าง Line Chart
    line_chart = LineChart()
    line_chart.title = f"Monthly Trade Count - {year}"
    line_chart.style = 10
    line_chart.y_axis.title = 'Trade Count'
    line_chart.x_axis.title = 'Month'
    line_chart.height = 10
    line_chart.width = 20
    
    # เพิ่มข้อมูลลงกราฟ
    data = Reference(ws, min_col=2, min_row=1, max_col=13, max_row=2)
    line_chart.add_data(data, titles_from_data=True)
    
    # ตั้งค่า categories (ชื่อเดือน)
    cats = Reference(ws, min_col=2, min_row=1, max_col=13)
    line_chart.set_categories(cats)
    
    # วางกราฟเส้น
    ws.add_chart(line_chart, "A4")
    
    # สร้าง Bar Chart
    bar_chart = BarChart()
    bar_chart.title = f"Monthly Trade Count - {year}"
    bar_chart.style = 10
    bar_chart.y_axis.title = 'Trade Count'
    bar_chart.x_axis.title = 'Month'
    bar_chart.height = 10
    bar_chart.width = 20
    
    # เพิ่มข้อมูลลงกราฟ
    bar_chart.add_data(data, titles_from_data=True)
    bar_chart.set_categories(cats)
    
    # วางกราฟแท่ง
    ws.add_chart(bar_chart, "A20")
    
    # สร้างชื่อไฟล์
    if branch_id and branch_name:
        filename = f"trade_report_{year}_branch_{branch_id}.xlsx"
    else:
        filename = f"trade_report_{year}_all_branches.xlsx"
    
    # บันทึกไฟล์ใน temp directory
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    wb.save(filepath)
    print(f"✅ Excel report saved: {filepath}")
    
    return filepath


def generate_excel_report(trade_data, report_summary, date_start, date_end):
    """
    สร้างรายงาน Excel ตามช่วงวันที่ที่เลือก
    
    Args:
        trade_data: list of trade records
        report_summary: dict of summary data
        date_start: วันที่เริ่มต้น (DD/MM/YYYY)
        date_end: วันที่สิ้นสุด (DD/MM/YYYY)
    
    Returns:
        str: path to generated Excel file
    """
    wb = Workbook()
    
    # --- Sheet 1: Summary ---
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    # หัวข้อรายงาน
    ws_summary['A1'] = 'Trade Report Summary'
    ws_summary['A1'].font = Font(bold=True, size=16, color="333333")
    ws_summary.merge_cells('A1:D1')
    
    ws_summary['A2'] = f'Date Range: {date_start} - {date_end}'
    ws_summary['A2'].font = Font(size=12, italic=True)
    ws_summary.merge_cells('A2:D2')
    
    # สรุปภาพรวม
    ws_summary['A4'] = 'Overview'
    ws_summary['A4'].font = Font(bold=True, size=14)
    
    overview_data = [
        ('Total Items', report_summary.get('totalCount', 0)),
        ('Confirmed Items', report_summary.get('confirmedCount', 0)),
        ('Not Confirmed Items', report_summary.get('notConfirmedCount', 0)),
        ('Cancelled Items', report_summary.get('cancelledCount', 0)),
        ('Total Amount', f"{report_summary.get('totalAmount', 0):,.2f}"),
        ('Confirmed Amount', f"{report_summary.get('confirmedAmount', 0):,.2f}")
    ]
    
    for idx, (label, value) in enumerate(overview_data, start=5):
        ws_summary.cell(row=idx, column=1).value = label
        ws_summary.cell(row=idx, column=2).value = value
        ws_summary.cell(row=idx, column=1).font = Font(bold=True)
        ws_summary.cell(row=idx, column=2).alignment = Alignment(horizontal='right')
    
    # สรุปตามสถานะ
    row_start = 13
    ws_summary.cell(row=row_start, column=1).value = 'Status Summary'
    ws_summary.cell(row=row_start, column=1).font = Font(bold=True, size=14)
    
    ws_summary.cell(row=row_start+1, column=1).value = 'Status'
    ws_summary.cell(row=row_start+1, column=2).value = 'Count'
    ws_summary.cell(row=row_start+1, column=3).value = 'Amount'
    
    # Header Style
    for col in range(1, 4):
        cell = ws_summary.cell(row=row_start+1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')
    
    current_row = row_start + 2
    for status, data in report_summary.get('statusSummary', {}).items():
        ws_summary.cell(row=current_row, column=1).value = status
        ws_summary.cell(row=current_row, column=2).value = data.get('count', 0)
        ws_summary.cell(row=current_row, column=3).value = f"{data.get('amount', 0):,.2f}"
        current_row += 1
        
    # สรุปตามแบรนด์
    row_start = current_row + 2
    ws_summary.cell(row=row_start, column=1).value = 'Brand Summary'
    ws_summary.cell(row=row_start, column=1).font = Font(bold=True, size=14)
    
    ws_summary.cell(row=row_start+1, column=1).value = 'Brand'
    ws_summary.cell(row=row_start+1, column=2).value = 'Count'
    ws_summary.cell(row=row_start+1, column=3).value = 'Amount'
    
    # Header Style
    for col in range(1, 4):
        cell = ws_summary.cell(row=row_start+1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')
        
    current_row = row_start + 2
    for brand, data in report_summary.get('brandSummary', {}).items():
        ws_summary.cell(row=current_row, column=1).value = brand
        ws_summary.cell(row=current_row, column=2).value = data.get('count', 0)
        ws_summary.cell(row=current_row, column=3).value = f"{data.get('amount', 0):,.2f}"
        current_row += 1
        
    # ปรับความกว้างคอลัมน์ Summary
    ws_summary.column_dimensions['A'].width = 30
    ws_summary.column_dimensions['B'].width = 15
    ws_summary.column_dimensions['C'].width = 20
    
    # --- Sheet 2: Details ---
    ws_details = wb.create_sheet("Details")
    
    headers = [
        'Document No', 'Date', 'Branch', 'Sale Code', 'Sale Name', 
        'Customer Name', 'Brand', 'Model', 'Status', 'Amount', 
        'Invoice No', 'Ref No'
    ]
    
    for col_idx, header in enumerate(headers, start=1):
        cell = ws_details.cell(row=1, column=col_idx)
        cell.value = header
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')
    
    for row_idx, item in enumerate(trade_data, start=2):
        ws_details.cell(row=row_idx, column=1).value = item.get('document_no', '')
        ws_details.cell(row=row_idx, column=2).value = item.get('document_date', '')
        ws_details.cell(row=row_idx, column=3).value = item.get('branch_name', '') # Note: API might not return branch_name in item directly if filtered by branch
        ws_details.cell(row=row_idx, column=4).value = item.get('SALE_CODE', '')
        ws_details.cell(row=row_idx, column=5).value = item.get('SALE_NAME', '')
        ws_details.cell(row=row_idx, column=6).value = item.get('customer_name', '')
        ws_details.cell(row=row_idx, column=7).value = item.get('brand_name', '')
        ws_details.cell(row=row_idx, column=8).value = item.get('series', '')
        ws_details.cell(row=row_idx, column=9).value = item.get('BIDDING_STATUS_NAME', '')
        
        amount = item.get('amount')
        try:
            amount = float(amount) if amount else 0.0
        except:
            amount = 0.0
        ws_details.cell(row=row_idx, column=10).value = amount
        
        ws_details.cell(row=row_idx, column=11).value = item.get('invoice_no', '')
        ws_details.cell(row=row_idx, column=12).value = item.get('DOCUMENT_REF_1', '')
    
    # ปรับความกว้างคอลัมน์ Details
    widths = [20, 15, 20, 15, 20, 20, 15, 20, 20, 15, 20, 20]
    for i, w in enumerate(widths):
        ws_details.column_dimensions[chr(65+i)].width = w
        
    # บันทึกไฟล์
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"trade_report_{date_str}.xlsx"
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    wb.save(filepath)
    print(f"✅ Excel report saved: {filepath}")
    
    return filepath

def parse_year_from_command(year_str):
    """
    แปลงปีจากคำสั่งเป็น Gregorian year
    รองรับทั้ง พ.ศ. และ ค.ศ.
    
    Args:
        year_str: string ปี เช่น "2024", "2567"
    
    Returns:
        int: Gregorian year หรือ None ถ้าไม่ valid
    """
    try:
        year = int(year_str)
        
        # ถ้าเป็น พ.ศ. (มากกว่า 2500) แปลงเป็น ค.ศ.
        if year > 2500:
            year = year - 543
        
        # ตรวจสอบว่าอยู่ในช่วงที่ยอมรับได้
        current_year = datetime.now().year
        if 2020 <= year <= current_year + 1:
            return year
        else:
            return None
    except ValueError:
        return None


def get_year_date_range(year):
    """
    คำนวณวันแรกและวันสุดท้ายของปี
    
    Args:
        year: Gregorian year
    
    Returns:
        tuple: (date_start, date_end) ในรูปแบบ DD/MM/YYYY
    """
    date_start = f"01/01/{year}"
    date_end = f"31/12/{year}"
    
    return date_start, date_end

def parse_date(date_str):
    """
    Helper function to parse date string from various formats
    """
    if not date_str:
        return None
        
    try:
        # Format: /Date(1704042000000)/
        if date_str.startswith('/Date('):
            timestamp_match = re.search(r'/Date\((\d+)\)/', date_str)
            if timestamp_match:
                timestamp = int(timestamp_match.group(1)) / 1000
                return datetime.fromtimestamp(timestamp)
                
        # Format: DD/MM/YYYY
        parts = date_str.split('/')
        if len(parts) == 3:
            day, month, year = map(int, parts)
            return datetime(year, month, day)
            
    except Exception:
        pass
        
    return None
