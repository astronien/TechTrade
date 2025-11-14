#!/usr/bin/env python3
"""
สคริปต์สำหรับแก้ไขไฟล์ index.html ให้ใช้ข้อมูลสาขา hardcode
"""
import re

# ข้อมูลสาขาทั้งหมดที่คุณให้มา (ตัวอย่าง - ใส่ข้อมูลครบ 1474 สาขา)
BRANCHES_JSON = '''[
{"branch_id":1,"branch_name":"00009 : ID9 : BN-Zeer-Rangsit-Pathum Thani-1"},
{"branch_id":2,"branch_name":"00013 : ID13 : BN-ITmall-Fortune Town-Bangkok-1"},
{"branch_id":3,"branch_name":"00024 : ID24 : BN-Zeer-Rangsit-Pathum Thani-2"},
{"branch_id":4,"branch_name":"00031 : ID31 : BN-Lotus-Amatanakorn-Chonburi"},
{"branch_id":5,"branch_name":"00035 : ID35 : BN-Passion-Rayong"}
]'''

# ฟังก์ชัน loadBranches ใหม่
NEW_LOAD_BRANCHES = f'''        // ฟังก์ชันดึงรายการสาขา (ใช้ข้อมูล Hardcode)
        function loadBranches() {{
            const branchSelect = document.getElementById('branchSelect');
            const reportBranchSelect = document.getElementById('reportBranchSelect');
            const branchStatus = document.getElementById('branchStatus');
            const reportBranchStatus = document.getElementById('reportBranchStatus');
            
            // แสดง loading indicator
            branchSelect.innerHTML = '<option value="">กำลังโหลดสาขา...</option>';
            reportBranchSelect.innerHTML = '<option value="">กำลังโหลดสาขา...</option>';
            branchSelect.disabled = true;
            reportBranchSelect.disabled = true;
            
            branchStatus.textContent = '⏳ กำลังโหลดสาขา...';
            branchStatus.className = 'form-text text-muted';
            reportBranchStatus.textContent = '⏳ กำลังโหลดสาขา...';
            reportBranchStatus.className = 'form-text text-muted';

            // ข้อมูลสาขา Hardcode
            const HARDCODED_BRANCHES = {BRANCHES_JSON};
            
            try {{
                // ใช้ข้อมูล hardcode แทนการเรียก API
                console.log('📦 ใช้ข้อมูลสาขา Hardcode:', HARDCODED_BRANCHES.length, 'สาขา');
                populateBranchDropdown(HARDCODED_BRANCHES);
            }} catch (error) {{
                console.error('❌ Error loading branches:', error);
                setDefaultBranches();
                branchStatus.textContent = '❌ ' + error.message;
                branchStatus.className = 'form-text text-danger';
                reportBranchStatus.textContent = '❌ ' + error.message;
                reportBranchStatus.className = 'form-text text-danger';
            }} finally {{
                branchSelect.disabled = false;
                reportBranchSelect.disabled = false;
            }}
        }}'''

def apply_patch():
    """แก้ไขไฟล์ index.html"""
    file_path = 'templates/index.html'
    
    try:
        # อ่านไฟล์
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # ค้นหาและแทนที่ฟังก์ชัน loadBranches
        # Pattern: จับตั้งแต่ "async function loadBranches()" จนถึง "}" ปิดฟังก์ชัน
        pattern = r'async function loadBranches\(\).*?^\s{8}\}'
        
        if re.search(pattern, content, re.MULTILINE | re.DOTALL):
            content = re.sub(pattern, NEW_LOAD_BRANCHES, content, flags=re.MULTILINE | re.DOTALL)
            
            # บันทึกไฟล์
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ แก้ไขไฟล์สำเร็จ!")
            print(f"📝 ไฟล์: {file_path}")
            print(f"🔧 แทนที่ฟังก์ชัน loadBranches() ด้วยข้อมูล hardcode")
        else:
            print("⚠️ ไม่พบฟังก์ชัน loadBranches() ในไฟล์")
            print("💡 กรุณาแก้ไขด้วยตนเองตามคำแนะนำใน INSTRUCTIONS.md")
    
    except FileNotFoundError:
        print(f"❌ ไม่พบไฟล์: {file_path}")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")

if __name__ == '__main__':
    print("🔧 กำลังแก้ไขไฟล์ index.html...")
    print("="*60)
    apply_patch()
    print("="*60)
    print("\n💡 หมายเหตุ:")
    print("- ตัวอย่างนี้ใช้ข้อมูล 5 สาขาเท่านั้น")
    print("- กรุณาแก้ไข BRANCHES_JSON ในสคริปต์ให้มีข้อมูลครบ 1474 สาขา")
    print("- หรือแก้ไขด้วยตนเองตามคำแนะนำใน INSTRUCTIONS.md")
