# 🔐 คู่มือการใช้งานระบบ Admin

## ข้อมูล Admin เริ่มต้น

เมื่อติดตั้งระบบครั้งแรก จะมี Admin User เริ่มต้นให้ใช้งาน:

- **Username:** `admin`
- **Password:** `admin123`

## การเข้าสู่ระบบ

1. เปิดเว็บไซต์ที่ URL ของคุณ
2. ระบบจะ redirect ไปหน้า Login อัตโนมัติ
3. กรอก Username และ Password
4. คลิก "เข้าสู่ระบบ"

## การออกจากระบบ

คลิกปุ่ม "🚪 ออกจากระบบ" ที่ด้านล่างของเมนูด้านซ้าย

## การเปลี่ยนรหัสผ่าน

### วิธีที่ 1: ใช้ Python Script

```python
import psycopg2
import hashlib
import os

# เชื่อมต่อ database
db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# เปลี่ยนรหัสผ่าน
username = 'admin'
new_password = 'your-new-password'
password_hash = hashlib.sha256(new_password.encode()).hexdigest()

cur.execute("""
    UPDATE admin_users 
    SET password_hash = %s 
    WHERE username = %s
""", (password_hash, username))

conn.commit()
cur.close()
conn.close()

print(f"✅ เปลี่ยนรหัสผ่านสำหรับ {username} สำเร็จ")
```

### วิธีที่ 2: ใช้ SQL โดยตรง (Supabase Dashboard)

1. เข้า Supabase Dashboard
2. ไปที่ SQL Editor
3. รันคำสั่ง:

```sql
UPDATE admin_users 
SET password_hash = encode(digest('your-new-password', 'sha256'), 'hex')
WHERE username = 'admin';
```

## การเพิ่ม Admin User ใหม่

### วิธีที่ 1: ใช้ Python Script

```python
import psycopg2
import hashlib
import os

db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

username = 'newadmin'
password = 'newpassword'
password_hash = hashlib.sha256(password.encode()).hexdigest()

cur.execute("""
    INSERT INTO admin_users (username, password_hash)
    VALUES (%s, %s)
""", (username, password_hash))

conn.commit()
cur.close()
conn.close()

print(f"✅ สร้าง admin user {username} สำเร็จ")
```

### วิธีที่ 2: ใช้ SQL โดยตรง

```sql
INSERT INTO admin_users (username, password_hash)
VALUES ('newadmin', encode(digest('newpassword', 'sha256'), 'hex'));
```

## โครงสร้างตาราง admin_users

```sql
CREATE TABLE admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## การรีเซ็ตรหัสผ่าน Admin

หากลืมรหัสผ่าน สามารถรีเซ็ตกลับเป็นค่าเริ่มต้นได้:

```sql
UPDATE admin_users 
SET password_hash = encode(digest('admin123', 'sha256'), 'hex')
WHERE username = 'admin';
```

## Security Best Practices

1. **เปลี่ยนรหัสผ่านเริ่มต้น** ทันทีหลังติดตั้งระบบ
2. **ใช้รหัสผ่านที่แข็งแรง** อย่างน้อย 12 ตัวอักษร ผสมตัวพิมพ์ใหญ่-เล็ก ตัวเลข และสัญลักษณ์
3. **เปลี่ยน SECRET_KEY** ใน `.env` เป็นค่าที่ปลอดภัย
4. **ไม่แชร์ข้อมูล Login** กับผู้อื่น
5. **ออกจากระบบ** เมื่อใช้งานเสร็จ

## การตั้งค่า SECRET_KEY

แก้ไขไฟล์ `.env`:

```bash
SECRET_KEY=your-very-long-random-secret-key-here
```

สร้าง SECRET_KEY แบบสุ่ม:

```python
import secrets
print(secrets.token_hex(32))
```

## Troubleshooting

### ไม่สามารถ Login ได้

1. ตรวจสอบว่า database เชื่อมต่อได้
2. ตรวจสอบว่ามีตาราง `admin_users` แล้ว
3. ลองรีเซ็ตรหัสผ่านกลับเป็นค่าเริ่มต้น

### Session หมดอายุเร็วเกินไป

แก้ไขใน `app.py`:

```python
from datetime import timedelta

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
```

### ต้องการเพิ่มฟีเจอร์ "จำฉันไว้"

เพิ่มใน login route:

```python
session.permanent = True
```
