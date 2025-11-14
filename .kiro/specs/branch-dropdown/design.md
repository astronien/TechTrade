# Design Document - Branch Dropdown Feature

## Overview

ฟีเจอร์นี้เพิ่มความสามารถในการเลือกสาขาผ่าน dropdown โดยดึงข้อมูลสาขาจาก EVE API แบบ real-time แทนการใช้ BRANCH_ID แบบ hardcode ระบบจะประกอบด้วย 3 ส่วนหลัก:

1. **Backend API Endpoint** - Flask route ที่เชื่อมต่อกับ EVE API
2. **Frontend Dropdown Component** - UI สำหรับแสดงและเลือกสาขา
3. **State Management** - จัดการค่าสาขาที่เลือกด้วย localStorage

## Architecture

### System Flow

```
User Browser
    ↓
[Frontend - index.html]
    ↓ (1) GET /api/branches
[Flask Backend - app.py]
    ↓ (2) POST /GetDropDownBranch
[EVE API]
    ↓ (3) Return branch list
[Flask Backend]
    ↓ (4) Return JSON
[Frontend]
    ↓ (5) Display dropdown
    ↓ (6) User selects branch
[localStorage] ← Store selected BRANCH_ID
    ↓ (7) Use BRANCH_ID in search/report
```

### Component Interaction

- **Frontend** เรียก `/api/branches` เมื่อโหลดหน้าเว็บ
- **Backend** ทำหน้าที่เป็น proxy ส่ง request ไปยัง EVE API พร้อม session cookies
- **EVE API** ส่งรายการสาขากลับมาในรูปแบบ JSON
- **Frontend** แสดงรายการใน dropdown และเก็บค่าที่เลือกใน localStorage
- เมื่อผู้ใช้ค้นหาหรือสร้างรายงาน ระบบจะใช้ BRANCH_ID ที่เลือก

## Components and Interfaces

### 1. Backend API Endpoint

**Route:** `/api/branches`
**Method:** GET
**Purpose:** ดึงรายการสาขาจาก EVE API

**Implementation Details:**
```python
@app.route('/api/branches', methods=['GET'])
def get_branches():
    # ใช้ session_id จาก session
    # เรียก EVE API: /GetDropDownBranch
    # Return JSON response
```

**Request:**
- ไม่ต้องส่ง parameters
- ใช้ session_id จาก Flask session

**Response Format:**
```json
{
  "success": true,
  "branches": [
    {
      "id": "231",
      "name": "สาขาสยาม"
    },
    {
      "id": "232",
      "name": "สาขาเซ็นทรัล"
    }
  ]
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Failed to fetch branches",
  "message": "Session expired or invalid"
}
```

### 2. EVE API Integration

**Endpoint:** `https://eve.techswop.com/TI/inventory/stock-view-list.aspx/GetDropDownBranch`
**Method:** POST
**Content-Type:** application/json

**Request Headers:**
```
Cookie: ASP.NET_SessionId={session_id}
Content-Type: application/json
```

**Request Body:**
```json
{}
```

**Expected Response:**
ต้องทำการทดสอบเพื่อดูรูปแบบข้อมูลที่แท้จริง แต่คาดว่าจะเป็น:
```json
{
  "d": [
    {"BRANCH_ID": "231", "BRANCH_NAME": "สาขาสยาม"},
    {"BRANCH_ID": "232", "BRANCH_NAME": "สาขาเซ็นทรัล"}
  ]
}
```

### 3. Frontend Dropdown Component

**Location:** `templates/index.html`

**HTML Structure:**
```html
<div class="form-group">
    <label for="branchSelect">เลือกสาขา:</label>
    <select id="branchSelect" class="form-control">
        <option value="">กำลังโหลด...</option>
    </select>
    <small id="branchStatus" class="form-text text-muted"></small>
</div>
```

**JavaScript Functions:**
- `loadBranches()` - ดึงข้อมูลสาขาจาก API
- `populateBranchDropdown(branches)` - แสดงรายการใน dropdown
- `saveBranchSelection(branchId)` - บันทึกค่าใน localStorage
- `loadSavedBranch()` - โหลดค่าที่บันทึกไว้
- `onBranchChange()` - จัดการเมื่อผู้ใช้เลือกสาขาใหม่

### 4. State Management

**localStorage Keys:**
- `selected_branch_id` - เก็บ BRANCH_ID ที่เลือก
- `selected_branch_name` - เก็บชื่อสาขาที่เลือก (optional, สำหรับแสดงผล)

**Default Value:**
- ถ้าไม่มีค่าใน localStorage ให้ใช้ "231" เป็นค่าเริ่มต้น

## Data Models

### Branch Object

```javascript
{
  id: String,        // BRANCH_ID เช่น "231"
  name: String       // BRANCH_NAME เช่น "สาขาสยาม"
}
```

### API Response Model

```python
# Success Response
{
    'success': bool,
    'branches': List[Dict[str, str]]
}

# Error Response
{
    'success': bool,
    'error': str,
    'message': str
}
```

## Error Handling

### Backend Error Scenarios

1. **Session Invalid/Expired**
   - Return 401 status
   - Message: "Session expired. Please login again."
   - Frontend: Redirect to login

2. **EVE API Connection Failed**
   - Return 503 status
   - Message: "Unable to connect to EVE API"
   - Frontend: Show error message, retry button

3. **EVE API Returns Error**
   - Return 500 status
   - Message: Include EVE API error details
   - Frontend: Show error message

4. **Timeout (>10 seconds)**
   - Return 504 status
   - Message: "Request timeout"
   - Frontend: Show timeout message, retry button

### Frontend Error Handling

1. **Network Error**
   - Show: "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์"
   - Action: แสดงปุ่ม "ลองใหม่"

2. **Empty Branch List**
   - Show: "ไม่พบข้อมูลสาขา"
   - Action: ใช้ค่า default (231)

3. **Invalid Response Format**
   - Log error to console
   - Show: "เกิดข้อผิดพลาดในการโหลดข้อมูล"
   - Action: ใช้ค่า default (231)

## Integration Points

### 1. Search Functionality

**Current Implementation:**
```javascript
// ใช้ BRANCH_ID แบบ hardcode
const BRANCH_ID = "231";
```

**New Implementation:**
```javascript
// ดึงจาก localStorage
const BRANCH_ID = localStorage.getItem('selected_branch_id') || "231";
```

**Files to Modify:**
- `templates/index.html` - ฟังก์ชัน `searchTradein()`

### 2. Report Generation

**Current Implementation:**
```javascript
// ส่ง BRANCH_ID แบบ hardcode
data: { branch_id: "231", ... }
```

**New Implementation:**
```javascript
// ใช้ค่าจาก dropdown
const branchId = document.getElementById('branchSelect').value || "231";
data: { branch_id: branchId, ... }
```

**Files to Modify:**
- `templates/index.html` - ฟังก์ชัน `generateReport()`

### 3. Session Management

**Existing Session Flow:**
- User login → Store session_id in Flask session
- Use session_id for EVE API calls

**No Changes Required:**
- ใช้ session management ที่มีอยู่แล้ว
- `/api/branches` endpoint จะใช้ session_id เดียวกัน

## Testing Strategy

### Unit Tests

1. **Backend Tests** (`test_app.py`)
   - Test `/api/branches` endpoint
   - Mock EVE API response
   - Test error scenarios (invalid session, API error, timeout)
   - Verify response format

2. **Frontend Tests** (Manual/Browser Console)
   - Test `loadBranches()` function
   - Test dropdown population
   - Test localStorage save/load
   - Test branch selection change

### Integration Tests

1. **End-to-End Flow**
   - Login → Load branches → Select branch → Search → Verify correct BRANCH_ID used
   - Login → Load branches → Select branch → Generate report → Verify correct BRANCH_ID used

2. **Error Recovery**
   - Test with invalid session
   - Test with EVE API down
   - Test with slow network (timeout)
   - Verify fallback to default BRANCH_ID

### Manual Testing Checklist

- [ ] หน้าเว็บโหลดและแสดง dropdown สาขา
- [ ] เลือกสาขาและค้นหา Trade-In ได้
- [ ] รีเฟรชหน้าแล้วสาขาที่เลือกยังคงอยู่
- [ ] เปลี่ยนสาขาแล้วข้อมูลอัพเดท
- [ ] แสดง loading indicator ขณะโหลด
- [ ] แสดง error message เมื่อเกิดข้อผิดพลาด
- [ ] ใช้ค่า default (231) เมื่อไม่มีข้อมูลสาขา

## Performance Considerations

1. **Caching Strategy**
   - Cache รายการสาขาใน localStorage (optional)
   - TTL: 24 ชั่วโมง
   - Refresh เมื่อ user login ใหม่

2. **Loading Optimization**
   - โหลดรายการสาขาแบบ async (ไม่ block UI)
   - แสดง loading indicator
   - Timeout: 10 วินาที

3. **API Call Optimization**
   - เรียก `/api/branches` เพียงครั้งเดียวเมื่อโหลดหน้า
   - ไม่เรียกซ้ำเมื่อเปลี่ยนสาขา

## Security Considerations

1. **Session Validation**
   - ตรวจสอบ session_id ก่อนเรียก EVE API
   - Return 401 ถ้า session invalid

2. **Input Validation**
   - Validate BRANCH_ID format (ตัวเลขเท่านั้น)
   - Sanitize input ก่อนส่งไปยัง API

3. **Error Messages**
   - ไม่เปิดเผยข้อมูล sensitive ใน error message
   - Log detailed errors ที่ server-side เท่านั้น

## Deployment Notes

1. **No Database Changes Required**
   - ไม่ต้องแก้ไข schema
   - ไม่ต้อง migration

2. **Backward Compatibility**
   - ถ้าโหลดสาขาไม่สำเร็จ ใช้ค่า default (231)
   - ระบบยังทำงานได้ปกติ

3. **Rollback Plan**
   - ถ้ามีปัญหา สามารถ revert code กลับไปใช้ hardcode BRANCH_ID ได้ทันที
   - ไม่มี data migration ที่ต้อง rollback

## Future Enhancements

1. **Multi-Branch Selection**
   - รองรับการเลือกหลายสาขาพร้อมกัน
   - แสดงข้อมูลรวมจากหลายสาขา

2. **Branch Favorites**
   - บันทึกสาขาที่ใช้บ่อย
   - Quick select จากรายการโปรด

3. **Branch Search**
   - เพิ่ม search box ใน dropdown
   - กรองสาขาตามชื่อ

4. **Branch Analytics**
   - แสดงสถิติการใช้งานแต่ละสาขา
   - แนะนำสาขาที่ใช้บ่อย
