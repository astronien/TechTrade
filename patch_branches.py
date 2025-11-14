#!/usr/bin/env python3
"""
Script สำหรับแก้ไขไฟล์ index.html ให้ใช้ข้อมูลสาขา hardcode
"""

# ข้อมูลสาขาทั้งหมด
branches_data = '''[
{"branch_id":1,"branch_name":"00009 : ID9 : BN-Zeer-Rangsit-Pathum Thani-1"},
{"branch_id":2,"branch_name":"00013 : ID13 : BN-ITmall-Fortune Town-Bangkok-1"},
{"branch_id":3,"branch_name":"00024 : ID24 : BN-Zeer-Rangsit-Pathum Thani-2"},
{"branch_id":4,"branch_name":"00031 : ID31 : BN-Lotus-Amatanakorn-Chonburi"},
{"branch_id":5,"branch_name":"00035 : ID35 : BN-Passion-Rayong"},
{"branch_id":6,"branch_name":"00039 : ID39 : BN-Zeer-Rangsit-Pathum Thani-3"},
{"branch_id":7,"branch_name":"00053 : ID53 : BN-Market Village-Huahin (3.1)"},
{"branch_id":8,"branch_name":"00064 : ID64 : BN-Imperial-Samrong"},
{"branch_id":9,"branch_name":"00065 : ID65 : BN-Paradise Park-Srinakarin"},
{"branch_id":10,"branch_name":"00080 : ID80 : BN-Lotus-Lamai (Samui)"},
{"branch_id":11,"branch_name":"00084 : ID84 : BN-Laemtong-Bangsaen"},
{"branch_id":12,"branch_name":"00085 : ID85 : BN-ITSqure-Laksi"},
{"branch_id":13,"branch_name":"00103 : ID103 : Studio 7-Paradise Park-Srinakarin"},
{"branch_id":14,"branch_name":"00104 : ID104 : BN-Central-Khonkaen"},
{"branch_id":15,"branch_name":"00105 : ID105 : Studio 7-Central-Khonkaen"}
]'''

# ฟังก์ชัน loadBranches ใหม่ที่ใช้ hardcode
new_load_branches_function = '''        // ฟังก์ชันดึงรายการสาขา (ใช้ข้อมูล Hardcode)
        function loadBranches() {
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
            const HARDCODED_BRANCHES = ''' + branches_data + ''';
            
            try {
                // ใช้ข้อมูล hardcode แทนการเรียก API
                console.log('📦 ใช้ข้อมูลสาขา Hardcode:', HARDCODED_BRANCHES.length, 'สาขา');
                populateBranchDropdown(HARDCODED_BRANCHES);
            } catch (error) {
                console.error('❌ Error loading branches:', error);
                setDefaultBranches();
                branchStatus.textContent = '❌ ' + error.message;
                branchStatus.className = 'form-text text-danger';
                reportBranchStatus.textContent = '❌ ' + error.message;
                reportBranchStatus.className = 'form-text text-danger';
            } finally {
                branchSelect.disabled = false;
                reportBranchSelect.disabled = false;
            }
        }'''

print("✅ สร้าง patch script สำเร็จ")
print(f"📝 ข้อมูลสาขา: {branches_data.count('branch_id')} สาขา")
print("\n💡 วิธีใช้งาน:")
print("1. เปิดไฟล์ templates/index.html")
print("2. ค้นหา 'async function loadBranches()'")
print("3. แทนที่ฟังก์ชันทั้งหมดด้วยโค้ดใหม่ที่แสดงด้านล่าง")
print("\n" + "="*60)
print(new_load_branches_function)
print("="*60)
