# 🤖 ตั้งค่า Telegram Bot สำหรับส่งรายงานอัตโนมัติ

## ขั้นตอนที่ 1: สร้าง Telegram Bot

1. เปิด Telegram แล้วค้นหา **@BotFather**
2. พิมพ์ `/newbot`
3. ตั้งชื่อ bot (เช่น "Trade-In Report Bot")
4. ตั้ง username (ต้องลงท้ายด้วย "bot" เช่น "tradein_report_bot")
5. จะได้ **Bot Token** แบบนี้:
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
6. **เก็บ Token ไว้ให้ดี!**

## ขั้นตอนที่ 2: หา Chat ID

### วิธีที่ 1: ใช้ Bot
1. ค้นหา bot ที่สร้างใน Telegram (ใช้ username ที่ตั้งไว้)
2. กด **Start** หรือพิมพ์ `/start`
3. เปิด browser ไปที่:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   (แทน `<YOUR_BOT_TOKEN>` ด้วย Token ที่ได้)
4. จะเห็น JSON แบบนี้:
   ```json
   {
     "ok": true,
     "result": [{
       "message": {
         "chat": {
           "id": 123456789,  ← นี่คือ Chat ID
           "first_name": "Your Name"
         }
       }
     }]
   }
   ```
5. **เก็บ Chat ID ไว้!**

### วิธีที่ 2: ใช้ @userinfobot
1. ค้นหา **@userinfobot** ใน Telegram
2. กด Start
3. จะได้ Chat ID ทันที

## ขั้นตอนที่ 3: ตั้งค่าในระบบ

### เพิ่มการตั้งค่า Telegram ใน localStorage

เปิด Browser Console (F12) ในหน้าระบบ Trade-In แล้วพิมพ์:

```javascript
// บันทึก Bot Token
localStorage.setItem('telegramBotToken', 'YOUR_BOT_TOKEN_HERE');

// บันทึก Chat ID
localStorage.setItem('telegramChatId', 'YOUR_CHAT_ID_HERE');

// ตั้งเวลาส่งรายงาน (เช่น 18:00)
localStorage.setItem('telegramReportTime', '18:00');

// เปิดใช้งานการส่งอัตโนมัติ
localStorage.setItem('telegramAutoSend', 'true');
```

## ขั้นตอนที่ 4: ทดสอบส่งรายงาน

1. ไปที่หน้า "📈 รายงานยอดเทรด"
2. เลือกวันที่และสร้างรายงาน
3. คลิกปุ่ม "📤 ส่งไป Telegram"
4. ตรวจสอบ Telegram ว่าได้รับข้อความหรือไม่

## ขั้นตอนที่ 5: ตั้งค่าส่งอัตโนมัติ (ทุกวัน)

### ใช้ Cron Job (สำหรับ Linux/Mac)

สร้างไฟล์ `send_daily_report.sh`:

```bash
#!/bin/bash

# ตั้งค่า
API_URL="http://localhost:5000/api/report"
TELEGRAM_API="http://localhost:5000/api/send-telegram"
BOT_TOKEN="YOUR_BOT_TOKEN"
CHAT_ID="YOUR_CHAT_ID"

# วันที่วันนี้
DATE=$(date +%Y-%m-%d)

# ดึงรายงาน
REPORT=$(curl -s "$API_URL?dateStart=$DATE&dateEnd=$DATE&customerSign=")

# ส่งไป Telegram
curl -X POST "$TELEGRAM_API" \
  -H "Content-Type: application/json" \
  -d "{
    \"botToken\": \"$BOT_TOKEN\",
    \"chatId\": \"$CHAT_ID\",
    \"message\": \"$REPORT\"
  }"
```

ตั้ง Cron Job (ส่งทุกวัน 18:00):
```bash
crontab -e
```

เพิ่มบรรทัดนี้:
```
0 18 * * * /path/to/send_daily_report.sh
```

### ใช้ Task Scheduler (สำหรับ Windows)

1. เปิด Task Scheduler
2. Create Basic Task
3. ตั้งชื่อ "Send Trade-In Report"
4. Trigger: Daily เวลา 18:00
5. Action: Start a program
6. Program: `python`
7. Arguments: `/path/to/send_report.py`

สร้างไฟล์ `send_report.py`:

```python
import requests
from datetime import datetime

# ตั้งค่า
API_URL = "http://localhost:5000/api/report"
TELEGRAM_API = "http://localhost:5000/api/send-telegram"
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# วันที่วันนี้
today = datetime.now().strftime("%Y-%m-%d")

# ดึงรายงาน
response = requests.get(f"{API_URL}?dateStart={today}&dateEnd={today}&customerSign=")
report_data = response.json()

# สร้างข้อความ
message = f"""📊 รายงานยอดเทรด
📅 วันที่: {today}
━━━━━━━━━━━━

📈 สรุปภาพรวม
• รายการทั้งหมด: {report_data['report']['totalCount']} รายการ
• ลูกค้าตกลง: {report_data['report']['confirmedCount']} รายการ
• ลูกค้าไม่ตกลง: {report_data['report']['notConfirmedCount']} รายการ

👤 สรุปตามพนักงาน
"""

# เพิ่มข้อมูลพนักงาน
for sale_code, info in report_data['report']['salesSummary'].items():
    confirmed = info['confirmedCount']
    total = info['count']
    not_confirmed = total - confirmed
    message += f"{sale_code}: {total} รายการ (✅{confirmed} ❌{not_confirmed})\n"

message += "━━━━━━━━━━━━"

# ส่งไป Telegram
requests.post(TELEGRAM_API, json={
    "botToken": BOT_TOKEN,
    "chatId": CHAT_ID,
    "message": message
})

print("✅ ส่งรายงานสำเร็จ!")
```

## 🎯 สรุป

หลังจากตั้งค่าเสร็จแล้ว:
- ✅ ส่งรายงานด้วยตัวเอง: คลิกปุ่ม "📤 ส่งไป Telegram"
- ✅ ส่งอัตโนมัติทุกวัน: ใช้ Cron Job หรือ Task Scheduler
- ✅ ได้รับรายงานใน Telegram ทุกวันเวลา 18:00

## 🔧 Troubleshooting

### ส่งไม่สำเร็จ
- ตรวจสอบ Bot Token ถูกต้องหรือไม่
- ตรวจสอบ Chat ID ถูกต้องหรือไม่
- ตรวจสอบว่ากด Start bot แล้วหรือยัง

### ไม่ได้รับข้อความ
- ตรวจสอบว่า bot ไม่ถูก block
- ลองส่งข้อความไปหา bot ก่อน
- ตรวจสอบ Chat ID อีกครั้ง

## 📚 เอกสารเพิ่มเติม
- Telegram Bot API: https://core.telegram.org/bots/api
- BotFather Commands: https://core.telegram.org/bots#6-botfather
