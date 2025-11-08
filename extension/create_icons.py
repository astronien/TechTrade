from PIL import Image, ImageDraw, ImageFont

def create_icon(size, filename):
    # สร้างภาพพื้นหลังสีม่วง
    img = Image.new('RGB', (size, size), color='#667eea')
    draw = ImageDraw.Draw(img)
    
    # วาดวงกลมสีขาว
    margin = size // 6
    draw.ellipse([margin, margin, size-margin, size-margin], fill='white')
    
    # วาดข้อความ (emoji หรือตัวอักษร)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", size//2)
        draw.text((size//2, size//2), "🍪", font=font, anchor="mm", fill='#667eea')
    except:
        # ถ้าไม่มี emoji font ใช้ตัวอักษรธรรมดา
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size//3)
        except:
            font = ImageFont.load_default()
        draw.text((size//2, size//2), "S", font=font, anchor="mm", fill='#667eea')
    
    img.save(filename)
    print(f"Created {filename}")

# สร้างไอคอนทุกขนาด
create_icon(16, 'extension/icon16.png')
create_icon(48, 'extension/icon48.png')
create_icon(128, 'extension/icon128.png')

print("\n✅ สร้างไอคอนเรียบร้อย!")
