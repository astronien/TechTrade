# วิธี Import Environment Variables เข้า Vercel

## วิธีที่ 1: Import จากไฟล์ .env (แนะนำ)

### ขั้นตอน:

1. **เข้า Vercel Dashboard**
   - ไปที่ https://vercel.com/dashboard
   - เลือก Project ของคุณ

2. **ไปที่ Settings → Environment Variables**
   - คลิก "Add New"
   - เลือก "Import from .env"

3. **Upload ไฟล์ .env**
   - เลือกไฟล์ `.env` ที่สร้างไว้
   - หรือ copy-paste เนื้อหาจากไฟล์

4. **เลือก Environment**
   - Production ✅
   - Preview ✅
   - Development ✅

5. **Save**

## วิธีที่ 2: ใช้ Vercel CLI

### ติดตั้ง Vercel CLI:
```bash
npm install -g vercel
```

### Login:
```bash
vercel login
```

### Import Environment Variables:
```bash
vercel env pull .env.local
```

### หรือ Push จากไฟล์ .env:
```bash
# Production
vercel env add POSTGRES_URL_NON_POOLING production < .env

# หรือทีละตัว
vercel env add POSTGRES_URL_NON_POOLING production
# แล้ววางค่าเมื่อถูกถาม
```

## วิธีที่ 3: Copy-Paste ทีละตัว

### ไปที่ Vercel Dashboard → Settings → Environment Variables

เพิ่มทีละตัว:

```
Key: POSTGRES_URL_NON_POOLING
Value: postgres://postgres.wnbcuztmbvchsgifpxau:spGylXEj6seFU6GO@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
Environment: Production, Preview, Development
```

```
Key: SUPABASE_URL
Value: https://wnbcuztmbvchsgifpxau.supabase.co
Environment: Production, Preview, Development
```

```
Key: SUPABASE_ANON_KEY
Value: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InduYmN1enRtYnZjaHNnaWZweGF1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxMjc2MzIsImV4cCI6MjA3ODcwMzYzMn0.209KN8SaUyrKIg3xnI5bHz_VB_1Mex4WySXVYXZGXj0
Environment: Production, Preview, Development
```

## ตัวแปรที่จำเป็น (Required):

✅ **POSTGRES_URL_NON_POOLING** - สำหรับเชื่อมต่อ Supabase (สำคัญที่สุด!)

## ตัวแปรเสริม (Optional):

- SUPABASE_URL
- SUPABASE_ANON_KEY
- LINE_CHANNEL_ACCESS_TOKEN (ถ้าใช้ LINE Bot)

## หลังจาก Import แล้ว:

1. **Redeploy Project:**
   ```bash
   git push
   ```
   หรือ
   - Vercel Dashboard → Deployments → Redeploy

2. **ตรวจสอบว่า Environment Variables ถูกโหลด:**
   - Vercel Dashboard → Settings → Environment Variables
   - ควรเห็นตัวแปรทั้งหมด

3. **ทดสอบ:**
   - เข้าเว็บไซต์
   - สร้าง Zone ใหม่
   - ตรวจสอบว่าบันทึกสำเร็จ

## Troubleshooting:

### ถ้า Environment Variables ไม่ทำงาน:

1. ตรวจสอบว่าเลือก Environment ถูกต้อง (Production, Preview, Development)
2. Redeploy project ใหม่
3. ดู Runtime Logs ใน Vercel Dashboard

### ถ้ายังได้ 500 Error:

1. ตรวจสอบ Vercel Logs:
   - Deployments → Latest → Runtime Logs
   
2. ตรวจสอบว่า `POSTGRES_URL_NON_POOLING` ถูกต้อง:
   - ต้องมี `?sslmode=require` ท้ายสุด
   - ต้องใช้ port 5432 (ไม่ใช่ 6543)

## ความปลอดภัย:

⚠️ **อย่า commit ไฟล์ .env เข้า Git!**
- ไฟล์ `.env` อยู่ใน `.gitignore` แล้ว
- ใช้เฉพาะสำหรับ import เข้า Vercel
- ลบออกจากเครื่องหลังจาก import แล้ว (ถ้าต้องการ)

✅ **ใช้ .env.example สำหรับ documentation**
- Commit `.env.example` เข้า Git ได้
- ไม่มีค่าจริง มีแค่ตัวอย่าง
