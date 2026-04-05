import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import fetch_data_from_api, get_eve_session

def test_fetch():
    session_id = get_eve_session()
    print(f"Using session: {session_id}")
    
    # fetch some data for Feb 2026
    filters = {
        'date_start': '01/02/2026',
        'date_end': '28/02/2026',
        'branch_id': '1847' # test branch
    }
    
    data = fetch_data_from_api(start=0, length=10, **filters)
    
    if 'data' in data and data['data']:
        items = data['data']
        print(f"Found {len(items)} items")
        for i, item in enumerate(items[:5]):
            print(f"--- Item {i+1} ---")
            print(f"Doc Number: {item.get('document_no')}")
            print(f"SALE_CODE: '{item.get('SALE_CODE', '')}'")
            print(f"SALE_NAME: '{item.get('SALE_NAME', '')}'")
            print(f"Status: {item.get('BIDDING_STATUS_NAME', '')}")
    else:
        print("No data or error:", data)

if __name__ == '__main__':
    test_fetch()
