import os
from dotenv import load_dotenv
from turso_handler import TursoHandler

load_dotenv()

def apply_optimization():
    print("🚀 Applying database optimizations (creating indexes)...")
    handler = TursoHandler()
    success = handler.init_db()
    if success:
        print("✅ Indexes created/verified successfully!")
    else:
        print("❌ Failed to initialize database.")
    handler.close()

if __name__ == "__main__":
    apply_optimization()
