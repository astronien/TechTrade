#!/usr/bin/env python3
"""
ทดสอบ login API
"""
import requests
import json

# URL ของ Flask app (แก้ไขตามที่ใช้งานจริง)
BASE_URL = "http://localhost:5001"

def test_login(username, password):
    """ทดสอบ login"""
    url = f"{BASE_URL}/login"
    
    print(f"\n🔐 Testing login...")
    print(f"URL: {url}")
    print(f"Username: {username}")
    print(f"Password: {password}")
    
    try:
        response = requests.post(
            url,
            json={'username': username, 'password': password},
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"\n📥 Response:")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("\n✅ Login successful!")
            else:
                print(f"\n❌ Login failed: {result.get('error')}")
        else:
            print(f"\n❌ HTTP Error: {response.status_code}")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    print("=" * 60)
    print("🧪 Login Test")
    print("=" * 60)
    
    # ทดสอบด้วย admin/admin123
    test_login('admin', 'admin123')
    
    # ทดสอบด้วยรหัสผ่านผิด
    print("\n" + "=" * 60)
    test_login('admin', 'wrongpassword')
