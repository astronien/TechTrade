# แอปพลิเคชันดึงข้อมูลจาก API

แอปพลิเคชัน Python Flask สำหรับดึงข้อมูลจาก API และแสดงผลในหน้าเว็บ

## การติดตั้ง

1. ติดตั้ง dependencies:
```bash
pip install -r requirements.txt
```

## การใช้งาน

1. รันแอปพลิเคชัน:
```bash
python app.py
```

2. เปิดเบราว์เซอร์และไปที่:
```
http://localhost:5000
```

3. กดปุ่ม "โหลดข้อมูล" เพื่อดึงข้อมูลจาก API

## คุณสมบัติ

- ✅ ดึงข้อมูลจาก API อัตโนมัติ
- ✅ แสดงข้อมูลในรูปแบบ JSON
- ✅ แสดงข้อมูลในรูปแบบตาราง (ถ้าเป็น array)
- ✅ รีเฟรชข้อมูลได้
- ✅ UI สวยงาม responsive

## โครงสร้างไฟล์

```
.
├── app.py              # แอปพลิเคชันหลัก Flask
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html     # หน้าเว็บแสดงผล
└── README.md          # เอกสารนี้
```
