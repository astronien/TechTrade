from app import get_auto_cancel_config
from dotenv import load_dotenv

load_dotenv()
config = get_auto_cancel_config()
print("Current DB Config:", config)
