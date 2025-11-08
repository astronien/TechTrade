from PIL import Image, ImageDraw

def create_icon(size, filename):
    # สร้างภาพพื้นหลังสีม่วง
    img = Image.new('RGB', (size, size), color='#667eea')
    draw = ImageDraw.Draw(img)
    
    # วาดวงกลมสีขาว
    margin = size // 4
    draw.ellipse([margin, margin, size-margin, size-margin], fill='white')
    
    # วาดวงกลมเล็กๆ ตรงกลาง (เหมือนคุกกี้)
    center = size // 2
    dot_size = size // 8
    draw.ellipse([center-dot_size, center-dot_size, center+dot_size, center+dot_size], fill='#667eea')
    
    img.save(filename)
    print(f"Created {filename}")

# สร้างไอคอนทุกขนาด
create_icon(16, 'extension/icon16.png')
create_icon(48, 'extension/icon48.png')
create_icon(128, 'extension/icon128.png')

print("\n✅ สร้างไอคอนเรียบร้อย!")
