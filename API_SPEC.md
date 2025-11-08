# Trade-In Management System - API Specification

## ภาพรวมระบบ

ระบบจัดการข้อมูล Trade-In ที่ทำงานเป็น Proxy API ระหว่าง Web Application กับ API ของ eve.techswop.com โดยใช้ Session ID จาก Chrome Extension สำหรับ Authentication

**Base URL:** `http://localhost:5000`

**Technology Stack:**
- Backend: Flask (Python)
- Frontend: HTML, JavaScript, Bootstrap
- Authentication: Session-based via Chrome Extension

---

## 1. Web Pages

### 1.1 หน้าแรก (Dashboard)
```
GET /
```

**Response:** HTML Page
- แสดงตารางข้อมูล Trade-In
- ฟอร์มค้นหาและกรอง
- ฟังก์ชันยกเลิกรายการ (Bulk Cancel)

---

### 1.2 หน้าติดตั้ง Extension
```
GET /install-extension
```

**Response:** HTML Page
- คู่มือการติดตั้ง Chrome Extension
- ลิงก์ดาวน์โหลด Extension

---

### 1.3 ดาวน์โหลด Extension
```
GET /download-extension
```

**Response:** ZIP File
- ไฟล์ `trade-in-extension.zip`
- ประกอบด้วย Extension files (ไม่รวม .py)

---

## 2. API Endpoints

### 2.1 ดึงข้อมูล Trade-In

```
GET /api/data
```

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| start | integer | No | 0 | เริ่มต้นที่แถวที่ (pagination) |
| length | integer | No | 100 | จำนวนแถวที่ต้องการ |
| dateStart | string | No | เมื่อวาน | วันที่เริ่มต้น (dd/mm/yyyy) |
| dateEnd | string | No | วันนี้ | วันที่สิ้นสุด (dd/mm/yyyy) |
| saleCode | string | No | "" | รหัสพนักงานขาย |
| status | string | No | "" | สถานะรายการ |
| brand | string | No | "" | ยี่ห้อสินค้า |
| series | string | No | "" | รุ่นสินค้า |
| docRefNumber | string | No | "" | เลขที่เอกสารอ้างอิง |
| promoCode | string | No | "" | รหัสโปรโมชั่น |
| customerSign | string | No | "0" | ลูกค้าเซ็นแล้ว (0=ทั้งหมด, 1=เซ็นแล้ว) |

**Response Success (200):**
```json
{
  "data": [
    {
      "trade_in_id": "12345",
      "document_no": "TI2024001",
      "document_date": "22/10/2024",
      "IS_SIGNED": "Y",
      "SIGN_DATE": "22/10/2024 10:30",
      "series": "iPhone 15 Pro",
      "brand_name": "Apple",
      "category_name": "Smartphone",
      "part_number": "MTUX3TH/A",
      "amount": 35000,
      "COUPON_TRADE_IN_CODE": "TI2024001",
      "invoice_no": "INV2024001",
      "CAMPAIGN_ON_TOP_NAME": "Trade-In Campaign",
      "COUPON_ON_TOP_BRAND_CODE": "BRAND001",
      "COUPON_ON_TOP_BRAND_PRICE": 1000,
      "COUPON_ON_TOP_COMPANY_CODE": "COMP001",
      "COUPON_ON_TOP_COMPANY_PRICE": 500,
      "customer_name": "สมชาย ใจดี",
      "customer_phone_number": "0812345678",
      "customer_email": "somchai@email.com",
      "buyer_name": "สมหญิง รับซื้อ",
      "SALE_CODE": "S001",
      "SALE_NAME": "พนักงานขาย A",
      "DOCUMENT_REF_1": "REF001",
      "BIDDING_STATUS_NAME": "อนุมัติแล้ว",
      "CHANGE_REQUEST_COUNT": 0
    }
  ],
  "recordsTotal": 150,
  "recordsFiltered": 150
}
```

**Response Error:**
```json
{
  "error": "Error message"
}
```

**ใช้งาน:**
- แสดงรายการ Trade-In ในตาราง
- รองรับการค้นหาและกรองข้อมูล
- รองรับ Pagination

---

### 2.2 ตรวจสอบว่ายกเลิกได้หรือไม่

```
POST /api/check-cancel
```

**Request Body:**
```json
{
  "tradeInId": "12345",
  "cookies": {
    "ASP.NET_SessionId": "xxx",
    ".ASPXAUTH": "xxx"
  }
}
```

**Response Success (200):**
```json
{
  "d": {
    "is_success": true,
    "allow_cancel": true,
    "message": ["สามารถยกเลิกได้"]
  }
}
```

**Response Error:**
```json
{
  "d": {
    "is_success": false,
    "message": ["ไม่สามารถยกเลิกได้ เนื่องจาก..."]
  }
}
```

**ใช้งาน:**
- ตรวจสอบก่อนยกเลิกรายการ
- ป้องกันการยกเลิกรายการที่ไม่สามารถยกเลิกได้

---

### 2.3 ยกเลิกรายการเดี่ยว

```
POST /api/cancel-data
```

**Request Body:**
```json
{
  "payload": {
    "param": {
      "TRADE_IN_ID": "12345",
      "EMP_CODE": "E001",
      "EMP_FULL_NAME": "พนักงาน ทดสอบ",
      "EMP_PHONE_NUMBER": "0812345678",
      "REASON": "ยกเลิกจากระบบ",
      "CANCEL_STATUS": "1",
      "REASON_CANCEL": "3",
      "DESCRIPTION": "ลูกค้าขอยกเลิก"
    }
  },
  "cookies": {
    "ASP.NET_SessionId": "xxx",
    ".ASPXAUTH": "xxx"
  }
}
```

**Field Descriptions:**

| Field | Type | Description | Values |
|-------|------|-------------|--------|
| TRADE_IN_ID | string | รหัสรายการ Trade-In | - |
| EMP_CODE | string | รหัสพนักงาน | - |
| EMP_FULL_NAME | string | ชื่อพนักงาน | - |
| EMP_PHONE_NUMBER | string | เบอร์โทรพนักงาน | - |
| REASON | string | เหตุผลการยกเลิก | - |
| CANCEL_STATUS | string | ประเภทการยกเลิก | 1=โดนยกเลิกจากผู้ขาย, 2=อื่นๆ |
| REASON_CANCEL | string | สาเหตุการยกเลิก | 1=ลูกค้าเปลี่ยนใจ, 2=ราคาไม่ตรง, 3=อื่นๆ |
| DESCRIPTION | string | รายละเอียดเพิ่มเติม | - |

**Response Success (200):**
```json
{
  "d": {
    "is_success": true,
    "message": ["ยกเลิกสำเร็จ"]
  }
}
```

**Response Error:**
```json
{
  "d": {
    "is_success": false,
    "message": ["ยกเลิกไม่สำเร็จ เนื่องจาก..."]
  }
}
```

---

### 2.4 ยกเลิกหลายรายการพร้อมกัน (Bulk Cancel)

```
POST /api/cancel
```

**Request Body:**
```json
{
  "tradeInIds": ["12345", "12346", "12347"],
  "cancelInfo": {
    "empCode": "E001",
    "empName": "พนักงาน ทดสอบ",
    "empPhone": "0812345678",
    "reason": "ยกเลิกจากระบบ",
    "reasonCancel": "3",
    "cancelType": "1",
    "description": "ยกเลิกหลายรายการ"
  }
}
```

**Response Success (200):**
```json
{
  "success": true,
  "successCount": 3,
  "failedCount": 0,
  "message": "ยกเลิกสำเร็จ 3 รายการ",
  "errors": []
}
```

**Response Partial Success:**
```json
{
  "success": true,
  "successCount": 2,
  "failedCount": 1,
  "message": "ยกเลิกสำเร็จ 2 รายการ, ล้มเหลว 1 รายการ",
  "errors": [
    "ID 12347: ไม่สามารถยกเลิกได้ เนื่องจากมีการเปลี่ยนแปลงสถานะ"
  ]
}
```

**Response Error:**
```json
{
  "success": false,
  "successCount": 0,
  "failedCount": 3,
  "error": "ยกเลิกล้มเหลวทั้งหมด 3 รายการ",
  "errors": [
    "ID 12345: ไม่สามารถยกเลิกได้",
    "ID 12346: Session หมดอายุ",
    "ID 12347: ไม่พบรายการ"
  ]
}
```

**ใช้งาน:**
- ยกเลิกหลายรายการพร้อมกัน
- ตรวจสอบแต่ละรายการก่อนยกเลิก
- รายงานผลการยกเลิกแต่ละรายการ

---

### 2.5 ดึง Cookies

```
GET /api/get-cookies
```

**Headers Required:**
```
Cookie: ASP.NET_SessionId=xxx; .ASPXAUTH=xxx
```

**Response Success (200):**
```json
{
  "cookies": {
    "ASP.NET_SessionId": "xxx",
    ".ASPXAUTH": "xxx"
  }
}
```

**ใช้งาน:**
- ดึง cookies จาก request header
- ใช้สำหรับ debugging

---

## 3. External API (eve.techswop.com)

### 3.1 ดึงข้อมูล Trade-In

```
POST https://eve.techswop.com/ti/index.aspx/Getdata
```

**Headers:**
```
Accept: application/json, text/javascript, */*; q=0.01
Content-Type: application/json; charset=utf-8
Origin: https://eve.techswop.com
Referer: https://eve.techswop.com/ti/index.aspx
X-Requested-With: XMLHttpRequest
Cookie: ASP.NET_SessionId=xxx
```

**Request Body:** (DataTables format)
```json
{
  "draw": 1,
  "columns": [...],
  "order": [],
  "start": 0,
  "length": 50,
  "search": {"value": "", "regex": false},
  "textdateStart": "21/10/2024",
  "textdateEnd": "22/10/2024",
  "status": "",
  "series": [],
  "brands": [],
  "saleCode": "",
  "branchID": "231",
  "txtSearchRef1": "",
  "txtSearchCOTN": "",
  "customerSign": "0"
}
```

---

### 3.2 ตรวจสอบการยกเลิก

```
POST https://eve.techswop.com/ti/index.aspx/CheckAllowCancel
```

**Request Body:**
```json
{
  "trade_in_id": 12345
}
```

---

### 3.3 ยกเลิกรายการ

```
POST https://eve.techswop.com/ti/index.aspx/CancelData
```

**Request Body:**
```json
{
  "param": {
    "TRADE_IN_ID": "12345",
    "EMP_CODE": "E001",
    "EMP_FULL_NAME": "พนักงาน ทดสอบ",
    "EMP_PHONE_NUMBER": "0812345678",
    "REASON": "ยกเลิกจากระบบ",
    "CANCEL_STATUS": "1",
    "REASON_CANCEL": "3",
    "DESCRIPTION": "-"
  }
}
```

---

## 4. Authentication Flow

### 4.1 Chrome Extension
1. ผู้ใช้ login ที่ eve.techswop.com
2. Extension ดึง Session ID จาก cookies
3. Extension ส่ง Session ID ไปยัง Web App
4. Web App บันทึก Session ID ใน localStorage

### 4.2 API Calls
1. Web App ดึง Session ID จาก localStorage
2. ส่ง Session ID ใน cookies header
3. Backend proxy request ไปยัง eve.techswop.com
4. ส่ง response กลับมายัง Web App

---

## 5. Error Handling

### 5.1 HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - ข้อมูลไม่ถูกต้อง |
| 401 | Unauthorized - Session หมดอายุ |
| 403 | Forbidden - ไม่มีสิทธิ์เข้าถึง |
| 404 | Not Found - ไม่พบข้อมูล |
| 500 | Internal Server Error |

### 5.2 Error Response Format

```json
{
  "error": "Error message",
  "details": "Detailed error information"
}
```

---

## 6. Data Models

### 6.1 Trade-In Record

```typescript
interface TradeInRecord {
  trade_in_id: string;
  document_no: string;
  document_date: string;
  IS_SIGNED: string;
  SIGN_DATE: string;
  series: string;
  brand_name: string;
  category_name: string;
  part_number: string;
  amount: number;
  COUPON_TRADE_IN_CODE: string;
  invoice_no: string;
  CAMPAIGN_ON_TOP_NAME: string;
  COUPON_ON_TOP_BRAND_CODE: string;
  COUPON_ON_TOP_BRAND_PRICE: number;
  COUPON_ON_TOP_COMPANY_CODE: string;
  COUPON_ON_TOP_COMPANY_PRICE: number;
  customer_name: string;
  customer_phone_number: string;
  customer_email: string;
  buyer_name: string;
  SALE_CODE: string;
  SALE_NAME: string;
  DOCUMENT_REF_1: string;
  BIDDING_STATUS_NAME: string;
  CHANGE_REQUEST_COUNT: number;
}
```

### 6.2 Cancel Info

```typescript
interface CancelInfo {
  empCode: string;
  empName: string;
  empPhone: string;
  reason: string;
  reasonCancel: "1" | "2" | "3"; // 1=ลูกค้าเปลี่ยนใจ, 2=ราคาไม่ตรง, 3=อื่นๆ
  cancelType: "1" | "2"; // 1=โดนยกเลิกจากผู้ขาย, 2=อื่นๆ
  description: string;
}
```

---

## 7. Configuration

### 7.1 Environment Variables

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=True

# Server Configuration
HOST=0.0.0.0
PORT=5000

# API Configuration
API_URL=https://eve.techswop.com/ti/index.aspx/Getdata
BRANCH_ID=231
```

### 7.2 Constants

```python
API_URL = "https://eve.techswop.com/ti/index.aspx/Getdata"
BRANCH_ID = "231"
```

---

## 8. Usage Examples

### 8.1 ดึงข้อมูล Trade-In (JavaScript)

```javascript
async function fetchTradeInData(filters = {}) {
  const params = new URLSearchParams({
    start: 0,
    length: 100,
    dateStart: filters.dateStart || '',
    dateEnd: filters.dateEnd || '',
    saleCode: filters.saleCode || '',
    ...filters
  });
  
  const response = await fetch(`/api/data?${params}`);
  const data = await response.json();
  
  if (data.error) {
    throw new Error(data.error);
  }
  
  return data;
}
```

### 8.2 ยกเลิกหลายรายการ (JavaScript)

```javascript
async function bulkCancelOrders(tradeInIds, cancelInfo) {
  const response = await fetch('/api/cancel', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      tradeInIds,
      cancelInfo
    })
  });
  
  const result = await response.json();
  
  if (!result.success) {
    throw new Error(result.error);
  }
  
  return result;
}

// ใช้งาน
const result = await bulkCancelOrders(
  ['12345', '12346', '12347'],
  {
    empCode: 'E001',
    empName: 'พนักงาน ทดสอบ',
    empPhone: '0812345678',
    reason: 'ยกเลิกจากระบบ',
    reasonCancel: '3',
    cancelType: '1',
    description: 'ยกเลิกหลายรายการ'
  }
);

console.log(`ยกเลิกสำเร็จ ${result.successCount} รายการ`);
```

### 8.3 ดึงข้อมูลด้วย Python

```python
import requests

def get_trade_in_data(filters=None):
    url = "http://localhost:5000/api/data"
    params = {
        'start': 0,
        'length': 100,
        **(filters or {})
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    return response.json()

# ใช้งาน
data = get_trade_in_data({
    'dateStart': '21/10/2024',
    'dateEnd': '22/10/2024',
    'saleCode': 'S001'
})

print(f"พบข้อมูล {len(data['data'])} รายการ")
```

---

## 9. Testing

### 9.1 Test API Endpoints

```bash
# ดึงข้อมูล
curl "http://localhost:5000/api/data?length=10"

# ยกเลิกรายการ
curl -X POST http://localhost:5000/api/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "tradeInIds": ["12345"],
    "cancelInfo": {
      "empCode": "E001",
      "empName": "Test",
      "empPhone": "0812345678",
      "reason": "Test",
      "reasonCancel": "3",
      "cancelType": "1",
      "description": "Test"
    }
  }'
```

---

## 10. Security Considerations

1. **Session Management**
   - Session ID ต้องเก็บใน localStorage
   - ตรวจสอบ Session หมดอายุ
   - ไม่ส่ง Session ID ใน URL

2. **CORS**
   - จำกัด Origin ที่อนุญาต
   - ตรวจสอบ Referer header

3. **Input Validation**
   - Validate ข้อมูลทุก input
   - Sanitize ข้อมูลก่อนส่งไปยัง API

4. **Rate Limiting**
   - จำกัดจำนวน request ต่อนาที
   - ป้องกัน DDoS

---

## 11. Deployment

### 11.1 Production Configuration

```python
# config.py
import os

class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
```

### 11.2 Run Production Server

```bash
# ใช้ Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# หรือใช้ uWSGI
uwsgi --http 0.0.0.0:5000 --wsgi-file app.py --callable app --processes 4
```

---

## 12. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 22/10/2024 | Initial release |

---

## 13. Support

สำหรับคำถามหรือปัญหา กรุณาติดต่อ:
- Email: support@example.com
- GitHub Issues: https://github.com/your-repo/issues
