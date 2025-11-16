# 🔐 ระบบ Admin Authentication

## Quick Start

### 1. ติดตั้ง Dependencies

```bash
pip3 install psycopg2-binary python-dotenv
```

### 2. ตั้งค่า Environment Variables

แก้ไขไฟล์ `.env`:
```bash
# Database
POSTGRES_URL_NON_POOLING=your-database-url

# Session Secret (สร้างใหม่ด้วย: python3 -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY=your-secret-key-here
```

### 3. รัน Flask App

```bash
python3 app.py
```

ระบบจะสร้างตาราง `admin_users` และ admin user เริ่มต้นอัตโนมัติ

### 4. Login

เปิด http://localhost:5001/login

ใช้ข้อมูล Admin ที่ได้รับจากผู้ดูแลระบบ

## การจัดการ Admin Users

### ใช้ check_admin.py (แนะนำ)

```bash
python3 check_admin.py
```

เมนู:
1. แสดงรายการ Admin Users
2. ตรวจสอบรหัสผ่าน
3. รีเซ็ตรหัสผ่าน
4. สร้าง/อัพเดท Admin User
5. รีเซ็ต admin เป็นค่าเริ่มต้น (admin/admin123)

### คำสั่งด่วน

**ตรวจสอบรหัสผ่าน:**
```bash
python3 check_admin.py << EOF
2
your-username
your-password
EOF
```

**เปลี่ยนรหัสผ่าน:**
```bash
python3 check_admin.py << EOF
3
your-username
new-password
EOF
```

**สร้าง admin ใหม่:**
```bash
python3 check_admin.py << EOF
4
newadmin
newpassword
EOF
```

## ฟีเจอร์

✅ Login/Logout
✅ Session Management
✅ Password Hashing (SHA-256)
✅ Protected Routes
✅ Admin User Management
✅ Debug Logging

## โครงสร้างไฟล์

```
.
├── app.py                      # Flask app พร้อม authentication
├── check_admin.py              # เครื่องมือจัดการ admin users
├── test_login.py               # ทดสอบ login API
├── templates/
│   ├── login.html             # หน้า login
│   └── index.html             # หน้าหลัก (ต้อง login)
├── ADMIN_SETUP.md             # คู่มือการตั้งค่า
└── TROUBLESHOOTING_LOGIN.md   # แก้ปัญหา login

```

## Security Best Practices

1. **เปลี่ยนรหัสผ่านเริ่มต้น** ทันทีหลังติดตั้ง
2. **ใช้รหัสผ่านที่แข็งแรง** (12+ ตัวอักษร, ผสมตัวพิมพ์ใหญ่-เล็ก, ตัวเลข, สัญลักษณ์)
3. **เปลี่ยน SECRET_KEY** เป็นค่าที่ปลอดภัย
4. **ไม่แชร์ข้อมูล Login**
5. **ออกจากระบบ** เมื่อใช้งานเสร็จ
6. **ใช้ HTTPS** ใน production

## การแก้ปัญหา

หาก login ไม่ได้ ดูคู่มือที่ [TROUBLESHOOTING_LOGIN.md](TROUBLESHOOTING_LOGIN.md)

**แก้ไขด่วน:**
```bash
# ตรวจสอบรหัสผ่าน
python3 check_admin.py
# เลือก 2 (ตรวจสอบรหัสผ่าน)
```

## API Endpoints

### POST /login
Login เข้าสู่ระบบ

**Request:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "เข้าสู่ระบบสำเร็จ"
}
```

**Response (Failed):**
```json
{
  "success": false,
  "error": "Username หรือ Password ไม่ถูกต้อง"
}
```

### GET /logout
Logout ออกจากระบบ

**Response:** Redirect to /login

### GET /
หน้าหลัก (ต้อง login)

**Response:** 
- ถ้า login แล้ว: แสดงหน้า index.html
- ถ้ายัง: Redirect to /login

## Database Schema

```sql
CREATE TABLE admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## การทดสอบ

### ทดสอบ Login API
```bash
python3 test_login.py
```

### ทดสอบด้วย curl
```bash
curl -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

## Production Deployment

### Vercel

1. เพิ่ม Environment Variables ใน Vercel Dashboard:
   - `POSTGRES_URL_NON_POOLING`
   - `SECRET_KEY`

2. Deploy:
```bash
vercel --prod
```

### Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV FLASK_ENV=production
CMD ["gunicorn", "-b", "0.0.0.0:5001", "app:app"]
```

## License

MIT
