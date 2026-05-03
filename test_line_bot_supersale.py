import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app import find_branch_by_id, fetch_data_from_api, parse_thai_month, get_month_date_range
from line_bot_handler import generate_branch_monthly_report

def test_line_bot_report():
    print("Testing generate_branch_monthly_report for branch 2957 (New Branch) for May")
    
    branch_id_input = "2957" # New branch
    month_name = "พฤษภาคม"
    
    result = generate_branch_monthly_report(
        branch_id_input, 
        month_name, 
        find_branch_by_id, 
        fetch_data_from_api, 
        parse_thai_month, 
        get_month_date_range
    )
    
    print("\n--- LINE BOT RESULT ---")
    print(result)

if __name__ == '__main__':
    test_line_bot_report()
