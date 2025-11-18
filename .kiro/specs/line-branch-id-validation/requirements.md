# Requirements Document

## Introduction

ระบบ LINE Bot ปัจจุบันมีปัญหาในการแปลงหมายเลขสาขาที่ผู้ใช้ป้อนเข้ามา ทำให้เมื่อผู้ใช้พิมพ์ "รายงาน 115 พฤศจิกายน" กลับได้รายงานของสาขา ID 368 แทน ปัญหานี้เกิดจากการที่ระบบไม่ได้ตรวจสอบและแปลงหมายเลขสาขาอย่างถูกต้องก่อนนำไปใช้ในการค้นหาข้อมูล

## Glossary

- **LINE Bot**: ระบบตอบกลับอัตโนมัติผ่าน LINE Messaging API
- **Branch ID**: รหัสประจำตัวสาขาที่ใช้ในระบบฐานข้อมูล (เช่น 368, 369)
- **User Input Branch Number**: ตัวเลขที่ผู้ใช้พิมพ์เข้ามา (เช่น 115, 9, 13)
- **Branch Name**: ชื่อสาขาในรูปแบบ "ID[number] : [ชื่อสาขา]" (เช่น "ID115 : สาขาตัวอย่าง")
- **Command Parser**: ส่วนของโค้ดที่แยกวิเคราะห์คำสั่งจากผู้ใช้

## Requirements

### Requirement 1

**User Story:** ในฐานะผู้ใช้ LINE Bot ฉันต้องการให้ระบบแสดงรายงานของสาขาที่ฉันระบุอย่างถูกต้อง เพื่อให้ฉันได้ข้อมูลที่ตรงกับความต้องการ

#### Acceptance Criteria

1. WHEN a user sends a command with a branch number THEN the system SHALL parse the branch number from the user input correctly
2. WHEN the system receives a branch number THEN the system SHALL validate that the branch number exists in the branches database
3. WHEN a valid branch number is provided THEN the system SHALL map the branch number to the correct branch_id for database queries
4. WHEN an invalid branch number is provided THEN the system SHALL return an error message indicating the branch was not found
5. WHEN the system searches for a branch THEN the system SHALL match the user input number against the numeric portion of the branch_name field (e.g., "115" matches "ID115 : สาขาตัวอย่าง")

### Requirement 2

**User Story:** ในฐานะผู้ใช้ LINE Bot ฉันต้องการได้รับข้อความแจ้งเตือนที่ชัดเจน เมื่อฉันพิมพ์หมายเลขสาขาที่ไม่มีในระบบ เพื่อให้ฉันสามารถแก้ไขคำสั่งได้ทันที

#### Acceptance Criteria

1. WHEN a user provides a non-existent branch number THEN the system SHALL display an error message with the invalid branch number
2. WHEN displaying an error message THEN the system SHALL include examples of valid branch numbers
3. WHEN a branch lookup fails THEN the system SHALL NOT proceed with generating a report

### Requirement 3

**User Story:** ในฐานะนักพัฒนาระบบ ฉันต้องการให้ฟังก์ชัน find_branch ทำงานได้อย่างถูกต้อง เพื่อให้สามารถค้นหาสาขาจากหมายเลขที่ผู้ใช้ป้อนได้

#### Acceptance Criteria

1. WHEN find_branch receives a numeric string input THEN the system SHALL search for a branch where the branch_name contains "ID[input]"
2. WHEN multiple branches match the pattern THEN the system SHALL return the first exact match
3. WHEN no branches match the pattern THEN the system SHALL return None
4. WHEN find_branch is called THEN the system SHALL load branch data from extracted_branches.json file
5. WHEN the branch data file is missing or corrupted THEN the system SHALL handle the error gracefully and return an appropriate error message
