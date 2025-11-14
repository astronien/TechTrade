# Implementation Plan - Branch Dropdown Feature

- [x] 1. สร้าง Backend API endpoint สำหรับดึงข้อมูลสาขา
  - สร้าง route `/api/branches` ใน `app.py` ที่รับ GET request
  - ดึง session_id จาก Flask session
  - เรียก EVE API endpoint `/GetDropDownBranch` พร้อม session cookies
  - แปลง response จาก EVE API เป็น JSON format ที่ Frontend ใช้งานได้
  - จัดการ error cases (invalid session, API error, timeout)
  - Return JSON response ที่มี success flag และ branches list
  - _Requirements: 1.1, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 2. เพิ่ม Branch Dropdown UI ในหน้า index.html
  - เพิ่ม HTML structure สำหรับ dropdown (select element) ในส่วน search form
  - เพิ่ม label "เลือกสาขา:" และ select element พร้อม loading state
  - เพิ่ม status message element สำหรับแสดงข้อความ loading/error
  - จัด styling ให้เข้ากับ UI ที่มีอยู่
  - _Requirements: 1.2, 1.3, 5.1, 5.4_

- [x] 3. สร้าง JavaScript functions สำหรับจัดการ Branch Dropdown
- [x] 3.1 สร้างฟังก์ชัน loadBranches()
  - เรียก API `/api/branches` ด้วย fetch
  - แสดง loading indicator ขณะรอข้อมูล
  - จัดการ timeout (10 วินาที)
  - จัดการ error response และแสดง error message
  - เรียก populateBranchDropdown() เมื่อได้ข้อมูล
  - _Requirements: 1.1, 1.4, 5.1, 5.2, 5.3_

- [x] 3.2 สร้างฟังก์ชัน populateBranchDropdown(branches)
  - Clear options เดิมใน dropdown
  - สร้าง option elements จาก branches array
  - แสดงจำนวนสาขาที่พบ
  - โหลดค่าสาขาที่เลือกไว้จาก localStorage
  - Set selected option ตามค่าที่โหลด
  - _Requirements: 1.2, 1.3, 2.3, 5.5_

- [x] 3.3 สร้างฟังก์ชัน saveBranchSelection() และ loadSavedBranch()
  - saveBranchSelection(): บันทึก BRANCH_ID และชื่อสาขาลง localStorage
  - loadSavedBranch(): โหลดค่าจาก localStorage หรือใช้ default "231"
  - เรียก saveBranchSelection() เมื่อ user เลือกสาขาใหม่
  - _Requirements: 2.1, 2.4, 2.5, 1.5_

- [x] 3.4 สร้าง event handler สำหรับ dropdown change
  - เพิ่ม onchange event listener ให้ select element
  - เรียก saveBranchSelection() เมื่อมีการเปลี่ยนแปลง
  - อัพเดทข้อมูล Trade-In ด้วย BRANCH_ID ใหม่ (ถ้ามีข้อมูลแสดงอยู่)
  - _Requirements: 2.1, 2.2, 4.4_

- [x] 4. แก้ไขฟังก์ชัน searchTradein() ให้ใช้ BRANCH_ID จาก dropdown
  - ลบ hardcoded BRANCH_ID = "231"
  - ดึงค่า BRANCH_ID จาก dropdown element หรือ localStorage
  - ใช้ค่า default "231" ถ้าไม่มีค่าใน dropdown
  - ส่ง BRANCH_ID ที่เลือกไปใน API request
  - _Requirements: 4.1, 2.1_

- [x] 5. แก้ไขฟังก์ชัน generateReport() ให้ใช้ BRANCH_ID จาก dropdown
  - ดึงค่า BRANCH_ID จาก dropdown element
  - ส่ง BRANCH_ID ไปใน report API request
  - แสดงชื่อสาขาในหน้ารายงาน (ถ้าต้องการ)
  - _Requirements: 4.2, 4.3_

- [x] 6. เพิ่ม initialization code ในหน้า index.html
  - เรียก loadBranches() เมื่อ document ready
  - โหลดค่าสาขาที่บันทึกไว้จาก localStorage
  - Set dropdown เป็นค่าที่โหลด
  - จัดการกรณีที่โหลดสาขาล้มเหลว (ใช้ default value)
  - _Requirements: 1.1, 2.5, 1.5_

- [ ]* 7. เพิ่ม error handling และ user feedback
  - แสดง error message ที่เหมาะสมสำหรับแต่ละ error case
  - เพิ่มปุ่ม "ลองใหม่" สำหรับกรณี error
  - แสดง loading state ที่ชัดเจน
  - Log errors ไปที่ console สำหรับ debugging
  - _Requirements: 1.4, 5.1, 5.2, 5.3, 5.4_

- [ ]* 8. ทดสอบ integration กับระบบที่มีอยู่
  - ทดสอบ login → load branches → select branch → search
  - ทดสอบ select branch → generate report
  - ทดสอบ refresh page → branch selection ยังคงอยู่
  - ทดสอบ error cases (invalid session, API down, timeout)
  - ทดสอบ fallback ไปใช้ default BRANCH_ID เมื่อเกิด error
  - _Requirements: 2.5, 4.1, 4.2, 4.4_
