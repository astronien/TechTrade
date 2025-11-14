# Setup Supabase สำหรับ Custom Zones

## ขั้นตอนการตั้งค่า

### 1. ตั้งค่า Environment Variables ใน Vercel

ไปที่ Vercel Dashboard → Project Settings → Environment Variables

เพิ่ม variable นี้:

```
POSTGRES_URL_NON_POOLING=postgres://postgres.wnbcuztmbvchsgifpxau:spGylXEj6seFU6GO@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

### 2. Deploy Code ใหม่

```bash
git add .
git commit -m "Add Supabase integration"
git push
```

Vercel จะ deploy อัตโนมัติ

### 3. ตรวจสอบ Database

เข้า Supabase Dashboard → SQL Editor

รันคำสั่งนี้เพื่อดูตาราง:

```sql
SELECT * FROM custom_zones;
```

### 4. ทดสอบ

1. เข้าเว็บไซต์
2. ไปที่เมนู "🗺️ จัดการ Zone"
3. สร้าง Zone ใหม่
4. ตรวจสอบใน Supabase ว่ามีข้อมูลหรือไม่

## โครงสร้างตาราง

```sql
CREATE TABLE custom_zones (
    id SERIAL PRIMARY KEY,
    zone_id VARCHAR(255) UNIQUE NOT NULL,
    zone_name VARCHAR(255) NOT NULL,
    branch_ids JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Troubleshooting

### ถ้าได้ 500 Error:

1. ตรวจสอบ Vercel Logs:
   - Vercel Dashboard → Deployments → Latest → Runtime Logs

2. ตรวจสอบว่า Environment Variable ถูกต้อง:
   - ต้องใช้ `POSTGRES_URL_NON_POOLING` (ไม่ใช่ `POSTGRES_URL`)

3. ตรวจสอบว่า psycopg2-binary ติดตั้งแล้ว:
   - ดูใน `requirements.txt`

### ถ้าตารางไม่ถูกสร้าง:

รันคำสั่งนี้ใน Supabase SQL Editor:

```sql
CREATE TABLE IF NOT EXISTS custom_zones (
    id SERIAL PRIMARY KEY,
    zone_id VARCHAR(255) UNIQUE NOT NULL,
    zone_name VARCHAR(255) NOT NULL,
    branch_ids JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## ข้อดีของการใช้ Supabase

✅ ข้อมูลไม่หาย (เก็บถาวร)
✅ ทุกคนเห็นข้อมูลเดียวกัน
✅ ทำงานบน Vercel ได้
✅ มี UI สำหรับจัดการข้อมูล
✅ Backup อัตโนมัติ
