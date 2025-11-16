#!/usr/bin/env python3
"""
สคริปต์สำหรับตรวจสอบและจัดการ Admin User
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import os
from dotenv import load_dotenv

# โหลด environment variables
load_dotenv()

def get_db_connection():
    """เชื่อมต่อ database"""
    db_url = os.environ.get('POSTGRES_URL_NON_POOLING')
    if not db_url:
        print("❌ POSTGRES_URL_NON_POOLING not found")
        return None
    
    try:
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        print("✅ Connected to database")
        return conn
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None

def list_admin_users():
    """แสดงรายการ admin users ทั้งหมด"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, created_at FROM admin_users ORDER BY id")
        users = cur.fetchall()
        
        print("\n📋 Admin Users:")
        print("-" * 60)
        for user in users:
            print(f"ID: {user['id']}")
            print(f"Username: {user['username']}")
            print(f"Created: {user['created_at']}")
            print("-" * 60)
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.close()

def check_password(username, password):
    """ตรวจสอบว่ารหัสผ่านถูกต้องหรือไม่"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        print(f"\n🔍 Checking password for: {username}")
        print(f"Password: {password}")
        print(f"Hash: {password_hash}")
        
        cur.execute("""
            SELECT id, username, password_hash FROM admin_users 
            WHERE username = %s
        """, (username,))
        
        user = cur.fetchone()
        
        if not user:
            print(f"❌ User '{username}' not found")
        else:
            print(f"\n✅ User found:")
            print(f"ID: {user['id']}")
            print(f"Username: {user['username']}")
            print(f"Stored Hash: {user['password_hash']}")
            
            if user['password_hash'] == password_hash:
                print("\n✅ Password is CORRECT!")
            else:
                print("\n❌ Password is INCORRECT!")
                print("The stored hash doesn't match the provided password")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.close()

def reset_password(username, new_password):
    """รีเซ็ตรหัสผ่าน"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        
        cur.execute("""
            UPDATE admin_users 
            SET password_hash = %s 
            WHERE username = %s
        """, (password_hash, username))
        
        if cur.rowcount > 0:
            conn.commit()
            print(f"\n✅ Password reset successfully for '{username}'")
            print(f"New password: {new_password}")
            print(f"Hash: {password_hash}")
        else:
            print(f"\n❌ User '{username}' not found")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
            conn.close()

def create_admin(username, password):
    """สร้าง admin user ใหม่"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cur.execute("""
            INSERT INTO admin_users (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO UPDATE
            SET password_hash = EXCLUDED.password_hash
        """, (username, password_hash))
        
        conn.commit()
        print(f"\n✅ Admin user created/updated:")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"Hash: {password_hash}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
            conn.close()

def main():
    """เมนูหลัก"""
    print("=" * 60)
    print("🔐 Admin User Management")
    print("=" * 60)
    print("\n1. แสดงรายการ Admin Users")
    print("2. ตรวจสอบรหัสผ่าน")
    print("3. รีเซ็ตรหัสผ่าน")
    print("4. สร้าง/อัพเดท Admin User")
    print("5. รีเซ็ต admin เป็นค่าเริ่มต้น (admin/admin123)")
    print("0. ออก")
    
    choice = input("\nเลือกเมนู: ").strip()
    
    if choice == '1':
        list_admin_users()
    elif choice == '2':
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        check_password(username, password)
    elif choice == '3':
        username = input("Username: ").strip()
        new_password = input("New Password: ").strip()
        reset_password(username, new_password)
    elif choice == '4':
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        create_admin(username, password)
    elif choice == '5':
        print("\n🔄 Resetting admin to default...")
        create_admin('admin', 'admin123')
    elif choice == '0':
        print("👋 Bye!")
        return
    else:
        print("❌ Invalid choice")

if __name__ == '__main__':
    main()
