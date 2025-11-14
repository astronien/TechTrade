# Requirements Document

## Introduction

ฟีเจอร์นี้เพิ่มความสามารถในการดึงรายการสาขา (Branch) ทั้งหมดจาก API ของระบบ EVE และแสดงเป็น dropdown ในหน้าค้นหา เนื่องจากปัจจุบันผู้ใช้ไม่ทราบว่ามีสาขาอะไรบ้างในระบบ และต้องใช้ค่า BRANCH_ID แบบ hardcode (231) ฟีเจอร์นี้จะช่วยให้ผู้ใช้เห็นรายการสาขาทั้งหมดและเลือกสาขาที่ต้องการค้นหาข้อมูล Trade-In ได้อย่างสะดวก

## Glossary

- **System**: ระบบ Trade-In Management System ที่พัฒนาด้วย Flask
- **EVE API**: API ของระบบ eve.techswop.com ที่ใช้ดึงข้อมูล
- **Branch**: สาขาของร้านค้า แต่ละสาขามี ID และชื่อเฉพาะ
- **Dropdown**: รายการแบบเลื่อนลงที่ผู้ใช้สามารถเลือกได้
- **Session ID**: รหัสเซสชันที่ใช้ในการยืนยันตัวตนกับ EVE API
- **Frontend**: ส่วนหน้าบ้านของระบบ (HTML/JavaScript)
- **Backend**: ส่วนหลังบ้านของระบบ (Flask/Python)

## Requirements

### Requirement 1

**User Story:** ในฐานะผู้ใช้งานระบบ ฉันต้องการเห็นรายการสาขาทั้งหมดที่มีในระบบ เพื่อที่ฉันจะได้เลือกสาขาที่ต้องการดูข้อมูล

#### Acceptance Criteria

1. WHEN THE System โหลดหน้าเว็บครั้งแรก, THE System SHALL ดึงข้อมูลรายการสาขาจาก EVE API endpoint `/GetDropDownBranch`
2. WHEN THE System ได้รับข้อมูลสาขาสำเร็จ, THE System SHALL แสดงรายการสาขาใน Dropdown บนหน้าเว็บ
3. THE System SHALL แสดงชื่อสาขาและ ID ของสาขาในรูปแบบที่อ่านง่าย
4. IF การดึงข้อมูลสาขาล้มเหลว, THEN THE System SHALL แสดงข้อความแจ้งเตือนข้อผิดพลาดให้ผู้ใช้ทราบ
5. THE System SHALL เก็บค่า BRANCH_ID เริ่มต้นเป็น "231" สำหรับกรณีที่ยังไม่มีการเลือกสาขา

### Requirement 2

**User Story:** ในฐานะผู้ใช้งานระบบ ฉันต้องการเลือกสาขาจาก dropdown เพื่อดูข้อมูล Trade-In ของสาขานั้นๆ

#### Acceptance Criteria

1. WHEN ผู้ใช้เลือกสาขาจาก Dropdown, THE System SHALL บันทึกค่า BRANCH_ID ที่เลือก
2. WHEN ผู้ใช้เลือกสาขาใหม่, THE System SHALL ดึงข้อมูล Trade-In ของสาขาที่เลือกโดยอัตโนมัติ
3. THE System SHALL แสดงสาขาที่เลือกอยู่ใน Dropdown
4. THE System SHALL เก็บค่าสาขาที่เลือกไว้ใน localStorage เพื่อให้ผู้ใช้ไม่ต้องเลือกใหม่เมื่อรีเฟรชหน้า
5. WHEN ผู้ใช้รีเฟรชหน้าเว็บ, THE System SHALL โหลดค่าสาขาที่เลือกไว้ล่าสุดจาก localStorage

### Requirement 3

**User Story:** ในฐานะผู้พัฒนาระบบ ฉันต้องการ API endpoint ที่ดึงข้อมูลสาขาจาก EVE API เพื่อให้ Frontend เรียกใช้งานได้

#### Acceptance Criteria

1. THE Backend SHALL สร้าง API endpoint `/api/branches` สำหรับดึงข้อมูลสาขา
2. WHEN Frontend เรียก endpoint `/api/branches`, THE Backend SHALL ส่ง request ไปยัง EVE API endpoint `/GetDropDownBranch`
3. THE Backend SHALL ส่ง Session ID ใน cookies header เมื่อเรียก EVE API
4. WHEN EVE API ตอบกลับสำเร็จ, THE Backend SHALL ส่งข้อมูลสาขาในรูปแบบ JSON กลับไปยัง Frontend
5. IF EVE API ตอบกลับด้วยข้อผิดพลาด, THEN THE Backend SHALL ส่ง error response พร้อมข้อความอธิบายกลับไปยัง Frontend

### Requirement 4

**User Story:** ในฐานะผู้ใช้งานระบบ ฉันต้องการให้ระบบใช้สาขาที่เลือกในการค้นหาและสร้างรายงาน เพื่อให้ข้อมูลที่แสดงตรงกับสาขาที่ต้องการ

#### Acceptance Criteria

1. WHEN ผู้ใช้ค้นหาข้อมูล Trade-In, THE System SHALL ใช้ BRANCH_ID ที่เลือกในการส่ง request ไปยัง API
2. WHEN ผู้ใช้สร้างรายงาน, THE System SHALL ใช้ BRANCH_ID ที่เลือกในการดึงข้อมูลรายงาน
3. THE System SHALL แสดงชื่อสาขาที่เลือกในหน้ารายงาน
4. WHEN ผู้ใช้เปลี่ยนสาขา, THE System SHALL อัพเดทข้อมูลทั้งหมดให้ตรงกับสาขาใหม่
5. THE System SHALL รองรับการเลือก "ทุกสาขา" ถ้า EVE API รองรับ

### Requirement 5

**User Story:** ในฐานะผู้ใช้งานระบบ ฉันต้องการให้ระบบแสดงสถานะการโหลดข้อมูลสาขา เพื่อให้ฉันทราบว่าระบบกำลังทำงาน

#### Acceptance Criteria

1. WHILE THE System กำลังดึงข้อมูลสาขา, THE System SHALL แสดง loading indicator ใน Dropdown
2. WHEN การดึงข้อมูลสาขาเสร็จสิ้น, THE System SHALL ซ่อน loading indicator
3. IF การดึงข้อมูลใช้เวลานานเกิน 10 วินาที, THEN THE System SHALL แสดงข้อความ timeout error
4. THE System SHALL แสดงข้อความ "กำลังโหลดสาขา..." ขณะรอข้อมูล
5. WHEN ข้อมูลสาขาโหลดเสร็จ, THE System SHALL แสดงจำนวนสาขาที่พบ
