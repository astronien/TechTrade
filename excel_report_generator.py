# Excel Report Generator for Annual Trade Reports
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from datetime import datetime
from collections import defaultdict
import os
import tempfile

def generate_annual_excel_report_for_zone(branches_data, year, zone_name):
    """
    สร้างรายงาน Excel รายปีสำหรับ Zone (แยกตามสาขา)
    
    Args:
        branches_data: list of dict with branch data [{'branch_id': '19', 'branch_name': '...', 'monthly_counts': {...}}]
        year: ปีที่ต้องการรายงาน
        zone_name: ชื่อ Zone
    
    Returns:
        str: path to generated Excel file
    """
    wb = Workbook()
    ws = wb.active
    ws.title = f"Zone Report {year}"
    
    month_names = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
                   'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    # หัวตาราง
    ws['A1'] = 'สาขา'
    ws['A1'].font = Font(bold=True, size=12, color="FFFFFF")
    ws['A1'].fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    
    # เขียนชื่อเดือน
    for col_idx, month_name in enumerate(month_names, start=2):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = month_name
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
    total_by_month = [0] * 12
    grand_total = 0
    
    for branch in branches_data:
        branch_name = branch.get('branch_name', f"สาขา {branch.get('branch_id')}")
        if ' : ' in branch_name:
            branch_name = branch_name.split(' : ')[-1]
        
        monthly_counts = branch.get('monthly_counts', {})
        
        # ชื่อสาขา
        cell = ws.cell(row=row_idx, column=1)
        cell.value = branch_name
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        cell.alignment = Alignment(horizontal='left', vertical='center')
        
        branch_total = 0
        
        # ข้อมูลแต่ละเดือน
        for month_num in range(1, 13):
            col_idx = month_num + 1
            count = monthly_counts.get(month_num, 0)
            
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.value = count
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                top=Side(style='thin'), bottom=Side(style='thin'))
            
            if count > 0:
                cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
            
            total_by_month[month_num - 1] += count
            branch_total += count
        
        # คอลัมน์รวมของสาขา
        cell = ws.cell(row=row_idx, column=14)
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
    
    for month_num in range(1, 13):
        col_idx = month_num + 1
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.value = total_by_month[month_num - 1]
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="d1ecf1", end_color="d1ecf1", fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    cell = ws.cell(row=row_idx, column=14)
    cell.value = grand_total
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # ปรับความกว้างคอลัมน์
    ws.column_dimensions['A'].width = 30
    for col_idx in range(2, 15):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 10
    
    # สร้างกราฟ
    bar_chart = BarChart()
    bar_chart.title = f"Monthly Trade Count - {year} - {zone_name}"
    bar_chart.style = 10
    bar_chart.y_axis.title = 'Trade Count'
    bar_chart.x_axis.title = 'Month'
    bar_chart.height = 10
    bar_chart.width = 20
    
    data = Reference(ws, min_col=2, min_row=1, max_col=13, max_row=row_idx)
    bar_chart.add_data(data, titles_from_data=True)
    
    cats = Reference(ws, min_col=2, min_row=1, max_col=13)
    bar_chart.set_categories(cats)
    
    ws.add_chart(bar_chart, f"A{row_idx + 2}")
    
    # บันทึกไฟล์
    filename = f"trade_report_{year}_zone_{zone_name}.xlsx"
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    wb.save(filepath)
    print(f"✅ Excel report saved: {filepath}")
    
    return filepath


def generate_annual_excel_report(trade_data, year, branch_id=None, branch_name=None):
    """
    สร้างรายงาน Excel รายปี พร้อมกราฟ
    
    Args:
        trade_data: list of trade records from API
        year: ปีที่ต้องการรายงาน (Gregorian)
        branch_id: รหัสสาขา (optional)
        branch_name: ชื่อสาขา (optional)
    
    Returns:
        str: path to generated Excel file
    """
    
    # นับจำนวนเทรดแต่ละเดือน
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
