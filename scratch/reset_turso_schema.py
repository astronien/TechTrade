
import os
from dotenv import load_dotenv
from turso_handler import TursoHandler

load_dotenv()

def reset_database():
    print("🔄 Resetting Turso Database with new schema...")
    turso = TursoHandler()
    if not turso.client:
        print("❌ Failed to connect to Turso. Check your .env file.")
        return

    try:
        # 1. Drop existing table
        print("🗑️ Dropping old 'trades' table...")
        turso.client.execute("DROP TABLE IF EXISTS trades")
        
        # 2. Re-initialize with new schema
        print("🏗️ Creating new 'trades' table with full columns...")
        turso.init_db()
        
        print("✅ Database reset successful! Now ready to store all columns from Eve API.")
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
    finally:
        turso.close()

if __name__ == "__main__":
    reset_database()
