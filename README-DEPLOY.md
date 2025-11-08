# 🚀 Deploy ไปยัง Vercel (ฟรี!)

## ขั้นตอนการ Deploy

### 1. เตรียมโปรเจค
ตรวจสอบว่ามีไฟล์เหล่านี้:
- ✅ `app.py` - แอปพลิเคชัน Flask
- ✅ `vercel.json` - การตั้งค่า Vercel
- ✅ `requirements.txt` - Python dependencies
- ✅ `templates/` - HTML templates
- ✅ `extension/` - Browser extension files

### 2. สร้างบัญชี Vercel
1. ไปที่ https://vercel.com
2. Sign up ด้วย GitHub, GitLab, หรือ Bitbucket (ฟรี!)
3. ยืนยันอีเมล

### 3. Deploy ด้วย Vercel CLI (แนะนำ)

#### ติดตั้ง Vercel CLI:
```bash
npm install -g vercel
```

#### Login:
```bash
vercel login
```

#### Deploy:
```bash
vercel
```

ตอบคำถาม:
- Set up and deploy? `Y`
- Which scope? เลือก account ของคุณ
- Link to existing project? `N`
- What's your project's name? `trade-in-system` (หรือชื่อที่ต้องการ)
- In which directory is your code located? `./`
- Want to override the settings? `N`

#### Deploy Production:
```bash
vercel --prod
```

### 4. Deploy ผ่าน GitHub (ง่ายที่สุด)

1. **Push โค้ดขึ้น GitHub:**
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

2. **เชื่อมต่อกับ Vercel:**
   - ไปที่ https://vercel.com/dashboard
   - คลิก "Add New..." → "Project"
   - Import repository จาก GitHub
   - เลือก repository ของคุณ
   - คลิก "Deploy"

3. **เสร็จแล้ว!** Vercel จะ:
   - ติดตั้ง dependencies อัตโนมัติ
   - Build และ deploy
   - ให้ URL ฟรี เช่น `https://your-project.vercel.app`

### 5. การตั้งค่าเพิ่มเติม

#### Environment Variables (ถ้ามี):
1. ไปที่ Project Settings → Environment Variables
2. เพิ่มตัวแปรที่ต้องการ
3. Redeploy

#### Custom Domain (ฟรี!):
1. ไปที่ Project Settings → Domains
2. เพิ่ม domain ของคุณ
3. ตั้งค่า DNS ตามที่ Vercel แนะนำ

## 📝 หมายเหตุสำคัญ

### ข้อจำกัดของ Vercel Free Plan:
- ✅ Bandwidth: 100GB/เดือน
- ✅ Serverless Function Execution: 100GB-Hrs
- ✅ Builds: 6,000 นาที/เดือน
- ✅ Custom domains: ไม่จำกัด
- ⚠️ Serverless Functions timeout: 10 วินาที (Hobby), 60 วินาที (Pro)

### สำหรับโปรเจคนี้:
- ✅ เหมาะสำหรับใช้งานทั่วไป
- ✅ รองรับ API calls
- ⚠️ ถ้า API ตอบช้าเกิน 10 วินาที อาจต้องอัพเกรด Pro ($20/เดือน)

## 🔧 Troubleshooting

### ปัญหา: Build ล้มเหลว
```bash
# ตรวจสอบ Python version
vercel env add PYTHON_VERSION
# ใส่ค่า: 3.9
```

### ปัญหา: Import Error
ตรวจสอบว่า `requirements.txt` มีครบทุก package

### ปัญหา: 404 Not Found
ตรวจสอบ `vercel.json` ว่า routes ถูกต้อง

## 🎉 เสร็จแล้ว!

หลัง deploy สำเร็จ คุณจะได้:
- 🌐 URL สาธารณะ: `https://your-project.vercel.app`
- 🔄 Auto-deploy เมื่อ push ไป GitHub
- 📊 Analytics และ Logs
- 🚀 CDN ทั่วโลก

## 📚 เอกสารเพิ่มเติม
- Vercel Docs: https://vercel.com/docs
- Python on Vercel: https://vercel.com/docs/functions/serverless-functions/runtimes/python
